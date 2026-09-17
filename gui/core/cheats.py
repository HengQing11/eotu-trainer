# -*- coding: utf-8 -*-
"""关卡官方作弊开关 —— UGTileGrid 上的调试 bool（SDK 官方字段名证实）

界面顶栏的"食物" = UGTileGrid.ResourcesAvailable(+0x4FC)，只是**显示副本**，
建造判定不读它（2026-09-16 整晚验证的死路）。真正有效的是开发者留在
同一个对象上的 4 个调试 bool（连续 4 字节，一次 int32 写 0x01010101 全开）：

    +0x63A InfinateResources  无限资源
    +0x63B FreeHatch          免费孵化
    +0x63C InstantBuild       秒建
    +0x63D InstantDig         秒挖

UGTileGrid 的特征：vtable RVA 0x3CCDDB0（一关多个，玩家 = 容量最小那个）。
本模块只依赖 memscan，可打进 exe。
"""
import ctypes
import struct
from ctypes import wintypes

from . import memscan

GAME_EXE = 'EotU-Win64-Shipping.exe'
G_WORLD_RVA = 0x4FFB958
GRID_RVA = 0x3CCDDB0
RES_OFF = 0x4FC
MAX_OFF = 0x500
FLAG_BASE = 0x63A
FLAG_ALL_ON = 0x01010101

FLAG_DEFS = [('infinite', 0x63A, '无限资源', 'InfinateResources'),
             ('freehatch', 0x63B, '免费孵化', 'FreeHatch'),
             ('instant_build', 0x63C, '秒建', 'InstantBuild'),
             ('instant_dig', 0x63D, '秒挖', 'InstantDig')]

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
    """主模块基址/大小（toolhelp 快照，游戏重启后会变，每次都重新拿）"""
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


def _u64(d, o):
    return struct.unpack_from('<Q', d, o)[0]


def _i32(d, o):
    return struct.unpack_from('<i', d, o)[0]


def level_of(proc, base):
    raw = proc.read(base + G_WORLD_RVA, 8)
    if not raw or len(raw) < 8:
        return None
    gw = struct.unpack('<Q', raw)[0]
    if not gw:
        return None
    wd = proc.read(gw, 0x200)
    if not wd or len(wd) < 0x38:
        return None
    return _u64(wd, 0x30)


def actors(proc, level):
    ld = proc.read(level, 0x100)
    if not ld or len(ld) < 0xA4:
        return []
    aptr, anum = _u64(ld, 0x98), struct.unpack_from('<I', ld, 0xA0)[0]
    if not aptr or not (0 < anum < 200000):
        return []
    raw = proc.read(aptr, anum * 8)
    if not raw:
        return []
    return [_u64(raw, 8 * i) for i in range(anum)]


def find_grid(proc, base):
    """玩家的 UGTileGrid = vtable 匹配的候选里容量最小的那个"""
    level = level_of(proc, base)
    if not level:
        return None
    cols = []
    for a in actors(proc, level):
        h = proc.read(a, 8)
        if not h or len(h) < 8:
            continue
        try:
            if _u64(h, 0) - base != GRID_RVA:
                continue
        except (TypeError, ValueError):
            continue
        res, cap = proc.read_value(a + RES_OFF), proc.read_value(a + MAX_OFF)
        if res is None or cap is None or not (0 <= cap <= 1000000 and 0 <= res <= 1000000):
            continue
        cols.append((a, res, cap))
    if not cols:
        return None
    cols.sort(key=lambda t: t[2])
    return cols[0][0]


def read_status(proc, grid):
    """资源 + 四个开关的布尔状态（读字节，别按 int32 读——4 个开关挤在 4 字节里）"""
    raw = proc.read(grid + FLAG_BASE, 4)
    flags = {}
    for i, (key, _off, _cn, _en) in enumerate(FLAG_DEFS):
        flags[key] = bool(raw[i]) if raw and len(raw) == 4 else False
    return dict(res=proc.read_value(grid + RES_OFF),
                cap=proc.read_value(grid + MAX_OFF),
                flags=flags)


def apply_flags(proc, grid, wants):
    """按 {key: bool} 设置开关；一次 int32 写齐 4 个字节，返回写入的字节值"""
    cur = read_status(proc, grid)['flags']
    packed = 0
    for i, (key, _off, _cn, _en) in enumerate(FLAG_DEFS):
        want = wants.get(key, cur.get(key, False))
        if want:
            packed |= 1 << (8 * i)
    proc.write_value(grid + FLAG_BASE, packed, 'int32')
    return packed


def connect():
    """连上游戏；返回 (proc, base) 或 (None, None)。网格定位失败也返回，供上层重试"""
    pids = memscan.find_pids(GAME_EXE)
    if not pids:
        return None, None
    proc = memscan.Process(pids[0])
    info = module_info(pids[0])
    if not info:
        proc.close()
        return None, None
    return proc, info[0]


# ------------------------------------------------------------------ 蚁皇浆（运行时）
# 锚点定位（jelly_live.py 同款，2026-09-16 标定并实测）：同一 vtable 的候选里
# 用"玩没玩过"打分挑真身 —— 与浆的值无关，新档（浆=0）也能定位。
JELLY_OFF = 0x89C
TOT_RES_OFF = 0x86C
TILES_OFF = 0x8B4
JELLY_CAP = 2_000_000_000


def colony_candidates(proc, base):
    """vtable 匹配的全部候选对象"""
    level = level_of(proc, base)
    if not level:
        return []
    out = []
    for a in actors(proc, level):
        h = proc.read(a, 8)
        if not h or len(h) < 8:
            continue
        try:
            if _u64(h, 0) - base == GRID_RVA:
                out.append(a)
        except (TypeError, ValueError):
            continue
    return out


def score_colony(proc, obj):
    """打分挑"玩家在玩的那个"：累计采集>0 +3 / 已挖掘>0 +2 / 加点等级≥3 种 +2 / 浆>0 +1"""
    s = 0
    tot = proc.read_value(obj + TOT_RES_OFF)
    til = proc.read_value(obj + TILES_OFF)
    jel = proc.read_value(obj + JELLY_OFF)
    if isinstance(tot, int) and tot > 0:
        s += 3
    if isinstance(til, int) and til > 0:
        s += 2
    d = proc.read(obj, 0x2000)
    if d:
        lv = {struct.unpack_from('<i', d, o)[0]
              for o in range(0x40, len(d) - 3, 4)
              if 1 <= struct.unpack_from('<i', d, o)[0] <= 10}
        if len(lv) >= 3:
            s += 2
    if isinstance(jel, int) and jel > 0:
        s += 1
    return s


def find_play_colony(proc, base):
    """打分最高的候选（找不到候选返回 None）"""
    cands = colony_candidates(proc, base)
    if not cands:
        return None
    best, best_s = None, -1
    for a in cands:
        s = score_colony(proc, a)
        if s > best_s:
            best, best_s = a, s
    return best


def read_jelly(proc, obj):
    return proc.read_value(obj + JELLY_OFF)


def refill_jelly(proc, obj, base, target=JELLY_CAP):
    """写入前复核 vtable（堆地址会复用），写 20 亿后回读校验 -> (成功, 回读值)"""
    h = proc.read(obj, 8)
    if not h or len(h) < 8:
        return False, None
    try:
        if _u64(h, 0) - base != GRID_RVA:
            return False, None
    except (TypeError, ValueError):
        return False, None
    proc.write_value(obj + JELLY_OFF, int(target), 'int32')
    after = proc.read_value(obj + JELLY_OFF)
    return (after == int(target)), after
