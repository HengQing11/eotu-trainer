# -*- coding: utf-8 -*-
"""蚁皇浆一键补满 —— 把存档里的 RoyalJelly 余额直接改到指定值

为什么需要它
------------
游戏里「属性微调（IP）」的价格是等比滚动的：同一个小项每多买 1 点，单价 x1.15。
  加到第 85 点  -> 累计花费约 96 万
  加到第 120 点 -> 累计花费约 2 亿
  加到第 140 点 -> 累计花费约 21 亿（= int32 的物理上限，再往上存不下）
换句话说：**任何有限的余额都会「一会儿就没了」**，随时补货才是正解。

用法（推荐直接双击 mod\\补满蚁皇浆.bat）
----------------------------------------
  python refill_jelly.py              补满到 20 亿（默认）
  python refill_jelly.py --check      只查看当前余额，不改任何文件
  python refill_jelly.py --value N    指定目标值
  python refill_jelly.py --force      游戏运行中也强行改（不推荐）

安全措施
--------
* 游戏在运行 -> 拒绝执行（游戏退出存盘时会把你改的覆盖掉，白改）
  ⚠️ **这是最常见的「工具失效」原因**：游戏只要开着（哪怕停在菜单/后台），
  它就一定会拒绝。脚本会明确打印「已停止：游戏正在运行」。今天一次都没写成功，
  先看这里。--check 不受此限（只读）。
* 改之前自动备份到 mod/backup/saves/（自动保留最近 5 份）
* RoyalJelly 是 IntProperty，固定 4 字节，原地等长覆盖，文件大小不变
* 会同时补 **所有** *LevelData.sav（Colony1 / Colony2 / Freeplay2 …），
  所以不存在"补了别的档、你在玩的这个没补"的情况；脚本还会标出**当前活跃档**
  （读 LevelSetup.sav 的 SaveGameToLoad），免得看花眼
"""
import os
import re
import shutil
import struct
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

from patch_sav import find_int  # noqa: E402

FIELD = 'RoyalJelly'
DEFAULT_VALUE = 2_000_000_000
MAX_INT32 = 2_147_483_647
BAK_DIR = os.path.join(MOD, 'backup', 'saves')
KEEP_BAK = 5


def out(msg=''):
    sys.stdout.write(msg + '\n')


def saves_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    return os.path.join(base, 'EotU', 'Saved', 'SaveGames')


def game_running():
    """任务栏里有没有 EotU。用字节匹配，避免中文系统 GBK 解码炸掉。"""
    try:
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq EotU-Win64-Shipping.exe'],
                           capture_output=True, timeout=15)
        return b'EotU-Win64-Shipping' in (r.stdout or b'')
    except Exception:
        return None            # 判断不了，交给调用方决定


def _gvas_str(data, name):
    """从 GVAS 里取一个 StrProperty 的字符串值（**只用于显示，不参与写盘**）

    gui/core/gvas.py 只认定长类型（Bool/Int/Float），字符串得自己取。布局是
    名字FString + 类型FString + Size(4) + ArrayIndex(4) + 值FString，这里取巧：
    从名字往后找第一段可打印 ASCII，跳过 'StrProperty'，取到的就是值。
    即使取歪也只是打印难看，不会影响任何写入。
    """
    key = name.encode('latin1') + b'\x00'
    i = data.find(key)
    if i < 0:
        return None
    tail = data[i + len(key): i + len(key) + 400]
    for m in re.finditer(rb'[\x20-\x7e]{3,}', tail):
        s = m.group().decode('latin1')
        if s in ('StrProperty', 'None'):
            continue
        return s
    return None


def active_level_data():
    """游戏当前在玩哪个档 —— 读 LevelSetup.sav 的 SaveGameToLoad（只读报告用）

    LevelSetup.sav 是游戏自己写的"下一关要载入什么"：
      LevelToLoad（关卡路径） / SaveGameToLoad（Colony2LevelData） / FormicSaveToLoad（Colony2）
    """
    p = os.path.join(saves_dir(), 'LevelSetup.sav')
    if not os.path.isfile(p):
        return None, None
    try:
        d = open(p, 'rb').read()
    except OSError:
        return None, None
    return _gvas_str(d, 'SaveGameToLoad'), _gvas_str(d, 'LevelToLoad')


def jelly_of(path):
    """该存档里 RoyalJelly 的所有实例值；读不到返回 []"""
    try:
        return [v for _s, _o, v in find_int(open(path, 'rb').read(), FIELD)]
    except OSError:
        return []


def targets():
    """要处理的存档：*LevelData.sav，排除轮转备份/冻结快照/旧关卡快照"""
    d = saves_dir()
    res = []
    if not os.path.isdir(d):
        return res
    for n in sorted(os.listdir(d)):
        low = n.lower()
        if not low.endswith('.sav') or 'leveldata' not in low:
            continue
        if any(k in low for k in ('backup', 'newgameplus', 'stage')):
            continue
        res.append(os.path.join(d, n))
    return res


