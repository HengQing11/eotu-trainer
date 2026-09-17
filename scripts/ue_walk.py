# -*- coding: utf-8 -*-
"""UE4 对象遍历 —— 用游戏自己的对象系统去找东西（不猜数值）

为什么需要这一层
----------------
纯数值扫描会撞上"显示字段"：游戏会写它、UI 会读它，但真正做判定的是
另一份数据。要从"显示值"走到"真身"，只能走对象系统：
    GWorld(固定RVA) → UWorld → ULevel → Actors[] → 具体对象 → 字段
项目日志里 GWorld RVA=0x4FFB958（Dumper-7 导出，已复验有效）。

用法：python scripts/ue_walk.py
"""
import ctypes
import os
import struct
import sys
from ctypes import wintypes

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import try_food as tf                                               # noqa: E402

GAME_EXE = tf.GAME_EXE
G_WORLD_RVA = 0x4FFB958
k32 = ctypes.WinDLL('kernel32', use_last_error=True)


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('th32ModuleID', wintypes.DWORD),
                ('th32ProcessID', wintypes.DWORD), ('GlblcntUsage', wintypes.DWORD),
                ('ProccntUsage', wintypes.DWORD), ('modBaseAddr', ctypes.c_void_p),
                ('modBaseSize', wintypes.DWORD), ('hModule', ctypes.c_void_p),
                ('szModule', ctypes.c_char * 256), ('szExePath', ctypes.c_char * 260)]


k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.Module32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
k32.Module32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]


def module_info(pid):
    snap = k32.CreateToolhelp32Snapshot(0x00000018, pid)
    me = MODULEENTRY32()
    me.dwSize = ctypes.sizeof(MODULEENTRY32)
    out = None
    ok = k32.Module32First(snap, ctypes.byref(me))
    while ok:
        if me.szModule.decode('latin1', 'ignore').lower() == GAME_EXE.lower():
            out = (me.modBaseAddr, me.modBaseSize)
            break
        ok = k32.Module32Next(snap, ctypes.byref(me))
    k32.CloseHandle(snap)
    return out


def u64(d, o):
    return struct.unpack_from('<Q', d, o)[0]


def u32(d, o):
    return struct.unpack_from('<I', d, o)[0]


def i32(d, o):
    return struct.unpack_from('<i', d, o)[0]


def looks_ptr(v):
    return 0x10000 < v < 0x7FFFFFFFFFFF


def is_obj(proc, v, base, size):
    """首 8 字节是落在游戏镜像内的 vtable -> 像个 UObject"""
    if not looks_ptr(v):
        return False
    h = proc.read(v, 8)
    if not h:
        return False
    vt = u64(h, 0)
    return base <= vt < base + size


def find_arrays(proc, obj, base, size, span=0x2000, min_n=2, must_be_objs=True):
    """在对象里找 TArray<指针>：{T* Data; int32 Num; int32 Max}"""
    d = proc.read(obj, span)
    if not d:
        return []
    out = []
    for o in range(0, len(d) - 16, 4):
        p = u64(d, o)
        n, m = u32(d, o + 8), u32(d, o + 12)
        if not (looks_ptr(p) and min_n <= n <= m <= 500000):
            continue
        if must_be_objs:
            e = proc.read(p, 8 * min(n, 4))
            if not e or len(e) < 8:
                continue
            if not all(is_obj(proc, u64(e, 8 * i), base, size)
                       for i in range(min(n, 4))):
                continue
        out.append((o, p, n, m))
    return out
