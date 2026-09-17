# -*- coding: utf-8 -*-
"""零写入观察器：全程只读记录食物系统的四条线，看清游戏经济链路

记录：账面(+0x4FC) ｜ 在用槽Σ存量 ｜ 累计采集(+0x86c) ｜ +0xf7c ｜ 在用槽个数
每 2 秒重定位一次（重开局/换关自动跟上）。任何数值都不写。
用法：python observe_food.py [秒=600]
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.abspath(os.path.join(HERE, os.pardir)), 'gui'))

import try_food as tf                                               # noqa: E402
import ue_walk as uw                                                # noqa: E402
import food_chamber as fc                                           # noqa: E402
import food_pool as fp                                              # noqa: E402


def state(proc, loc):
    led = proc.read_value(loc['colony'] + fp.FOOD_OFF)
    gain = proc.read_value(loc['colony'] + 0x86C)
    f7c = proc.read_value(loc['colony'] + 0xf7c)
    stock, n = 0, 0
    for s in loc['slots']:
        v = proc.read_value(s['a'] + fp.SLOT_FOOD)
        if v is not None:
            stock += v
            n += 1
    return led, gain, f7c, stock, n


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 600.0
    pids = tf.memscan.find_pids(tf.GAME_EXE)
    if not pids:
        print('  游戏没开')
        return 1
    proc = tf.memscan.Process(pids[0])
    base, _ = uw.module_info(pids[0])
    print('  零写入观察 %d 秒（只读）—— 正常玩：采集 → 试建造' % secs, flush=True)
    t0, last, loc = time.time(), None, None
    while time.time() - t0 < secs:
        level = fc._level_of(proc, base)
        new_loc = None
        if level:
            try:
                new_loc = fp.locate(proc, base, level, verbose=False)
            except Exception:                                        # noqa: BLE001
                new_loc = None
        if new_loc is None:
            if loc is not None:
                print('[%6.1fs] （读不到关卡/殖民地 —— 加载中或回大地图）'
                      % (time.time() - t0), flush=True)
                loc = None
            time.sleep(2)
            continue
        if loc is None or new_loc['colony'] != loc['colony']:
            print('[%6.1fs] ★ 新殖民地：%s（账面 %s / 容量 %s）'
                  % (time.time() - t0, tf.fmt(new_loc['colony']),
                     new_loc['ledger_food'], new_loc['ledger_cap']), flush=True)
        loc = new_loc
        st = state(proc, loc)
        if st != last:
            print('[%6.1fs] 账面=%-5s 累计采集=%-6s +f7c=%-4s 在用%d格 Σ存量=%d'
                  % ((time.time() - t0,) + st), flush=True)
            last = st
        time.sleep(1.0)
    print('  观察结束', flush=True)
    proc.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
