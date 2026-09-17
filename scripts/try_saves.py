# -*- coding: utf-8 -*-
"""验证「存档文件名 <-> 游戏里的名字」的对应关系

双击即跑，不启界面、不打包。只读存档，不改任何文件。

三件事：
  1. 修改器里**会**显示哪些档（只显示游戏里的名字）
  2. 哪些档被过滤掉了、分别因为什么
  3. 按命名规律猜关卡数据文件会在哪些档上算错

跑法：
    python scripts/try_saves.py        （或双击 mod/检查存档名.bat）
"""
import os
import sys

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MOD not in sys.path:
    sys.path.insert(0, MOD)

from gui.core import paths, saves                                              # noqa: E402


def naive(save_file):
    """旧的命名规律：X.sav -> XLevelData.sav（用来对照它什么时候会算错）"""
    stem, ext = os.path.splitext(save_file)
    return '%sLevelData%s' % (stem, ext or '.sav')


def why_filtered(save_file):
    """这个文件为什么不出现在修改器的存档下拉里"""
    f = save_file.lower()
    if 'stage' in f:
        return '章节关卡进行中的自动快照'
    if 'newgameplus' in f:
        return 'NG+ 的自动快照'
    if f.startswith('freeplay'):
        return '自由模式 —— 另一个玩法'
    if 'leveldata' in f:
        return '关卡数据文件（不是存档本身）'
    if 'backup' in f:
        return '游戏自己的轮转备份'
    return '其它内部文件'


def main():
    d = paths.saves_dir()
    print('存档目录：%s' % d)

    shown = saves.list_saves()
    every = saves.list_all()

    print('\n' + '=' * 74)
    print('修改器里会显示的存档（%d 个）—— 只显示游戏里的名字' % len(shown))
    print('=' * 74)
    if not shown:
        print('  （一个都没有）')
    for s in shown:
        ld = saves.leveldata_of(s.file)
        print('    %-12s  <-  %-16s  数据在 %s' % (s.label, s.file, ld))

    # 按文件名比，别按对象比 —— list_all 和 list_saves 返回的是不同的
    # SaveInfo 实例，SaveInfo 没定义 __eq__，用 in 判断永远不相等。
    shown_files = {s.file for s in shown}
    hidden = [s for s in every if s.file not in shown_files]
    print('\n' + '=' * 74)
    print('被过滤掉的（%d 个）—— 游戏自己产生或别的模式' % len(hidden))
    print('=' * 74)
    for s in hidden:
        print('    %-16s %-34s %s' % (s.label, s.file, why_filtered(s.file)))

    print('\n' + '=' * 74)
    print('关卡数据文件的定位方式对照')
    print('=' * 74)
    print('    %-18s %-34s %s' % ('游戏里的名字', '实际的数据文件', '按命名规律算会怎样'))
    print('    ' + '-' * 68)
    wrong = []
    for s in shown:
        got = saves.leveldata_of(s.file)
        guess = naive(s.file)
        if got == guess:
            mark = '一致'
        else:
            mark = '** 算成 %s（错）' % guess
            wrong.append((s.file, guess, got))
        print('    %-18s %-34s %s' % (s.label, got, mark))
    if wrong:
        print('\n    -> 这 %d 个档必须用存档自己声明的 LinkedSaveGame，'
              '按命名规律会找错文件、读不到蚁皇浆余额' % len(wrong))

    names = [s.label for s in shown]
    dup = sorted({n for n in names if names.count(n) > 1})
    print('\n显示名重复：%s' % ('无' if not dup else '、'.join(dup)))
    miss = [s.file for s in shown if not s.colony]
    print('读不到名字（会退回显示文件名）：%s' % ('无' if not miss else '、'.join(miss)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
