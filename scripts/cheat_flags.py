# -*- coding: utf-8 -*-
"""关卡内官方作弊开关（InfinateResources / FreeHatch / InstantBuild / InstantDig）

这是游戏开发者留在 UGTileGrid 上的调试开关（SDK 官方字段名），直接绕过
食物/孵化/建造/挖掘的全部判定 —— 比"改食物数字"可靠一万倍
（界面数字只是显示副本，判定不读它，这是 2026-09-16 整晚验证过的死路）。

开关位置（UGTileGrid = vtable RVA 0x3CCDDB0 的对象，取容量最小的 = 玩家）：
    +0x63A InfinateResources  无限资源
    +0x63B FreeHatch          免费孵化
    +0x63C InstantBuild       秒建
    +0x63D InstantDig         秒挖

命令：
  status              只读：当前开关状态 + 资源
  on [秒]             打开并保持（默认 86400 秒；每 0.5s 重申，换关自动跟上）
  off                 全部关闭
退出码：0 正常 ｜ 1 游戏没开 ｜ 2 不在关卡 ｜ 3 定位失败 ｜ 10 关卡结束/切换/退出
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

FLAGS = [(0x63A, 'InfinateResources 无限资源'),
         (0x63B, 'FreeHatch 免费孵化'),
         (0x63C, 'InstantBuild 秒建'),
         (0x63D, 'InstantDig 秒挖')]

EXIT_LEVEL_ENDED = 10


def locate_grid(proc, base, verbose=True):
    level = fc._level_of(proc, base)
    if not level:
        return None
    grid = fp.find_colony(proc, base, fc._actors(proc, level), verbose=verbose)
    if grid is None:
        return None
    return dict(grid=grid, base=base)


def read_flags(proc, grid):
    return {off: proc.read_value(grid + off) for off, _n in FLAGS}


def apply(proc, grid, value):
    """4 个开关是连续的 4 个字节（bool），一次 int32 写齐：0x01010101 = 四个 1"""
    packed = value & 0xFF
    packed |= packed << 8
    packed |= packed << 16
    proc.write_value(grid + FLAGS[0][0], packed, 'int32')


def main():
    args = [x for x in sys.argv[1:]]
    mode = args[0] if args else 'status'

    pids = tf.memscan.find_pids(tf.GAME_EXE)
    if not pids:
        tf.log('  ✗ 游戏没开')
        return 1
    proc = tf.memscan.Process(pids[0])
    base, _ = uw.module_info(pids[0])
    loc = locate_grid(proc, base)
    if loc is None:
        tf.log('  ✗ 现在不在关卡里（大地图/主菜单/加载中）—— 先进入一关')
        proc.close()
        return 2
    grid = loc['grid']

    if mode == 'status':
        tf.log('  网格 %s  资源 %s / %s'
               % (tf.fmt(grid), proc.read_value(grid + 0x4FC),
                  proc.read_value(grid + 0x500)))
        for off, name in FLAGS:
            tf.log('    %-28s = %s' % (name, proc.read_value(grid + off)))
        proc.close()
        return 0

    if mode == 'off':
        apply(proc, grid, 0)
        tf.log('  ✓ 已全部关闭')
        proc.close()
        return 0

    if mode != 'on':
        tf.log('  用法：status | on [秒] | off')
        proc.close()
        return 1

    secs = float(args[1]) if len(args) > 1 else 86400.0
    apply(proc, grid, 1)
    tf.log('  ✓ 4 个官方开关已打开并保持（关窗口=停止；关卡结束自动收工）')
    for _off, name in FLAGS:
        tf.log('    · %s' % name)

    t0, last = time.time(), 0.0
    away = None
    try:
        while time.time() - t0 < secs:
            now = time.time()
            if now - last >= 2.0:
                last = now
                ok = fc.level_fingerprint(proc, base) is not None
                if ok:
                    h = proc.read(grid, 8)
                    ok = h and len(h) >= 8 and uw.u64(h, 0) - base == fp.COLONY_RVA
                if not ok:
                    if away is None:
                        away = now
                        tf.log('    …世界变了，重新定位…')
                    if not fc.game_alive():
                        tf.log('  ★ 游戏已退出 —— 收工')
                        proc.close()
                        return EXIT_LEVEL_ENDED
                    new = locate_grid(proc, base, verbose=False)
                    if new is not None:
                        grid = new['grid']
                        apply(proc, grid, 1)
                        tf.log('      ✓ 已在新关卡重新打开（%s）' % tf.fmt(grid))
                        away = None
                    elif now - away > 45:
                        tf.log('  ★ 不在关卡里 —— 收工')
                        proc.close()
                        return EXIT_LEVEL_ENDED
                    time.sleep(0.5)
                    continue
                away = None
            apply(proc, grid, 1)          # 每 0.5s 重申一次，防游戏改回
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    tf.log('  收工（开关保持打开状态）')
    proc.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
