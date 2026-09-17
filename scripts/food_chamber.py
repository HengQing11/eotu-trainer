# -*- coding: utf-8 -*-
"""食物（关卡内）—— 自动定位 + 补满 + 智能补给

## 真身是什么（2026-09-16 用硬件写断点破出，用户实测有效）
食物是**两本账**，必须同时给，缺一个都花不出去：

1. **仓库**：每个粮仓格子对象的 `+0x290`（现存）/ `+0x294`（每格上限）
   —— 游戏自己的累加代码：`mov eax,[格子+0x290] / add [账面+0x4FC],eax`
2. **账面**：殖民地记录对象的 `+0x4FC`（总量）/ `+0x500`（总容量）
   —— **建造判定读的是它**。只给仓库不给账面 → 界面仍显示 0，照样建不了

> 用户的原话很准："仓库里有食物，但账面上没有，所以花费不了。"

## 自动定位原理（互相验证，不含任何硬编码地址）
- **格子候选**：关卡 Actor 里「+0x294 在 [1,1000] 且 +0x290 ≤ +0x294」的那些实例所属的类
  （⚠️ **不能要求各格上限相同** —— 粮仓升级后每格上限会不一样，实测踩过）
- **账面记录**：形状 `[总量, 总容量, 0×16, float 1.0f]`，
  且 **总容量 == Σ(格子的 +0x294)** —— 用这个等式把两边互相钉死，
  再用「所属对象 vtable 在镜像内 + Outer == ULevel」二次确认
- 账本对象**本身就是关卡 Actor 之一**，所以直接遍历 Actor 表即可，**不扫内存**
  （曾经全内存扫字节特征，被 5 万命中上限截断而定位失败 —— 别再走那条路）

## ★ 写入安全（2026-09-16 19:30 加固，必读）
改内存最怕"写到已经是别人家的地址上"：粮仓被拆/升级后，旧格子对象可能已被释放，
内存被别的东西复用；此时再往 `+0x290` 写就是**破坏别人的数据**。
所以现在**每次写入前都核对对象身份**（读 +0x00 的 vtable、+0x10 的 ClassPrivate，
与定位时记录的值逐一比对），任何一个对不上就**立刻停写并重新定位**。
身份记录存在缓存里；**老缓存（无 idents 字段）会被判为失效并自动重新定位**。

用法：
    python scripts/food_chamber.py report       # 自动定位并核对（只读）
    python scripts/food_chamber.py fill         # 仓库 + 账面一起补满（一次性）
    python scripts/food_chamber.py set 5        # 总量设成 5（按各格上限铺开）
    python scripts/food_chamber.py hold [秒] [百分比]   # 智能补给（默认 3600 秒 / 80%）
    python scripts/food_chamber.py lock [秒]    # 先补满，再无条件锁住（不推荐日常用）

日常用 `mod\\食物自动补给.bat`（= hold 86400 80，关窗口即停）。

## 关卡结束自动收工（2026-09-16 新增）
`hold` / `lock` 每轮都会检查"关卡还在不在"，命中任一条即以返回码
`EXIT_LEVEL_ENDED = 10` 退出 —— bat 收到这个码会**自动关闭窗口**，不用手动关：
1. **游戏进程退出**
2. **UWorld / ULevel 换人**（关卡卸载、切换下一关、回大地图）
3. **连续 6 次找不到粮仓/账本**（≈12 秒，说明关卡已经没了）
换新关卡后想继续用，再双击一次 bat 即可（它会重新定位，约 0.3 秒）。
"""

import json
import os
import struct
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import try_food as tf                                              # noqa: E402
import ue_walk as uw                                               # noqa: E402

FOOD_OFF = 0x290          # 每格现存
CAP_OFF = 0x294           # 每格上限
LEDGER_OFF = 0x4FC        # 账面上的总量（账面对象内偏移）
IDENT_SPAN = 0x18         # 身份指纹长度：vtable(8) + 0x10 处的 ClassPrivate(8)
CACHE = os.path.join(_HERE, os.pardir, 'food_locate.json')


class LocateError(Exception):
    pass


class StaleError(Exception):
    """定位已失效（对象被释放/换人）—— 必须重新定位后才能继续写"""


# ------------------------------------------------------------------ 定位

def _level_of(proc, base):
    gw = struct.unpack('<Q', proc.read(base + uw.G_WORLD_RVA, 8))[0]
    return uw.u64(proc.read(gw, 0x200), 0x30)


