# -*- coding: utf-8 -*-
"""抓指定进程的游戏窗口画面（纯 ctypes + GDI，PrintWindow）-> PNG

为什么不用 shot_screen.py：那个抓的是"桌面合成结果"，游戏在后台/被别的窗口盖住时
抓到的是别的窗口。PrintWindow 能直接问窗口要画面，**不抢焦点**。
实测本游戏（UnrealWindow，无边框窗口化 2560x1440）可用；独占全屏会抓到黑屏。

坑：① PrintWindow 在 user32（不是 gdi32）
    ② 所有 user32/gdi32 函数**必须声明 argtypes**，否则 64 位句柄会被截断
       （报 "int too long to convert"）

用法：python scripts/shot_win.py <pid> <输出png> [mode]
      mode=full（默认，缩小一半全画面） / top（顶栏一条，原始分辨率）
"""
import ctypes
import struct
import sys
import zlib
from ctypes import wintypes

u32 = ctypes.WinDLL('user32', use_last_error=True)
g32 = ctypes.WinDLL('gdi32', use_last_error=True)

u32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
u32.PrintWindow.restype = wintypes.BOOL
u32.GetWindowDC.argtypes = [wintypes.HWND]
u32.GetWindowDC.restype = wintypes.HDC
u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
g32.CreateCompatibleDC.argtypes = [wintypes.HDC]
g32.CreateCompatibleDC.restype = wintypes.HDC
g32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                 ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
g32.CreateDIBSection.restype = wintypes.HANDLE
g32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
g32.SelectObject.restype = wintypes.HANDLE
g32.DeleteObject.argtypes = [wintypes.HANDLE]
g32.DeleteDC.argtypes = [wintypes.HDC]


class BIH(ctypes.Structure):
    _fields_ = [('biSize', wintypes.DWORD), ('biWidth', ctypes.c_long),
                ('biHeight', ctypes.c_long), ('biPlanes', wintypes.WORD),
                ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', ctypes.c_long),
                ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD)]


def hwnd_of(pid, cls='UnrealWindow'):
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, lp):
        p = wintypes.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            c = ctypes.create_unicode_buffer(256)
            u32.GetClassNameW(h, c, 256)
            if not cls or c.value == cls:
                found.append(h)
        return True
    u32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def grab(hwnd):
    r = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    W, H = r.right - r.left, r.bottom - r.top
    hdc = u32.GetWindowDC(hwnd)
    mem = g32.CreateCompatibleDC(hdc)
    bmi = BIH()
    bmi.biSize, bmi.biWidth, bmi.biHeight = 40, W, -H
    bmi.biPlanes, bmi.biBitCount, bmi.biCompression = 1, 32, 0
    bits = ctypes.c_void_p()
    bmp = g32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    g32.SelectObject(mem, bmp)
    u32.PrintWindow(hwnd, mem, 2)
    raw = ctypes.string_at(bits, W * H * 4)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mem)
    u32.ReleaseDC(hwnd, hdc)
    lum = sum(raw[i] for i in range(0, len(raw), 4000)) / max(1, len(range(0, len(raw), 4000)))
    return raw, W, H, lum


def write_png(path, rows, w, h):
    def ck(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n'
        + ck(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
        + ck(b'IDAT', zlib.compress(b''.join(rows), 6))
        + ck(b'IEND', b''))


def main():
    pid = int(sys.argv[1])
    out = sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else 'full'
    hs = hwnd_of(pid)
    if not hs:
        print('  找不到该进程的 UnrealWindow'); return 1
    raw, W, H, lum = grab(hs[0])
    print('  窗口 %dx%d  采样亮度 %.1f' % (W, H, lum))
    if lum <= 5:
        print('  ✗ 全黑（独占全屏抓不到，改用桌面截图）'); return 2
    if mode == 'top':
        ys, step = range(0, min(46, H)), 1
    else:
        ys, step = range(0, H, 2), 2
    rows = []
    for y in ys:
        row = bytearray([0])
        for x in range(0, W, step):
            o = (y * W + x) * 4
            row += bytes((raw[o+2], raw[o+1], raw[o]))
        rows.append(bytes(row))
    write_png(out, rows, len(range(0, W, step)), len(rows))
    print('  已保存 %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
