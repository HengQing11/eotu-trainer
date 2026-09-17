# -*- coding: utf-8 -*-
"""蚁皇浆加点回退 —— 把加过的点清零，回到没加过点的状态

为什么需要它
------------
游戏里加点（属性微调 IP）**没有洗点功能**，加错了只能认。
更麻烦的是价格等比滚动 —— 同一个小项每多买 1 点，单价 x1.15，每个项独立算：

    加到  20 点  ->  累计约 102 浆
    加到  30 点  ->  累计约 434 浆
    加到  85 点  ->  累计约 96 万
    加到 120 点  ->  累计约 2 亿
    加到 140 点  ->  累计约 21 亿（int32 的物理上限，再往上存档存不下）

所以一旦点歪，代价是几十万浆，而且玩家自己撤销不了。

这个脚本直接改存档，**只做一件事：把加点字段清零**。
  * IntProperty 固定 4 字节，原地等长覆盖，文件大小一个字节不变
  * **只动 Colony1.sav 这一个文件，完全不碰蚁皇浆存档**（少动一个文件 = 少一分风险）
  * 清零后游戏会从第 1 点的价格重新算，想加回来随时再加

已投入的蚁皇浆不会退回来 —— 想让浆回来，另外双击 `补满蚁皇浆.bat`
（那个脚本专门管浆，会把余额补到 20 亿）。两个工具各管一件事，互不干扰。

用法（推荐直接双击 mod\\回退加点.bat）
--------------------------------------
  python revert_addons.py --check              只看现状，不改任何文件
  python revert_addons.py                      交互式：列出清单，输入编号选要清的
  python revert_addons.py --all                清空全部加点
  python revert_addons.py --only 切叶蚁中工     只清这一个单位（可写多次）
  python revert_addons.py --all --adapt        连适应性开关一起清
  python revert_addons.py --file Colony1Stage1.sav   指定处理哪个存档
  python revert_addons.py --list-backups       列出可还原的备份
  python revert_addons.py --restore            从备份整档还原（交互选择）

安全措施
--------
* 游戏在运行 -> 拒绝执行（存档只在存盘那一刻落盘，开着游戏改会被覆盖）
* 改之前自动备份到 mod/backup/saves/（同类文件保留最近 8 份）
* 只改 .sav 里 4 字节的数值，不增删任何字段；写完立刻读回来校验
* 校验不过会明确告诉你还原哪个备份文件
"""
import os
import shutil
import struct
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.abspath(os.path.join(HERE, '..'))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from patch_sav import find_int, find_bool                 # noqa: E402
import jelly_calc as JC                                   # noqa: E402
from field_lib import all_fields                          # noqa: E402

BAK_DIR = os.path.join(MOD, 'backup', 'saves')
KEEP_BAK = 8
DEFAULT_SAVE = 'Colony1.sav'     # LevelSetup.sav 指向的当前蚁巢


def out(msg=''):
    sys.stdout.write(msg + '\n')


# --------------------------------------------------------------- 价格 / 花费
def cost_of(n):
    """买 n 点要花多少浆

    首点 1 浆，之后每点 x1.15（等比滚动）。累计 = (1.15^n - 1) / 0.15。
    用你存档实测校验过：85 点算出 962,104，游戏实际扣了 962,177，差 0.008%。
    （只用来显示"当初投入多少"，本脚本不做任何退款计算）
    """
    if n <= 0:
        return 0
    return int(round((1.15 ** n - 1) / 0.15))


def fmt(v):
    return '{:,}'.format(int(v))


# ------------------------------------------------------------------- 环境检查
def saves_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    return os.path.join(base, 'EotU', 'Saved', 'SaveGames')


def game_running():
    """任务栏里有没有 EotU。字节匹配，避免中文系统 GBK 解码炸掉。

    tasklist 走绝对路径，不吃 PATH（这个脚本可能在 PATH 被改过的环境里被调用）。
    -> True / False / None（判断不了）
    """
    import shutil as _sh
    cands = [os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'tasklist.exe')]
    w = _sh.which('tasklist')
    if w:
        cands.append(w)
    for exe in cands:
        if not os.path.isfile(exe):
            continue
        try:
            r = subprocess.run([exe, '/FI', 'IMAGENAME eq EotU-Win64-Shipping.exe'],
                               capture_output=True, timeout=15)
            return b'EotU-Win64-Shipping' in (r.stdout or b'')
        except Exception:
            continue
    return None            # 判断不了，交给调用方决定