def _actors(proc, level):
    ld = proc.read(level, 0x100)
    aptr, anum = uw.u64(ld, 0x98), uw.u32(ld, 0xA0)
    raw = proc.read(aptr, anum * 8)
    if not raw:
        raise LocateError('读不到 Actor 表 —— 可能没进关卡')
    return [uw.u64(raw, 8 * i) for i in range(anum)]


def _fingerprint(proc, addr):
    """对象的身份指纹：vtable + ClassPrivate。读不到返回 None"""
    d = proc.read(addr, IDENT_SPAN)
    if not d or len(d) < IDENT_SPAN:
        return None
    return [uw.u64(d, 0), uw.u64(d, 0x10)]


def _candidate_classes(proc, actors):
    by = {}
    for a in actors:
        d, h = proc.read(a + FOOD_OFF, 8), proc.read(a, 0x20)
        if not d or not h:
            continue
        by.setdefault(uw.u64(h, 0x10), []).append((a, uw.i32(d, 0), uw.i32(d, 4)))
    out = []
    for c, items in by.items():
        if not (2 <= len(items) <= 64):
            continue
        # 每格：上限在合理范围、现存不超过上限（各格上限允许不同）
        if any(not (1 <= cap <= 1000) for _a, _f, cap in items):
            continue
        if any(not (0 <= f <= cap) for _a, f, cap in items):
            continue
        out.append((c, [a for a, _f, _c in items],
                    [f for _a, f, _c in items],
                    [cap for _a, _f, cap in items]))
    return out


def _find_ledger(proc, base, size, level):
    """找殖民地账面记录

    **主路径（快、稳）**：账本对象本身就是关卡 Actor 之一，直接遍历 ULevel 的
    Actor 数组，逐个测"资源记录形状"即可 —— **完全不扫内存**，0.1 秒级，
    也不会撞上"字节特征太常见被 limit 截断"的坑（踩过两次）。
    **兜底**：万一它不在数组里，就按「候选格子类的容量组合」逐个扫字节特征。
    """
    from itertools import combinations
    tail = b'\x00' * 16 + struct.pack('<f', 1.0)

    def probe(o):
        d = proc.read(o + LEDGER_OFF - 4, 32)
        if not d or len(d) < 32 or d[12:32] != tail:
            return None
        food, cap = uw.i32(d, 4), uw.i32(d, 8)
        if not (0 <= food <= cap <= 100000):
            return None
        od = proc.read(o, 0x40)
        if not od or uw.u64(od, 0x20) != level:
            return None
        return dict(ledger_food=o + LEDGER_OFF,
                    ledger_cap=o + LEDGER_OFF + 4, cap_total=cap,
                    food=food, obj=o,
                    ledger_ident=[uw.u64(od, 0), uw.u64(od, 0x10)])

    # ① 主路径：账本对象**本身就是关卡 Actor**，直接遍历 Actor 表逐个测形状
    #    （实测 2000 个 Actor 只要 0.01 秒；比扫内存快几个数量级，也不会被截断）
    out = []
    for a in _actors(proc, level):
        r = probe(a)
        if r:
            out.append(r)
    if out:
        return out

    # ② 次路径：万一它不在 Actor 表里，遍历 ULevel 里的对象数组
    for _off, ptr, num, _mx in uw.find_arrays(proc, level, base, size,
                                              span=0x4000, min_n=1):
        n = min(num, 8000)
        raw = proc.read(ptr, n * 8)
        if not raw:
            continue
        for i in range(n):
            o = uw.u64(raw, 8 * i)
            if uw.looks_ptr(o):
                r = probe(o)
                if r:
                    out.append(r)
    if out:
        return out

    # ③ 兜底：按容量值扫字节。⚠️ 这条极慢（4.5GB 扫一遍 ~3 分钟），
    #    只在①②都失败时才会走到，所以打一行提示免得像"卡死"。
    tf.log('  ⚠ 前两条路都没找到账本，走兜底字节扫描（较慢，约 1~3 分钟）…')
    cands = _candidate_classes(proc, _actors(proc, level))
    totals = []
    for k in (1, 2):
        for combo in combinations(cands, k):
            t = sum(sum(c[3]) for c in combo)
            if t not in totals:
                totals.append(t)
    for t in totals:
        for h in proc.scan_bytes(struct.pack('<i', t) + tail,
                                 writable_only=True, threads=4,
                                 max_region_mb=512, limit=400):
            r = probe(h - LEDGER_OFF - 4)
            if r:
                out.append(r)
    return out


