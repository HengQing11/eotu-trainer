# -*- coding: utf-8 -*-
"""升级效果计算 —— 存档 × 字段库 × 基础数值表，三合一

gen_ngp_report.py 和 merge_html.py 共用这一份实现。
同一个数字只算一次，避免两份报告对不上。

生效值算法（已用你存档里 6 个已知项反推验证）：
    生效值 = 基础数值表里的值 + 每点效果 × 已加点数
    逐等级各自加同样的绝对量（Lv1/2/3 都加 +N，不是按比例）
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from field_lib import all_fields, KIND_IP, KIND_UNLOCK, KIND_ADAPT  # noqa: E402
from sav_props import iter_tags, read_value                         # noqa: E402
from gen_jelly_table import STORY, STAT_COLS, fmt                   # noqa: E402

SAVES = r'C:/Users/beimo/AppData/Local/EotU/Saved/SaveGames/'
CUR = SAVES + 'Colony1.sav'
NG0 = SAVES + 'Colony1NewGamePlus0.sav'

COL_ZH = {c: zh for c, zh, _k in STAT_COLS}
COL_KIND = {c: k for c, _zh, k in STAT_COLS}


def read_save(path):
    """-> ({int 字段: 值}, {为 True 的 bool 字段})"""
    d = open(path, 'rb').read()
    ints, bools = {}, set()
    for off, name, typ in iter_tags(d):
        v = read_value(d, off, typ)
        if typ == 'IntProperty' and v is not None:
            ints[name] = v
        elif typ == 'BoolProperty' and v is True:
            bools.add(name)
    return ints, bools


def rows_of(prefix):
    """行名前缀 -> [(行名, 行数据)]，如 LeafcutterMedia -> 1/2/3"""
    out = []
    for i in (1, 2, 3):
        k = '%s%d' % (prefix, i)
        if k in STORY:
            out.append((k, STORY[k]))
    return out


def points(ints):
    """从存档里挑出所有已加点的 IP 字段 -> [(Field, 点数)]，按点数降序"""
    F = all_fields()
    out = []
    for name, val in ints.items():
        f = F.get(name)
        if f is not None and f.is_ip and val:
            out.append((f, val))
    out.sort(key=lambda x: -x[1])
    return out


def unknown_ints(ints):
    """存档里有、字段库里没登记的整数升级字段 —— 必须显式报出来，不许静默丢"""
    F = all_fields()
    out = []
    for name in ints:
        if name in F:
            continue
        if name.endswith('Improvment') or name.endswith('Improvement'):
            out.append(name)
    return sorted(out)


def unlocks(bools):
    F = all_fields()
    return sorted(b for b in bools if b in F and F[b].is_unlock)


def adapts(bools):
    F = all_fields()
    return sorted(b for b in bools if b in F and F[b].is_adapt)


def unknown_bools(bools):
    """存档里为 true、但字段库没登记的开关"""
    F = all_fields()
    return sorted(b for b in bools
                  if b not in F and (b.startswith('b') or b.startswith('B')))


def effective(f, pts):
    """算某个字段加点后的生效值

    -> dict(
        variants = [(形态标签, 每点原值, 是否百分比, 每点折算值, 总增量)]
        rows     = [(行名, 基础值, 生效值, 显示格式)]     # 不在基础表里则为 []
        col_zh   = 数值表列中文名 或 ''
        in_table = 能否落到基础数值表
    )

    注：per 文本写的是人话（'每点 +0.5%'），要 /100 才是数值表里的小数（0.005）。
    variants 里同时给出「原值」和「折算值」，前者用于给人看，后者用于算数。
    """
    vals = f.per_values()
    variants = []
    for v, pct, lab in vals:
        delta = (v / 100.0) if pct else v
        variants.append((lab, v, pct, delta, delta * pts))

    rows = []
    if f.in_stat_table and f.row_prefix and len(vals) == 1:
        kind = COL_KIND.get(f.col, 'num')
        delta = variants[0][3]
        for rn, row in rows_of(f.row_prefix):
            raw = row.get(f.col)
            if raw in (None, ''):
                continue
            try:
                base = float(raw)
            except ValueError:
                continue
            rows.append((rn, base, base + delta * pts, kind))

    return dict(variants=variants, rows=rows,
                col_zh=COL_ZH.get(f.col, ''), in_table=bool(rows))


def eff_text(rows):
    """生效值行内文本：Lv1 4.7 / Lv2 5.5 / Lv3 5.5（三档同值时只显示一个数）"""
    if not rows:
        return ''
    if len(rows) == 1 or all(r[2] == rows[0][2] for r in rows):
        return '生效值 <b>%s</b>' % fmt(rows[0][2], rows[0][3])
    parts = []
    for i, (rn, _b, after, kind) in enumerate(rows, 1):
        parts.append('Lv%d <b>%s</b>' % (i, fmt(after, kind)))
    return '生效值 ' + ' / '.join(parts)


def delta_text(f, variants):
    """总增量文本：+1.1 / +10% / -10 秒（多形态时用 / 分隔，如 迫击 / 速射）"""
    if not variants:
        return ''
    out = []
    for lab, _raw, pct, _delta, total in variants:
        s = ('%+g%%' % (total * 100)) if pct else ('%+g' % total)
        if len(variants) == 1:
            s += f.per_suffix()
        if lab:
            s += '（%s）' % lab
        out.append(s)
    return ' / '.join(out)


def backups_newer(fields_list):
    """对照轮转备份，找出「当前档有、所有备份都没有」的字段

    游戏每次存盘会把上一版轮转成 Colony1-backup1~5.sav。
    凡是全部备份里都找不到的字段，就是最近一次存盘才写进去的 ——
    这类字段在更早生成的报告里必然缺失（切叶蚁中工那 85 点就是这么漏的）。
    """
    bks = sorted(glob.glob(SAVES + 'Colony1-backup*.sav'))
    if not bks:
        return [], []
    seen = set()
    for bp in bks:
        try:
            bi, _ = read_save(bp)
        except OSError:
            continue
        seen |= set(bi)
    return [f.name for f, _ in fields_list if f.name not in seen], bks
