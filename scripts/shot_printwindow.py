# -*- coding: utf-8 -*-
"""用 PrintWindow(PW_RENDERFULLCONTENT) 抓 frameless 窗口（BitBlt 抓不到）"""
import ctypes
import sys
from ctypes import wintypes

sys.path.insert(0, r'D:/aiwork/WorkBuddy/2026-09-13-11-21-03/mod/scripts')
import shot_win as sw

u32 = ctypes.WinDLL('user32')
g32 = ctypes.WinDLL('gdi32')

u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.GetWindowDC.argtypes = [wintypes.HWND]
u32.GetWindowDC.restype = wintypes.HDC
u32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
u32.PrintWindow.restype = wintypes.BOOL
u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
g32.CreateCompatibleDC.argtypes = [wintypes.HDC]
g32.CreateCompatibleDC.restype = wintypes.HDC
g32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
g32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
g32.SelectObject.argtypes = [wintypes.HDC, wintypes.HBITMAP]
g32.SelectObject.restype = wintypes.HBITMAP
g32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                          wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p,
                          wintypes.UINT]
g32.GetDIBits.restype = ctypes.c_int
g32.DeleteObject.argtypes = [wintypes.HANDLE]
g32.DeleteDC.argtypes = [wintypes.HDC]


class BMIH(ctypes.Structure):
    _fields_ = [('biSize', wintypes.DWORD), ('biWidth', ctypes.c_long),
                ('biHeight', ctypes.c_long), ('biPlanes', wintypes.WORD),
                ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD), ('biXPels', ctypes.c_long),
                ('biYPels', ctypes.c_long), ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD)]


def capture(h, out_path):
    rect = wintypes.RECT()
    if not u32.GetWindowRect(h, ctypes.byref(rect)):
        return None
    W, H = rect.right - rect.left, rect.bottom - rect.top
    if W <= 0 or H <= 0:
        return None
    hdc = u32.GetWindowDC(h)
    mem = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, W, H)
    old = g32.SelectObject(mem, bmp)
    ok = u32.PrintWindow(h, mem, 2)          # PW_RENDERFULLCONTENT
    bi = BMIH(ctypes.sizeof(BMIH), W, -H, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = (ctypes.c_ubyte * (W * H * 4))()
    got = g32.GetDIBits(mem, bmp, 0, H, buf, ctypes.byref(bi), 0)
    rows = []
    for y in range(0, H, 2):
        row = bytearray([0])
        for x in range(0, W, 2):
            o = (y * W + x) * 4
            row += bytes((buf[o + 2], buf[o + 1], buf[o]))
        rows.append(bytes(row))
    sw.write_png(out_path, rows, len(range(0, W, 2)), len(rows))
    g32.SelectObject(mem, old)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mem)
    u32.ReleaseDC(h, hdc)
    return W, H, ok, got


if __name__ == '__main__':
    title_kw = sys.argv[1] if len(sys.argv) > 1 else '地下蚁国'
    out = sys.argv[2] if len(sys.argv) > 2 else \
        r'D:/aiwork/WorkBuddy/2026-09-13-11-21-03/mod/ui_web_pw.png'

    u32.EnumWindows
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, lp):
        b = ctypes.create_unicode_buffer(64)
        u32.GetWindowTextW(h, b, 64)
        if title_kw in b.value:
            found.append((h, b.value))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                     wintypes.LPARAM)
    u32.EnumWindows(WNDENUMPROC(cb), 0)
    print('  窗口：', [t for _h, t in found] or '（没找到）')
    for h, t in found:
        r = capture(h, out)
        if r:
            print('  ✓ %s → %s（PrintWindow=%s, GetDIBits=%s）'
                  % (t, out, r[2], r[3]))
            break