def _combo_for(cands, target, food_hint=None):
    """在候选类里找一组，使 Σ(所有格子的上限) 正好 == target

    粮仓可能横跨多个类（实测：7 格 + 9 格两类加起来 160），所以不能按单个类去对，
    必须做组合匹配。若给了 food_hint（账面上的存量），优先选「现存之和也对得上」
    的那组 —— 有两组容量相同却填不满一个等式时，这一条能把它们分开。
    """
    from itertools import combinations
    fallback = None
    for k in range(1, min(len(cands), 4) + 1):
        for combo in combinations(cands, k):
            if sum(sum(c[3]) for c in combo) != target:
                continue
            if food_hint is None:
                return list(combo)
            if sum(sum(c[2]) for c in combo) == food_hint:
                return list(combo)
            if fallback is None:
                fallback = list(combo)
    return fallback


def verify(proc, loc):
    """★ 写入前的安全闸：逐个核对对象身份，返回 (可以用的格子, 出问题的格子)

    为什么必须做：粮仓被拆/升级后，旧格子对象可能已释放、内存被别人复用。
    此时它的 vtable(对象首 8 字节) 和 ClassPrivate(+0x10) 都会变 —— 一读便知。
    任何一项对不上，就绝不能往它上面写。
    """
    idents = loc.get('idents') or []
    good, bad = [], []
    for i, a in enumerate(loc['chambers']):
        fp = _fingerprint(proc, a)
        want = idents[i] if i < len(idents) else None
        if fp and want and fp == want:
            good.append(a)
        else:
            bad.append(a)
    # 账本对象也要核
    lob = loc.get('ledger_obj')
    lid = loc.get('ledger_ident')
    if lob and lid:
        if _fingerprint(proc, lob) != lid:
            bad.append(lob)
    return good, bad


def _same(proc, loc):
    """缓存是否仍然自洽：身份都在 + 账面容量 == 各格上限之和"""
    good, bad = verify(proc, loc)
    if bad or len(good) != len(loc['chambers']):
        return False
    try:
        return (proc.read_value(loc['ledger_cap']) ==
                sum(proc.read_value(a + CAP_OFF) for a in loc['chambers']))
    except (KeyError, TypeError):
        return False


def locate(proc, base, size, use_cache=True, verbose=True):
    level = _level_of(proc, base)

    if use_cache and os.path.isfile(CACHE):
        try:
            d = json.load(open(CACHE, encoding='utf-8'))
            if (d.get('exe_base') == base and d.get('level') == level
                    and d.get('chambers') and d.get('idents')
                    and _same(proc, d)):
                if verbose:
                    tf.log('  ✓ 用上次定位（地址与身份都已核对）')
                return d
            if verbose:
                tf.log('  （缓存失效，重新定位）')
        except (OSError, ValueError, KeyError):
            pass

    ledgers = _find_ledger(proc, base, size, level)
    if not ledgers:
        raise LocateError('找不到殖民地账面记录 —— 可能没进关卡')
    if verbose:
        tf.log('  账本候选 %d 个：%s'
               % (len(ledgers), [(tf.fmt(x['ledger_cap']), x['cap_total'])
                                 for x in ledgers]))

    cands = _candidate_classes(proc, _actors(proc, level))
    if verbose:
        tf.log('  候选格子类 %d 个：' % len(cands))
        for c, addrs, foods, caps in cands:
            tf.log('    %s  %2d 格  合计 %d / %d  各格上限 %s'
                   % (tf.fmt(c), len(addrs), sum(foods), sum(caps),
                      sorted(set(caps))[:6]))

    for lg in ledgers:
        combo = _combo_for(cands, lg['cap_total'], lg.get('food'))
        if not combo:
            continue
        chambers = [a for c in combo for a in c[1]]
        caps = [x for c in combo for x in c[3]]
        foods = [x for c in combo for x in c[2]]
        idents = [_fingerprint(proc, a) for a in chambers]
        if any(x is None for x in idents):
            continue
        res = dict(exe_base=base, level=level,
                   cls=[c[0] for c in combo], chambers=chambers, caps=caps,
                   idents=idents, cap_total=lg['cap_total'],
                   ledger_food=lg['ledger_food'], ledger_cap=lg['ledger_cap'],
                   ledger_obj=lg.get('obj'), ledger_ident=lg.get('ledger_ident'))
        try:
            json.dump(res, open(CACHE, 'w', encoding='utf-8'), indent=1)
        except OSError:
            pass
        if verbose:
            tf.log('  ★ 定位成功：%d 个格子（来自 %d 个类），总容量 %d，账面 @%s'
                   % (len(chambers), len(combo), lg['cap_total'],
                      tf.fmt(lg['ledger_food'])))
            tf.log('    仓库现状 %s（合计 %d）' % (foods, sum(foods)))
        return res
    raise LocateError('账面的容量值找不到对应的格子组合 —— 可能没进关卡，或者结构变了')


