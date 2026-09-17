# -*- coding: utf-8 -*-
"""关卡内食物 —— 「池子签名 + 指针判据」版（2026-09-17 与用户对齐后的方案）

定位三层，终审不过就拒绝写：
  1. 找池子：按签名反查类 —— 成员的 +0x294(每格上限) 合法，且
     **在用槽的 Σ上限 == 账面容量**。不依赖 TileFunction、不硬编码类指针
     （类指针会随关卡重建；fn==1 的 21 个是地图格子，不是储物池）
  2. 挑槽：**+0x120 的 8 字节指针非空 = 在用槽**（玩家的格子挂着对象，模板槽是空指针）
     中局 AI 建仓后非空数会变多 → 按指针高 32 位（堆区）聚类分组再选；
     仍分不清就报"需差分验证"，绝不猜
  3. 终审：选中组 Σ上限 == 账面容量。对不上 → 只读报告，不写

命令：
  report              只读：池子 / 在用槽 / 账本 对照
  fill                一次性补满（在用槽 + 账面）
  hold [秒] [百分比]   持续补给（默认 86400 秒 / 99%，低于阈值才写）
退出码：0 正常 ｜ 1 游戏没开 ｜ 2 不在关卡 ｜ 3 定位失败/歧义 ｜ 10 关卡结束/切换/退出
"""
import collections
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.abspath(os.path.join(HERE, os.pardir)), 'gui'))

import try_food as tf                                               # noqa: E402
import ue_walk as uw                                                # noqa: E402
import food_chamber as fc                                           # noqa: E402

COLONY_RVA = 0x3CCDDB0
FOOD_OFF, CAP_OFF = 0x4FC, 0x500
SLOT_PTR, SLOT_FOOD, SLOT_CAP = 0x120, 0x290, 0x294

EXIT_LEVEL_ENDED = 10


class Ambiguous(Exception):
    pass


# ---------------------------------------------------------------- 定位

def find_colony(proc, base, actors, verbose=True):
    """玩家殖民地 = vtable RVA 匹配的候选里容量最小的那个"""
    cols = []
    for a in actors:
        h = proc.read(a, 8)
        if not h or len(h) < 8:
            continue
        try:
            if uw.u64(h, 0) - base != COLONY_RVA:
                continue
        except (TypeError, ValueError):
            continue
        f, c = proc.read_value(a + FOOD_OFF), proc.read_value(a + CAP_OFF)
        if f is None or c is None or not (0 <= c <= 100000 and 0 <= f <= 100000):
            continue
        cols.append((a, f, c))
    if not cols:
        return None
    cols.sort(key=lambda t: t[2])
    if verbose:
        for a, f, c in cols:
            tf.log('     殖民地 %s  食物=%-7s 容量=%-7s %s'
                   % (tf.fmt(a), f, c, '← 玩家' if a == cols[0][0] else ''))
    return cols[0][0]


def read_slot(proc, a):
    """读一个候选槽；+0x120 必须按 8 字节读指针（4 字节会读到假值 378 之类）"""
    d = proc.read(a + SLOT_PTR, 0x180)
    if not d or len(d) < 0x180:
        return None
    try:
        return dict(a=a, ptr=uw.u64(d, 0),
                    stock=uw.i32(d, SLOT_FOOD - SLOT_PTR),
                    cap=uw.i32(d, SLOT_CAP - SLOT_PTR))
    except (TypeError, ValueError):
        return None


def scan_pools(proc, actors):
    """把值域合法的候选按类分组"""
    by = collections.defaultdict(list)
    for a in actors:
        s = read_slot(proc, a)
        if not s:
            continue
        if not (1 <= s['cap'] <= 1000 and 0 <= s['stock'] <= s['cap']):
            continue
        h = proc.read(a, 0x20)
        if not h or len(h) < 0x20:
            continue
        try:
            s['cls'] = uw.u64(h, 0x10)
        except (TypeError, ValueError):
            continue
        by[s['cls']].append(s)
    return by


def _pick_active(members, cap_total, verbose=False):
    """在一个类里挑"玩家的槽"：指针非空 → 堆区聚类 → Σ上限==容量 终审"""
    act = [m for m in members if m['ptr']]
    if not act:
        return None
    if sum(m['cap'] for m in act) == cap_total:
        return act
    # 中局：AI 的槽也有指针了 → 按指针高 32 位（堆区）分组，找 Σ上限==容量的那组
    regions = collections.defaultdict(list)
    for m in act:
        regions[m['ptr'] >> 32].append(m)
    hits = [g for g in regions.values() if sum(m['cap'] for m in g) == cap_total]
    if len(hits) == 1:
        return hits[0]
    if verbose:
        tf.log('      堆区分组：%s'
               % {hex(k): sum(m['cap'] for m in g) for k, g in regions.items()})
    return None


