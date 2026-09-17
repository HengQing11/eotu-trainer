# -*- coding: utf-8 -*-
"""只读猎捕「真实食物计数器」：盯殖民地对象的全部字段，找随食物真实变化而动的那个

用法：python food_true_hunt.py [秒=150]
期间在游戏里让食物**真实**变化（采蜜露 / 消耗），结束打印候选偏移。
纯只读，不写任何内存。
"""
import struct
import sys
import time

sys.path.insert(0, r'D:/aiwork/WorkBuddy/2026-09-13-11-21-03/mod/gui')
sys.path.insert(0, r'D:/aiwork/WorkBuddy/2026-09-13-11-21-03/mod/scripts')
from core import live
import try_food as tf, ue_walk as uw, food_chamber as fc
import food_pool as fp

SPAN = 0x10000
KNOWN_WRITES = {0x4FC, 0x500}          # 我们自己写过的，排除


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 150.0
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
    print('  只读监视 %s（%d 秒）—— 期间去游戏里让食物真实变化（采蜜露/消耗）'
          % (tf.fmt(colony), secs), flush=True)

    snap = proc.read(colony, SPAN)
    if not snap:
        print('  读取失败')
        return 3
    ihist, fhist = {}, {}
    t0 = time.time()
    while time.time() - t0 < secs:
        time.sleep(0.4)
        new = proc.read(colony, SPAN)
        if not new or len(new) < SPAN:
            continue
        n = min(len(snap), len(new)) - 4
        for off in range(0, n, 4):
            if off in KNOWN_WRITES:
                continue
            o, v = uw.i32(snap, off), uw.i32(new, off)
            if o != v and abs(v - o) <= 10:
                ihist.setdefault(off, []).append((o, v))
            fo = struct.unpack_from('<f', snap, off)[0]
            fv = struct.unpack_from('<f', new, off)[0]
            if fo != fv and 0.0001 < abs(fv - fo) <= 50:
                fhist.setdefault(off, []).append((round(fo, 3), round(fv, 3)))
        snap = new

    def col(old, new):
        return '→'.join('%s' % n for _o, n in ev[:6])

    print()
    print('=== 整数候选（变化量 ≤10，按出现次数排序）===')
    for off, ev in sorted(ihist.items(), key=lambda kv: -len(kv[1])):
        print('   +%-6x  %2d 次  变化: %s' % (off, len(ev), ' '.join('%s→%s' % e for e in ev[:6])))
    print()
    print('=== 浮点候选（|Δ|≤50）===')
    for off, ev in sorted(fhist.items(), key=lambda kv: -len(kv[1]))[:25]:
        print('   +%-6x  %2d 次  变化: %s' % (off, len(ev), ' '.join('%s→%s' % e for e in ev[:5])))
    if not ihist and not fhist:
        print('   （没有捕获到变化 —— 期间食物没真实变化？）')
    proc.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
