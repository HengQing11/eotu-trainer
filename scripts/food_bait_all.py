# -*- coding: utf-8 -*-
"""全局诱饵差分：让食物真实增加 N，找出全部对象里变化量 == ±N 的字段

原理：殖民地的 +0x86C（累计采集资源）会随采集 +N，拿它当参照；
     对全部 8814 个 Actor 的前 0x1400 字节做前后差分，报告变化量 == ±N 的字段。
     GameState 本身也是关卡 Actor，所以会被覆盖到。
纯只读。用法：python food_bait_all.py [秒=300]
"""
import collections
import sys
import time

sys.path.insert(0, r'D:/aiwork/WorkBuddy/2026-09-13-11-21-03/mod/gui')
sys.path.insert(0, r'D:/aiwork/WorkBuddy/2026-09-13-11-21-03/mod/scripts')
from core import live
import try_food as tf, ue_walk as uw, food_chamber as fc, food_pool as fp

SPAN = 0x1400
GAIN_OFF = 0x86C          # 殖民地「累计采集资源」
SKIP_OFFS = {0x4FC, 0x500, 0xf7c}


def snapshot(proc, actors):
    snap = {}
    for a in actors:
        d = proc.read(a, SPAN)
        if d and len(d) >= SPAN:
            snap[a] = d
    return snap


def diff(snap1, snap2, n):
    hits = []
    for a, d1 in snap1.items():
        d2 = snap2.get(a)
        if not d2:
            continue
        h = proc = None
        for off in range(0, SPAN - 4, 4):
            if off in SKIP_OFFS:
                continue
            try:
                o, v = uw.i32(d1, off), uw.i32(d2, off)
            except (TypeError, ValueError):
                continue
            if o != v and (v - o == n or o - v == n):
                hits.append((a, off, o, v))
    return hits


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 300.0
    proc = live.game_proc()
    pids = tf.memscan.find_pids(tf.GAME_EXE)
    base, _ = uw.module_info(pids[0])
    level = fc._level_of(proc, base)
    if not level:
        print('  不在关卡里')
        return 2
    colony = fp.find_colony(proc, base, fc._actors(proc, level), verbose=False)
    if colony is None:
        print('  没找到殖民地')
        return 3
    print('  参照 = 殖民地累计采集 +0x86c；对全部 Actor 差分（纯只读 %d 秒）' % secs, flush=True)

    trials = []
    t0 = time.time()
    actors = fc._actors(proc, level)
    snap = snapshot(proc, actors)
    ref = proc.read_value(colony + GAIN_OFF)
    print('  基线：累计采集=%s，Actor=%d' % (ref, len(snap)), flush=True)
    trial = 0
    while time.time() - t0 < secs and trial < 3:
        time.sleep(1.0)
        cur = proc.read_value(colony + GAIN_OFF)
        if cur is None or ref is None or cur - ref < 1:
            continue
        n = cur - ref
        trial += 1
        print('  ★ 第 %d 次真实采集：+%d（累计采集 %s→%s），差分中…' % (trial, n, ref, cur), flush=True)
        snap2 = snapshot(proc, actors)
        hits = diff(snap, snap2, n)
        print('     变化量 == ±%d 的字段：%d 个' % (n, len(hits)), flush=True)
        byc = collections.Counter()
        for a, off, o, v in hits[:200]:
            h = proc.read(a, 0x20)
            cls = tf.fmt(uw.u64(h, 0x10)) if h and len(h) >= 0x20 else '?'
            byc[(cls, off)] += 1
            print('       %s  +%-6x  %s → %s' % (tf.fmt(a), off, o, v), flush=True)
        print('     按 (类,偏移) 聚合：%s' % dict(byc), flush=True)
        trials.append(hits)
        snap, ref = snap2, cur
    print()
    print('  共 %d 次采集，%d 轮差分' % (trial, len(trials)))
    if trial >= 2:
        sets = [set((a, off) for a, off, _o, _v in h) for h in trials]
        common = set.intersection(*sets)
        print('  ★ 两次都命中（=真身候选）：%d 个' % len(common))
        for a, off in list(common)[:20]:
            print('     %s  +%-6x' % (tf.fmt(a), off))
    proc.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