def relocate(proc, base, size, verbose=True):
    """丢掉缓存，强制重新定位"""
    try:
        os.remove(CACHE)
    except OSError:
        pass
    return locate(proc, base, size, use_cache=False, verbose=verbose)


# ------------------------------------------------------------------ 写

def fill(proc, loc, strict=True):
    """仓库 + 账面一起补满。

    只写"确实需要改"的格子，且每个格子写之前先核身份（strict=False 时跳过核对，
    仅用于确认无害的一次性场景）。身份不符 -> 抛 StaleError，绝不硬写。
    """
    good, bad = verify(proc, loc)
    if bad and strict:
        raise StaleError('有 %d 个对象身份不符（疑似已被释放/复用），已停止写入' % len(bad))
    n = 0
    total = 0
    for a in good:
        cap = proc.read_value(a + CAP_OFF)
        if cap is None:
            continue
        total += cap
        if proc.read_value(a + FOOD_OFF) != cap:        # 已经是满的不写
            if proc.write_value(a + FOOD_OFF, cap)[0]:
                n += 1
    if proc.read_value(loc['ledger_food']) != total:
        proc.write_value(loc['ledger_food'], total)
    return n, total


def set_total(proc, loc, value):
    """总量设成 value：按各格上限依次铺开，再写账面"""
    good, bad = verify(proc, loc)
    if bad:
        raise StaleError('有 %d 个对象身份不符，已停止写入' % len(bad))
    left = max(0, int(value))
    for a in good:
        cap = proc.read_value(a + CAP_OFF) or 0
        v = min(cap, left)
        if proc.read_value(a + FOOD_OFF) != v:
            proc.write_value(a + FOOD_OFF, v)
        left -= v
    proc.write_value(loc['ledger_food'], min(int(value), loc['cap_total']))


def spend(proc, loc, n):
    """从食物里扣掉 n（模拟花费），返回实际扣掉多少"""
    good, bad = verify(proc, loc)
    if bad:
        raise StaleError('有 %d 个对象身份不符，已停止写入' % len(bad))
    left = max(0, int(n))
    for a in good:
        cur = proc.read_value(a + FOOD_OFF) or 0
        d = min(cur, left)
        if d:
            proc.write_value(a + FOOD_OFF, cur - d)
            left -= d
        if not left:
            break
    proc.write_value(loc['ledger_food'],
                     max(0, (proc.read_value(loc['ledger_food']) or 0) - int(n)))
    return int(n) - left


# ------------------------------------------------------------------ 关卡结束探测

EXIT_LEVEL_ENDED = 10     # 关卡结束/切换 —— bat 看到这个返回码就**自动关窗口**


def level_fingerprint(proc, base):
    """当前关卡指纹 = (UWorld, ULevel, Actor 数量)，读不到就返回 None

    为什么用它判断"关卡结束"：打完一关后游戏会卸载/切换关卡 —— UWorld 或 ULevel
    对象必然更换（回到大地图、进入下一关都一样），Actor 数量也会突变。这是**结构性**
    信号，比去抓某个"胜利标志"字段稳得多（那个字段要先解决符号/名字解析才认得出来）。
    ⚠️ 地址每次重启游戏都变，所以只在**同一次运行内**做前后比对，不跨进程比较。
    """
    try:
        raw = proc.read(base + uw.G_WORLD_RVA, 8)
        if not raw or len(raw) < 8:
            return None
        gw = struct.unpack('<Q', raw)[0]
        if not gw:
            return None
        wd = proc.read(gw, 0x200)
        if not wd:
            return None
        level = uw.u64(wd, 0x30)
        if not level:
            return None
        ld = proc.read(level, 0x100)
        if not ld:
            return None
        return (gw, level, uw.u32(ld, 0xA0))
    except (struct.error, TypeError, ValueError):
        return None


def game_alive():
    """游戏进程还在不在（Toolhelp 快照，别每轮都调 —— 由调用方节流）"""
    try:
        return bool(tf.memscan.find_pids(tf.GAME_EXE))
    except OSError:
        return False


