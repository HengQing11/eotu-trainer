# -*- coding: utf-8 -*-
"""盯"某个值"的全部出现位置，等它变化 -> 找出"真身"字段

用法：python scripts/field_hunt.py <当前值> [秒数]
例：  python scripts/field_hunt.py 70 240
"""
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.abspath(os.path.join(HERE, os.pardir)), 'gui'))

import try_food as tf                                               # noqa: E402
import ue_walk as uw                                                # noqa: E402
import food_chamber as fc                                           # noqa: E402


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 70
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 240.0
    tf._LOG = open(tf.LOG_PATH, 'a', encoding='utf-8')

    proc = tf.connect()
    pids = tf.memscan.find_pids(tf.GAME_EXE)
    base, size = uw.module_info(pids[0])
    level = fc._level_of(proc, base)
    actors = fc._actors(proc, level)
    tf.log('  关卡 Actor = %d   盯着「值 == %d」的字段' % (len(actors), target))

    SPAN = 0x600
    snap = {}
    hits = 0
    for a in actors:
        d = proc.read(a, SPAN)
        if not d:
            continue
        snap[a] = d
        for o in range(0x40, len(d) - 3, 4):
            if struct.unpack_from('<i', d, o)[0] == target:
                hits += 1
    tf.log('  首轮快照：%d 个对象，其中「== %d」的字段共 %d 处' % (len(snap), target, hits))
    tf.log('  现在请在游戏里让这个数变一下（花掉/采集）…最多等 %.0f 秒' % secs)

    t0 = time.time()
    while time.time() - t0 < secs:
        time.sleep(1.5)
        changed = {}
        for a, old in snap.items():
            new = proc.read(a, SPAN)
            if not new or len(new) != len(old):
                continue
            for o in range(0x40, len(old) - 3, 4):
                ov = struct.unpack_from('<i', old, o)[0]
                nv = struct.unpack_from('<i', new, o)[0]
                if ov != nv:
                    changed.setdefault(a, []).append((o, ov, nv))
        if changed:
            tf.log('')
            tf.log('  ★ 捕捉到变化（%.1fs）：' % (time.time() - t0))
            for a, lst in list(changed.items())[:12]:
                h = proc.read(a, 0x20)
                cls = uw.u64(h, 0x10) if h else 0
                tf.log('     对象 %s  class=%s' % (tf.fmt(a), tf.fmt(cls)))
                for o, ov, nv in lst[:8]:
                    mark = '   ← 原来是 %d' % target if ov == target else ''
                    tf.log('        +%-6s  %-10d → %-10d%s' % (hex(o), ov, nv, mark))
            tf.log('')
            return 0
    tf.log('  （%.0f 秒内没有捕捉到变化）' % secs)
    return 1


if __name__ == '__main__':
    sys.exit(main())