def backup(path):
    os.makedirs(BAK_DIR, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    dst = os.path.join(BAK_DIR, '%s.bak-%s' % (os.path.basename(path), stamp))
    shutil.copy2(path, dst)
    base = os.path.basename(path) + '.bak-'
    olds = sorted(f for f in os.listdir(BAK_DIR) if f.startswith(base))
    for f in olds[:-KEEP_BAK]:
        try:
            os.remove(os.path.join(BAK_DIR, f))
        except OSError:
            pass
    return os.path.basename(dst)


# -------------------------------------------------------------------- 加点清单
def scan(path):
    """-> ([(Field, 点数)], {int 字段: 值}, {为 True 的 bool 字段})"""
    ints, bools = JC.read_save(path)
    return JC.points(ints), ints, bools


def select_by_keyword(items, keywords):
    """按关键字挑加点项（匹配中文名 / 英文名 / 内部字段名 / 项目名）"""
    hit, miss = [], []
    seen = set()
    for kw in keywords:
        k = kw.lower()
        got = [it for it in items
               if k in it[0].unit_zh.lower() or k in it[0].unit_en.lower()
               or k in it[0].name.lower() or k in it[0].item.lower()]
        if not got:
            miss.append(kw)
            continue
        for g in got:
            if g[0].name not in seen:
                seen.add(g[0].name)
                hit.append(g)
    return hit, miss


# ---------------------------------------------------------------------- 主流程
def do_clear(path, chosen, bools, do_adapt, dry, force):
    """把选中的加点清零（只改这一个文件，不碰蚁皇浆）"""
    name = os.path.basename(path)
    total_pts = sum(p for _f, p in chosen)
    spent = sum(cost_of(p) for _f, p in chosen)

    out('  将清零 %d 项 / %d 点' % (len(chosen), total_pts))
    out('  这些点当初一共投入约 %s 浆（清零后不退；想让浆回来请用 补满蚁皇浆.bat）' % fmt(spent))
    out()

    # ---- 适应性开关（可选）
    adapt_hits = []
    if do_adapt:
        F = all_fields()
        for b in sorted(bools):
            f = F.get(b)
            if f is not None and f.is_adapt:
                adapt_hits.append(b)
        if adapt_hits:
            out('  （--adapt）另有 %d 个适应性开关会被关掉：%s'
                % (len(adapt_hits), '、'.join(adapt_hits)))
            out()

    if dry:
        out('  [只检查] 没有改动任何文件。')
        return 0

    # ---- 游戏检测
    running = game_running()
    if running and not force:
        out('  ── 已停止：游戏正在运行 ──')
        out()
        out('  存档只在「游戏存盘那一刻」写盘。游戏开着的时候改，')
        out('  退出时会被它自己的数据覆盖，等于白改。')
        out()
        out('  请先完全退出游戏，回到桌面后重新运行。')
        out()
        return 2
    if running is None:
        out('  [注意] 没能确认游戏是否在运行，继续执行。如果游戏开着，改动可能无效。')
        out()

    # ---- 备份 + 清零
    bak = backup(path)
    data = bytearray(open(path, 'rb').read())
    size0 = len(data)
    changed = []
    for f, _pts in chosen:
        for _s, voff, old in find_int(data, f.name):
            if old:
                struct.pack_into('<i', data, voff, 0)
                changed.append((f.name, voff, old))
    if do_adapt:
        for b in adapt_hits:
            for _s, voff, old in find_bool(data, b):
                if old:
                    data[voff] = 0
                    changed.append((b, voff, 1))
    open(path, 'wb').write(bytes(data))

    out('  %s  已备份 -> backup\\saves\\%s' % (name, bak))
    out('  改写 %d 处；文件大小 %s 字节 -> %s 字节  %s'
        % (len(changed), fmt(size0), fmt(os.path.getsize(path)),
           '（等长，正常）' if os.path.getsize(path) == size0 else '（长度变了，异常！）'))
    out()

    # ---- 写后校验
    ints2, bools2 = JC.read_save(path)
    names = set(f.name for f, _ in chosen)
    left = [(f, v) for f, v in JC.points(ints2) if f.name in names]
    left_b = [b for b in adapt_hits if b in bools2] if do_adapt else []
    ok = not left and not left_b
    out('  校验：%s' % ('通过 —— 选中的加点已全部归零' if ok
                        else '失败！这些还非零：%s'
                             % ('、'.join(['%s=%d' % (f.name, v) for f, v in left]
                                          + list(left_b)))))
    if not ok:
        out()
        out('  请还原备份：copy "backup\\saves\\%s" "%s"' % (bak, path))
        return 3
    out()
    out('  完成。启动游戏后读档即可看到效果（加点已退回，价格从第 1 点重算）。')
    return 0


def do_restore(list_only=False):
    """从备份整档还原"""
    if not os.path.isdir(BAK_DIR):
        out('  没有备份目录：%s' % BAK_DIR)
        return 1
    files = sorted(f for f in os.listdir(BAK_DIR) if '.bak-' in f)
    if not files:
        out('  backup\\saves\\ 里还没有备份。')
        return 1
    out('  可还原的备份：')
    out()
    for i, f in enumerate(files, 1):
        p = os.path.join(BAK_DIR, f)
        out('   %2d  %-52s %8.1f KB  %s'
            % (i, f, os.path.getsize(p) / 1024.0,
               datetime.fromtimestamp(os.path.getmtime(p)).strftime('%m-%d %H:%M')))
    out()
    if list_only:
        out('  要还原其中一个：去掉 --list-backups，改成 --restore')
        return 0
    try:
        s = input('  输入编号还原，直接回车取消 > ').strip()
    except (EOFError, KeyboardInterrupt):
        s = ''
    if not s.isdigit() or not (1 <= int(s) <= len(files)):
        out('  已取消。')
        return 0
    src = os.path.join(BAK_DIR, files[int(s) - 1])
    real = files[int(s) - 1].split('.bak-')[0]
    dst = os.path.join(saves_dir(), real)
    if game_running():
        out()
        out('  ── 已停止：游戏正在运行，先退出游戏再还原 ──')
        return 2
    if os.path.isfile(dst):
        backup(dst)
    shutil.copy2(src, dst)
    out('  已还原 -> %s' % dst)
    out('  （还原前的当前版本也备份了一份，万一后悔还能换回来）')
    return 0


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    a = sys.argv[1:]
    dry = '--check' in a
    force = '--force' in a
    do_all = '--all' in a
    do_adapt = '--adapt' in a
    only = [a[i + 1] for i, x in enumerate(a) if x == '--only' and i + 1 < len(a)]
    fname = DEFAULT_SAVE
    if '--file' in a:
        try:
            fname = a[a.index('--file') + 1]
        except IndexError:
            out('  [!] --file 后面要跟存档文件名'); return 1

    out('=' * 68)
    out('  蚁皇浆加点回退' + ('   [只检查，不改文件]' if dry else ''))
    out('=' * 68)
    out()

    if '--list-backups' in a:
        return do_restore(list_only=True)
    if '--restore' in a:
        return do_restore()

    sdir = saves_dir()
    path = os.path.join(sdir, fname)
    if not os.path.isfile(path):
        out('  [!] 找不到存档：%s' % path)
        out('      用 --file 指定别的存档名（只写文件名，不用写路径）')
        return 1

    items, _ints, bools = scan(path)
    if not items:
        out('  %s 里没有找到任何加点。' % fname)
        out('  这台机器上还有这些档带加点：')
        out()
        for n in sorted(os.listdir(sdir)):
            if not n.endswith('.sav') or 'backup' in n.lower():
                continue
            try:
                it, _i, _b = scan(os.path.join(sdir, n))
            except Exception:
                continue
            if it:
                out('    --file %-34s %2d 项 / %4d 点'
                    % (n, len(it), sum(p for _f, p in it)))
        return 0

    out('  存档：%s' % path)
    out()
    out('  当前加点：')
    out('  ' + '-' * 64)
    for i, (f, p) in enumerate(items, 1):
        out('   %2d  %-14s %-12s %4d 点   已投入约 %s 浆'
            % (i, f.unit_zh, f.item, p, fmt(cost_of(p))))
    out('  ' + '-' * 64)
    out('      合计 %d 项 / %d 点 / 已投入约 %s 浆'
        % (len(items), sum(p for _f, p in items),
           fmt(sum(cost_of(p) for _f, p in items))))
    out()
    out('  说明：本脚本只清加点，不动蚁皇浆，已投入的浆不会退回来。')
    out('        想让浆回来，另外双击  补满蚁皇浆.bat（会补到 20 亿）。')
    out()

    # ---- 选哪些
    chosen = []
    if do_all:
        chosen = list(items)
    elif only:
        chosen, miss = select_by_keyword(items, only)
        if miss:
            out('  ── 已停止：有关键字没匹配到 ──')
            out()
            out('  匹配不到：%s' % '、'.join(miss))
            out()
            out('  这个存档里有加点的单位（想清哪个就直接抄它的名字）：')
            for u in sorted(set(f.unit_zh for f, _ in items)):
                out('      %s' % u)
            out()
            out('  只要有关键字认不出来，脚本就不动手 —— 免得你以为清掉了其实没清。')
            return 1
    else:
        if dry:
            out('  （--check 到此结束。要清加点：去掉 --check，或加 --all）')
            return 0
        out('  要清掉哪些？')
        out('    输入编号，多个用逗号隔开，如  1,3,5')
        out('    输入 all 全清')
        out('    直接回车 = 取消')
        out()
        out('    提示：想省着玩可以只清掉花浆最多的那几项，其余保留。')
        out('          清零的项以后能按原价重新加回来。')
        out()
        try:
            s = input('  > ').strip()
        except (EOFError, KeyboardInterrupt):
            s = ''
        if not s:
            out()
            out('  已取消，没有改动任何文件。')
            return 0
        if s.lower() == 'all':
            chosen = list(items)
        else:
            idx = set()
            for part in s.replace('，', ',').split(','):
                part = part.strip()
                if part.isdigit() and 1 <= int(part) <= len(items):
                    idx.add(int(part))
                elif part:
                    out('  [!] 忽略无效输入：%s' % part)
            chosen = [items[i - 1] for i in sorted(idx)]
        if not chosen:
            out()
            out('  没选中任何项，已取消。')
            return 0
        out()

    return do_clear(path, chosen, bools, do_adapt, dry, force)


if __name__ == '__main__':
    sys.exit(main())