# ------------------------------------------------------------------ 主流程

def main():
    tf._LOG = open(tf.LOG_PATH, 'a', encoding='utf-8')
    mode = sys.argv[1] if len(sys.argv) > 1 else 'report'
    nums = []
    for x in sys.argv[2:]:
        try:
            nums.append(int(x))
        except ValueError:
            pass

    pids = tf.memscan.find_pids(tf.GAME_EXE)
    if not pids:
        tf.log('  ✗ 游戏没开（先打开游戏并进入一关）')
        return 1
    proc = tf.memscan.Process(pids[0])
    base, size = uw.module_info(pids[0])
    tf.log('  ✓ 已连上游戏（pid %d，镜像 %s）' % (pids[0], tf.fmt(base)))

    try:
        loc = locate(proc, base, size)
    except LocateError as e:
        tf.log('  ✗ %s' % e)
        return 2

    def dump(tag):
        now = [proc.read_value(a + FOOD_OFF) for a in loc['chambers']]
        tf.log('  %s：仓库 %d 格 = %s（合计 %d / %d）  账面 %s / %s'
               % (tag, len(now), now, sum(v for v in now if v),
                  loc['cap_total'], proc.read_value(loc['ledger_food']),
                  proc.read_value(loc['ledger_cap'])))

    def safe_relocate():
        nonlocal loc
        try:
            loc = relocate(proc, base, size, verbose=True)
            dump('重新定位后')
            return True
        except LocateError as e:
            tf.log('    ⚠ 重新定位失败：%s（本轮跳过）' % e)
            return False

    dump('当前')
    if mode == 'report':
        good, bad = verify(proc, loc)
        tf.log('  身份核对：%d 个正常，%d 个异常' % (len(good), len(bad)))
        tf.log('  → fill 补满 / set <值> 指定 / hold [秒] [百分比] 智能补给 / lock [秒] 锁住')
        return 0

    if mode == 'fill':
        try:
            n, total = fill(proc, loc)
            tf.log('  ✓ 已补满（实际改了 %d 格），账面写入 %d' % (n, total))
        except StaleError as e:
            tf.log('  ⚠ %s' % e)
            return 4
    elif mode == 'set' and nums:
        try:
            set_total(proc, loc, nums[0])
            tf.log('  ✓ 已设为 %d' % nums[0])
        except StaleError as e:
            tf.log('  ⚠ %s' % e)
            return 4
    elif mode == 'lock':
        secs = nums[0] if nums else 60
        n, total = fill(proc, loc)
        dump('补满后')
        tf.log('  ★ 开始锁住（%(n)d 格 + 账面 = %(t)d）—— **关闭这个窗口就停止**'
               % {'n': n, 't': total})
        tf.log('    ⚠ 锁住期间会持续覆盖游戏自己的账 —— 建议只在"要一口气建东西"时用')
        fp0 = level_fingerprint(proc, base)
        t0 = time.time()
        last, writes, miss_loc = 0.0, 0, 0
        try:
            while time.time() - t0 < secs:
                fp = level_fingerprint(proc, base)
                if fp is None or (fp0 and (fp[0] != fp0[0] or fp[1] != fp0[1])):
                    tf.log('  ★ 关卡已结束/切换 —— 自动收工')
                    return EXIT_LEVEL_ENDED
                good, bad = verify(proc, loc)
                if bad:
                    tf.log('    …有 %d 个对象身份不符，重新定位…' % len(bad))
                    if not safe_relocate():
                        time.sleep(0.5)
                        continue
                try:
                    fill(proc, loc)
                    writes += 1
                except StaleError:
                    safe_relocate()
                el = time.time() - t0
                if el - last >= 10:
                    last = el
                    tf.log('    …锁定中 %.0f 秒（食物 %s / %s，已写 %d 次）'
                           % (el, proc.read_value(loc['ledger_food']),
                              proc.read_value(loc['ledger_cap']), writes))
                time.sleep(0.15)
        except KeyboardInterrupt:
            pass
        tf.log('  锁定结束（%.0f 秒，共写 %d 次）' % (time.time() - t0, writes))
    elif mode == 'hold':
        # 智能补给：只在食物低于阈值时才补满，平时**完全不干预**。
        # 为什么需要它：`lock` 高频把账面钉回满值，等于把游戏自己的扣费瞬间撤销 ——
        # 建造（一次扣款）尚可，但"先扣再结算"的升级/预留操作可能被搅黄。
        #
        # ★ 关卡结束时自动收工（2026-09-16 新增）：
        #   ① 游戏进程退出  ② UWorld/ULevel 换人（卸载/切换关卡、回大地图）
        #   ③ 连续找不到粮仓（关卡已卸载）
        #   命中任一条 -> 返回 EXIT_LEVEL_ENDED，bat 收到就**自动关窗口**。
        secs = nums[0] if nums else 3600
        pct = nums[1] if len(nums) > 1 else 80
        tf.log('  ★ 智能补给 %d 秒：食物低于 %d%% 才补满，平时不干预'
               % (secs, pct))
        tf.log('    （手动停止=关闭这个窗口；**关卡结束会自动退出并关窗口**）')
        fp0 = level_fingerprint(proc, base)
        if fp0:
            tf.log('    关卡指纹：世界=%s 关卡=%s Actor=%d'
                   % (tf.fmt(fp0[0]), tf.fmt(fp0[1]), fp0[2]))
        else:
            tf.log('    ⚠ 暂时读不到关卡指纹（不影响补给，只是关卡结束可能识别不到）')
        t0 = time.time()
        last, writes, miss_fp, miss_loc = 0.0, 0, 0, 0
        try:
            while time.time() - t0 < secs:
                el = time.time() - t0

                # ---- 关卡是否已经结束 ----
                fp = level_fingerprint(proc, base)
                if fp is None:
                    miss_fp += 1
                    if miss_fp >= 40:                      # ≈2 秒都读不到
                        if not game_alive():
                            tf.log('  ★ 游戏已退出 —— 自动收工')
                        else:
                            tf.log('  ★ 读不到关卡（世界已卸载/正在切换）—— 自动收工')
                        return EXIT_LEVEL_ENDED
                else:
                    miss_fp = 0
                    if fp0 and (fp[0] != fp0[0] or fp[1] != fp0[1]):
                        tf.log('  ★ 关卡已结束/切换（世界或关卡对象已更换）—— 自动收工')
                        return EXIT_LEVEL_ENDED

                # 每轮都核身份（读操作，很便宜）—— 一旦粮仓变了立刻重新定位，
                # 绝不在"已经不是那个对象"的地址上写东西
                good, bad = verify(proc, loc)
                if bad:
                    tf.log('    …粮仓有变动（新建/拆除/升级），重新定位…')
                    if not safe_relocate():
                        miss_loc += 1
                        if miss_loc >= 6:                  # ≈12 秒都找不到
                            tf.log('  ★ 连续找不到粮仓（关卡可能已结束）—— 自动收工')
                            return EXIT_LEVEL_ENDED
                        time.sleep(0.5)
                        continue
                    miss_loc = 0
                cap_now = sum(proc.read_value(a + CAP_OFF) or 0
                              for a in loc['chambers'])
                cur = proc.read_value(loc['ledger_food']) or 0
                if cap_now and cur * 100 < cap_now * pct:
                    try:
                        fill(proc, loc)
                        writes += 1
                        if el - last >= 2:                 # 日志限流：最多 2 秒一条
                            last = el
                            tf.log('    +%.0fs 食物偏低（%d / %d），已补满（累计 %d 次）'
                                   % (el, cur, cap_now, writes))
                    except StaleError as e:
                        tf.log('    ⚠ %s' % e)
                        if not safe_relocate():
                            miss_loc += 1
                            if miss_loc >= 6:
                                tf.log('  ★ 连续找不到粮仓 —— 自动收工')
                                return EXIT_LEVEL_ENDED
                            time.sleep(0.5)
                            continue
                        miss_loc = 0
                elif el - last >= 60:
                    last = el
                    tf.log('    …监视中 %.0f 秒（食物 %s / %s，未干预，已补 %d 次）'
                           % (el, cur, cap_now, writes))
                time.sleep(0.05)                           # 无论走哪个分支都歇一下
        except KeyboardInterrupt:
            pass
        tf.log('  补给结束（%.0f 秒，共补 %d 次）' % (time.time() - t0, writes))
    else:
        tf.log('  用法：report / fill / set <值> / hold [秒] [低于百分之几才补] / lock [秒]')
        tf.log('  说明：hold / lock 会**自动识别关卡结束**（世界换人 / 关卡卸载 / 游戏退出），')
        tf.log('        命中即返回码 %d —— bat 收到就自动关窗口。' % EXIT_LEVEL_ENDED)
        return 3

    dump('写入后')
    proc.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