def backup(path):
    os.makedirs(BAK_DIR, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    dst = os.path.join(BAK_DIR, '%s.bak-%s' % (os.path.basename(path), stamp))
    shutil.copy2(path, dst)
    olds = sorted(f for f in os.listdir(BAK_DIR)
                  if f.startswith(os.path.basename(path) + '.bak-'))
    for f in olds[:-KEEP_BAK]:
        try:
            os.remove(os.path.join(BAK_DIR, f))
        except OSError:
            pass
    return os.path.basename(dst)


def fmt(v):
    return '{:,}'.format(v)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    a = sys.argv[1:]
    dry = '--check' in a
    force = '--force' in a
    value = DEFAULT_VALUE
    if '--value' in a:
        try:
            value = int(a[a.index('--value') + 1])
        except (IndexError, ValueError):
            out('  [!] --value 后面要跟一个整数'); return 1
    if not (0 <= value <= MAX_INT32):
        out('  [!] 目标值必须在 0 ~ %s 之间（int32 上限）' % fmt(MAX_INT32)); return 1

    out('=' * 64)
    out('  蚁皇浆补满' + ('   [只检查，不改文件]' if dry else ''))
    out('=' * 64)
    out()

    sdir = saves_dir()
    if not os.path.isdir(sdir):
        out('  [!] 找不到存档目录：%s' % sdir); return 1
    out('  存档目录：%s' % sdir)
    if not dry:
        out('  目标数值：%s' % fmt(value))
    out()

    # ---- 游戏当前在玩哪个档（只读，报告用；这是本次困惑的根源，务必打出来）----
    act, lvl = active_level_data()
    if act:
        nm = os.path.basename(lvl) if lvl else ''
        out('  当前活跃档：%s%s' % (act, ('   关卡：%s' % nm) if nm else ''))
        pa = os.path.join(sdir, act + '.sav')
        if os.path.isfile(pa):
            vals = jelly_of(pa)
            out('      它现在的蚁皇浆 = %s'
                % ('、'.join(fmt(v) for v in vals) if vals else '（没有该字段）'))
    else:
        out('  当前活跃档：（读不到 LevelSetup.sav，按整个存档目录处理）')
    out()

    running = game_running()
    if running and not dry and not force:
        out('  ── 已停止：游戏正在运行 ──')
        out()
        out('  存档只在「游戏存盘那一刻」写盘。游戏开着的时候改，')
        out('  退出时会被它自己的数据覆盖，等于白改。')
        out()
        out('  请先完全退出游戏（确认任务栏里没有 EotU），再双击本脚本。')
        out('  只是想看数值：双击本脚本时带上 --check（不受此限制）。')
        out()
        return 2
    if running is None and not dry:
        out('  [注意] 没能确认游戏是否在运行，继续执行。如果游戏开着，改动可能无效。')
        out()

    files = targets()
    if not files:
        out('  [!] 没有找到可处理的存档（*LevelData.sav）'); return 1

    total = 0
    for path in files:
        name = os.path.basename(path)
        data = bytearray(open(path, 'rb').read())
        hits = find_int(data, FIELD)
        mark = '      ★ 你正在玩的档' if act and name.startswith(act) else ''
        out('  %s   (%.1f MB)%s' % (name, len(data) / 1048576.0, mark))
        if not hits:
            out('      ── 没有 %s 字段，跳过' % FIELD)
            out()
            continue
        if dry:
            for i, (_s, voff, old) in enumerate(hits, 1):
                out('      [%d] 值@%-9d = %s' % (i, voff, fmt(old)))
            out()
            continue

        bak = backup(path)
        for i, (_s, voff, old) in enumerate(hits, 1):
            struct.pack_into('<i', data, voff, value)
            out('      [%d] 值@%-9d  %s  ->  %s' % (i, voff, fmt(old), fmt(value)))
            total += 1
        open(path, 'wb').write(bytes(data))

        # 写回后验证
        again = find_int(open(path, 'rb').read(), FIELD)
        ok = all(v == value for _s, _v, v in again) and len(again) == len(hits)
        out('      已备份 -> backup\\saves\\%s' % bak)
        out('      校验：%s' % ('通过（%d 处全部为 %s）' % (len(again), fmt(value)) if ok
                                else '失败！请把备份还原'))
        out()

    if dry:
        out('  以上为当前余额。要补满，去掉 --check 再跑一次。')
    else:
        out('  完成：共改写 %d 处。%s现在可以启动游戏了。'
            % (total, ('你正在玩的 %s 已包含在内。' % act) if act else ''))
    out()
    return 0


if __name__ == '__main__':
    sys.exit(main())