def locate(proc, base, level, verbose=True):
    """返回 dict(colony, ledger_food, ledger_cap, cls, slots)；失败返回 None"""
    actors = fc._actors(proc, level)
    if verbose:
        tf.log('  Actor=%d' % len(actors))
    mine = find_colony(proc, base, actors, verbose=verbose)
    if mine is None:
        tf.log('  ✗ 没找到玩家殖民地')
        return None
    cap_total = proc.read_value(mine + CAP_OFF)
    food = proc.read_value(mine + FOOD_OFF)

    by = scan_pools(proc, actors)
    matches = []
    for cls, members in by.items():
        act = _pick_active(members, cap_total, verbose=False)
        if act:
            matches.append(dict(cls=cls, slots=sorted(act, key=lambda m: m['a']),
                                total=len(members)))
    if not matches:
        if verbose:
            tf.log('  ✗ 没有类能满足「在用槽 Σ上限 == 容量 %s」' % cap_total)
            top = sorted(by.items(),
                         key=lambda kv: abs(sum(m['cap'] for m in kv[1] if m['ptr'])
                                            - cap_total))[:3]
            for cls, members in top:
                act = [m for m in members if m['ptr']]
                tf.log('      候选 %s：在用 %d/%d，Σ上限=%d（差 %+d）'
                       % (tf.fmt(cls), len(act), len(members),
                          sum(m['cap'] for m in act),
                          sum(m['cap'] for m in act) - cap_total))
        return None
    if len(matches) > 1:
        tf.log('  ✗ 有 %d 个类同时满足签名，拒绝猜：%s'
               % (len(matches), [tf.fmt(m['cls']) for m in matches]))
        return None
    m = matches[0]
    if verbose:
        tf.log('  ✓ 池子 class %s（成员 %d）：在用 %d 格，Σ上限=%d == 容量 ✓'
               % (tf.fmt(m['cls']), m['total'], len(m['slots']),
                  sum(s['cap'] for s in m['slots'])))
    m.update(colony=mine, ledger_food=food, ledger_cap=cap_total, base=base, level=level)
    return m


# ---------------------------------------------------------------- 写入安全

def verify_slot(proc, loc, s):
    """写前身份核对：类指针没变 + 这个槽挂的还是原来那个对象 + 上限没变"""
    h = proc.read(s['a'], 0x20)
    if not h or len(h) < 0x20 or uw.u64(h, 0x10) != loc['cls']:
        return False
    d = proc.read(s['a'] + SLOT_PTR, 0x180)
    if not d or len(d) < 0x180:
        return False
    try:
        return (uw.u64(d, 0) == s['ptr'] and s['ptr']
                and uw.i32(d, SLOT_CAP - SLOT_PTR) == s['cap'])
    except (TypeError, ValueError):
        return False


def verify_colony(proc, loc):
    h = proc.read(loc['colony'], 8)
    return bool(h and len(h) >= 8 and uw.u64(h, 0) - loc['base'] == COLONY_RVA)


def fill(proc, loc, threshold=1.0):
    """在用槽补到各自上限；账面补到容量。返回写入次数"""
    cap_total = proc.read_value(loc['colony'] + CAP_OFF)
    if not cap_total or not verify_colony(proc, loc):
        raise StaleError('殖民地身份不符')
    n = 0
    for s in loc['slots']:
        if not verify_slot(proc, loc, s):
            raise StaleError('槽 %s 身份不符' % tf.fmt(s['a']))
        cur = proc.read_value(s['a'] + SLOT_FOOD)
        if cur is None or cur < s['cap'] * threshold:
            proc.write_value(s['a'] + SLOT_FOOD, s['cap'], 'int32')
            n += 1
    cur = proc.read_value(loc['colony'] + FOOD_OFF)
    if cur is None or cur < cap_total * threshold:
        proc.write_value(loc['colony'] + FOOD_OFF, int(cap_total), 'int32')
        n += 1
    return n


class StaleError(Exception):
    pass


# ---------------------------------------------------------------- 主流程

def relocate(proc, base, verbose=True):
    level = fc._level_of(proc, base)
    if not level:
        return None
    return locate(proc, base, level, verbose=verbose)


