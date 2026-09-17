# -*- coding: utf-8 -*-
"""运行时修改 —— 直接改游戏内存（不碰存档文件）

## 为什么需要这一层
改存档只在「不玩游戏」时有用：游戏运行时读的是内存，改文件它看不见，
存盘时还会用内存的值把文件覆盖回去。**「运行中生效」只能改内存。**
好处是改完之后，游戏自己会在下次存盘时把值写进存档。

## 定位原理（不依赖 UE4 内部结构，纯值特征）
1. 拿「游戏里当前显示的数」扫可写内存 -> 得到候选地址
2. 对每个候选，看它 ±16KB 内有没有存档里那些已知的加点点数
3. **命中种类最多的候选就是真的** —— 存档对象里这些字段是挨着排的，
   蚁皇浆就排在加点字段后面几百字节处

地址每次启动游戏都会变（ASLR + 动态分配），所以每次都得重新定位。
只扫 <1MB 的小区域约 0.4 秒，可接受。

## 安全约定
- 定位不下来、或没法交叉验证 -> **报失败，不写**
- 写完立刻回读校验
- 只改定长数值（int32 / float），绝不按偏移瞎写结构
"""
import struct

from . import actions, gvas, jelly, memscan

GAME_EXE = 'EotU-Win64-Shipping.exe'
SCAN_WINDOW = 16384          # 交叉验证时看候选地址前后多大范围
JELLY_CAP = 2_000_000_000    # 补满目标：留 1.4 亿余量防加法溢出


class LiveError(Exception):
    """运行时修改失败"""


def game_proc():
    """打开游戏进程 -> memscan.Process；游戏没开返回 None"""
    pids = memscan.find_pids(GAME_EXE)
    return memscan.Process(pids[0]) if pids else None


def known_addon_values(save_file='Colony1.sav'):
    """存档里已知的加点等级（给定位做交叉验证用）"""
    try:
        ads = jelly.addons(gvas.SaveFile(actions.save_path(save_file)))
        return sorted({pts for _f, pts, _c in ads if pts})
    except Exception:                                                   # noqa: BLE001
        return []


def locate(proc, value, known=None, window=SCAN_WINDOW):
    """定位「某个数值」在内存里的地址

    value : 游戏里当前显示的那个数（蚁皇浆、加点等级都行）
    known : 交叉验证用的已知值集合；不传就自动从存档读
    -> (地址, 命中种类数, 候选总数)
       没找到 / 没法验证时地址返回 None（这种情况**不要写**）
    """
    known = list(known) if known else known_addon_values()
    hits = proc.scan_value(value, 'int32', writable_only=True,
                           max_region_mb=1, threads=8)
    if not hits:
        return None, 0, 0
    if len(hits) == 1:
        return hits[0], 0, 1

    best, best_kinds = None, -1
    for a in hits:
        lo = max(a - window, 0)
        data = proc.read(lo, window * 2)
        if not data:
            continue
        kinds = set()
        for i in range(0, len(data) - 3, 4):
            v = struct.unpack_from('<i', data, i)[0]
            if v in known:
                kinds.add(v)
        if len(kinds) > best_kinds:
            best, best_kinds = a, len(kinds)

    # 一个已知值都对不上 -> 不敢写，宁可让用户再给一个值重扫
    if not known or best_kinds == 0:
        return None, 0, len(hits)
    return best, best_kinds, len(hits)


def read_jelly(proc, addr):
    """读当前余额"""
    return proc.read_value(addr, 'int32')


def write_jelly(proc, addr, value):
    """写入余额并回读校验 -> (成功, 回读到的值)"""
    return proc.write_value(addr, int(value), 'int32')


def refill(proc, current, target=JELLY_CAP, known=None):
    """一步到位：定位 -> 写入 -> 校验

    -> dict(ok, addr, before, after, kinds, hits, msg)
    """
    addr, kinds, nhits = locate(proc, current, known=known)
    if addr is None:
        return dict(ok=False, addr=None, msg=(
            '定位失败：扫到 %d 个候选但交叉验证一个都对不上（也可能是游戏里的'
            '数值和我以为的不一样）。重新给一个当前值再试。' % nhits
            if nhits else '内存里找不到这个值 —— 游戏里显示的数是不是填错了？'))

    before = read_jelly(proc, addr)
    ok, after = write_jelly(proc, addr, target)
    return dict(ok=bool(ok and after == target), addr=addr, before=before,
                after=after, kinds=kinds, hits=nhits,
                msg=('已写入并回读校验通过' if ok and after == target
                     else '写入了但回读对不上（%s）—— 可能这个地址不是蚁皇浆' % after))