def main():
    args = [x for x in sys.argv[1:] if not x.startswith('--')]
    mode = args[0] if args else 'report'
    nums = []
    for x in args[1:]:
        try:
            nums.append(float(x))
        except ValueError:
            pass

    pids = tf.memscan.find_pids(tf.GAME_EXE)
    if not pids:
        tf.log('  ✗ 游戏没开')
        return 1
    proc = tf.memscan.Process(pids[0])
    base, _ = uw.module_info(pids[0])
    tf.log('  ✓ 已连上游戏  PID=%d' % pids[0])
    level = fc._level_of(proc, base)
    if not level:
        tf.log('  ✗ 现在不在关卡里（大地图/主菜单/加载中）')
        proc.close()
        return 2

    loc = locate(proc, base, level)
    if loc is None:
        proc.close()
        return 3

    if mode == 'report':
        tf.log('')
        tf.log('  === 只读对照 ===')
        tf.log('  账面：食物 %s / 容量 %s' % (loc['ledger_food'], loc['ledger_cap']))
        for s in loc['slots']:
            tf.log('    槽 %s  存量=%-4s 上限=%-4s 指针=%s'
                   % (tf.fmt(s['a']), s['stock'], s['cap'], tf.fmt(s['ptr'])))
        tot = sum(s['stock'] for s in loc['slots'])
        tf.log('  在用 %d 格：Σ存量=%d  Σ上限=%d（账面容量 %s）'
               % (len(loc['slots']), tot, sum(s['cap'] for s in loc['slots']),
                  loc['ledger_cap']))
        tf.log('  ⚠ Σ存量与账面食物不同步是已知现象，别拿它判对错；对错以「能否建造」为准')
        proc.close()
        return 0

    if mode == 'fill':
        try:
            n = fill(proc, loc)
            tf.log('  ✓ 已补满（写入 %d 处）' % n)
        except StaleError as e:
            tf.log('  ✗ 拒绝写入：%s（身份核对失败）' % e)
            proc.close()
            return 3
        proc.close()
        return 0

    if mode != 'hold':
        tf.log('  用法：report | fill | hold [秒] [百分比]')
        proc.close()
        return 1

    secs = nums[0] if nums else 86400.0
    pct = min(max((nums[1] if len(nums) > 1 else 99.0) / 100.0, 0.1), 1.0)
    tf.log('')
    tf.log('  ★ 开始补给：低于 %d%% 才写，每 0.05s 检查；关窗口=停止，关卡结束自动收工'
           % (pct * 100))
    fp0 = fc.level_fingerprint(proc, base)
    t0, last, said, writes = time.time(), 0.0, 0.0, 0
    away = None
    try:
        while time.time() - t0 < secs:
            now = time.time()
            if now - last >= 2.0:
                last = now
                fp = fc.level_fingerprint(proc, base)
                changed = fp is None or (fp0 and (fp[0] != fp0[0] or fp[1] != fp0[1]))
                if changed or not verify_colony(proc, loc) or \
                        not all(verify_slot(proc, loc, s) for s in loc['slots']):
                    if away is None:
                        away = now
                        tf.log('    …世界/对象变了，重新定位…')
                    if not fc.game_alive():
                        tf.log('  ★ 游戏已退出 —— 收工')
                        proc.close()
                        return EXIT_LEVEL_ENDED
                    new = relocate(proc, base, verbose=False)
                    if new is not None:
                        loc, fp0 = new, (fp or fp0)
                        tf.log('      ✓ 已跟上：%s（食物 %s / %s）'
                               % (tf.fmt(loc['colony']),
                                  proc.read_value(loc['colony'] + FOOD_OFF),
                                  proc.read_value(loc['colony'] + CAP_OFF)))
                        away = None
                    elif now - away > 45:
                        tf.log('  ★ 不在关卡里 —— 自动收工')
                        proc.close()
                        return EXIT_LEVEL_ENDED
                    time.sleep(0.5)
                    continue
                away = None

            cap_total = proc.read_value(loc['colony'] + CAP_OFF)
            if cap_total and 1 <= cap_total <= 100000:
                cur = proc.read_value(loc['colony'] + FOOD_OFF)
                if cur is None or cur < cap_total * pct:
                    try:
                        writes += fill(proc, loc, threshold=pct)
                    except StaleError:
                        time.sleep(0.2)
                        continue
            el = now - t0
            if el - said >= 20:
                said = el
                tf.log('    …补给中 %.0f 秒：食物 %s / %s（累计写入 %d 处）'
                       % (el, proc.read_value(loc['colony'] + FOOD_OFF), cap_total, writes))
            time.sleep(0.05)
    except KeyboardInterrupt:
        tf.log('  已手动停止')
    proc.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
