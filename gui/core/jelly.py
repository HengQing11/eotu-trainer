# -*- coding: utf-8 -*-
"""蚁皇浆与加点：价格、清单、生效值、余额槽位

价格公式（用你存档里的实测值反推校准）：
    首点 1 浆，之后每点 ×1.15，每个项独立计价。
    累计 = (1.15^n - 1) / 0.15
    85 点 -> 962,104（存档实测 962,177，误差 0.008%，只用于显示，不参与写档）

生效值算法（已用 6 个已知项反推验证）：
    生效值 = 基础数值表的值 + 每点效果 × 已加点数
    逐等级各自加同样的绝对量（Lv1/2/3 都加 +N，不是按比例）
    '每点 +0.5%' 这类要 /100 才是表里的小数（0.005）
"""
import os

from . import paths
from . import gvas
from . import fieldlib

PRICE_RATE = 1.15

# 展示列: (CSV 列名, 表头, 显示方式)   'num' 普通 / 'pct' 0~1 存百分数 / 'cap' 0 表示不限
STAT_COLS = [
    ('Health', '生命', 'num'),
    ('AttackDamage', '普攻伤害', 'num'),
    ('AttackSpeed', '攻速系数', 'num'),
    ('Speed', '移速', 'num'),
    ('Armour', '护甲', 'num'),
    ('PhysicalResist', '物抗', 'pct'),
    ('VenomResist', '毒抗', 'pct'),
    ('AOEResist', 'AOE抗', 'pct'),
    ('Evasion', '闪避', 'pct'),
    ('Piercing', '穿刺', 'pct'),
    ('MaxSingleDamage', '单次最大受伤', 'cap'),
    ('HealthPerSecond', '回血/秒', 'num'),
    ('DigAmmount', '挖掘量', 'num'),
    ('FoodCarryMax', '搬运上限', 'num'),
    ('TargetRadius', '视野半径', 'num'),
    ('PointValue', '点数', 'num'),
]
COL_ZH = {c: zh for c, zh, _k in STAT_COLS}
COL_KIND = {c: k for c, _zh, k in STAT_COLS}

_stats_cache = {}


# ------------------------------------------------------------------ 价格

def cost_of(n):
    """从 0 加到 n 点的累计花费"""
    if n <= 0:
        return 0
    return int((PRICE_RATE ** n - 1) / (PRICE_RATE - 1) + 0.5)


def unit_price(n):
    """第 n 点（从 1 数）的单价"""
    if n <= 0:
        return 0
    return int(round(PRICE_RATE ** (n - 1)))


def budget_points(jelly):
    """手上这些浆大概还能买多少点（从 0 起算，单一项）"""
    if jelly <= 0:
        return 0
    import math
    n = int(math.log(jelly * (PRICE_RATE - 1) + 1, PRICE_RATE))
    while cost_of(n + 1) <= jelly:
        n += 1
    while n > 0 and cost_of(n) > jelly:
        n -= 1
    return n


# ------------------------------------------------------------------ 基础数值表

def stats_table(freeplay=False):
    """{行名: {列: 值}} —— 直接读工作区里解包出来的数值表

    真源是 uexp（由 `creature_stats` 解析），不是 CSV：
    CSV 只是给人看的导出物，改了数值也不会回流到它。
    延迟导入 creature_stats 是为了别在启动路径上拉起 pakbuild。
    """
    from . import creature_stats
    k = 'free' if freeplay else 'main'
    if k in _stats_cache:
        return _stats_cache[k]
    try:
        out = creature_stats.load(freeplay)[0]
    except (creature_stats.StatsError, OSError, ValueError):
        out = {}
    _stats_cache[k] = out
    return out


def rows_of(prefix, table=None):
    """行名前缀 -> [(行名, 行数据)]，如 LeafcutterMedia -> 1/2/3"""
    t = table if table is not None else stats_table()
    return [('%s%d' % (prefix, i), t['%s%d' % (prefix, i)])
            for i in (1, 2, 3) if '%s%d' % (prefix, i) in t]


def fmt(v, kind='num'):
    if v is None or v == '':
        return '—'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if kind == 'pct':
        return '%g%%' % round(f * 100, 1)
    if kind == 'cap':
        return '不限' if f == 0 else '%g' % round(f, 2)
    if f == int(f):
        return '%d' % int(f)
    return ('%.2f' % f).rstrip('0').rstrip('.')


# ------------------------------------------------------------------ 加点

def addons(save):
    """存档里已加点的 IP 项 -> [(Field, 点数, 已投入浆)]，按点数降序"""
    F = fieldlib.all_fields()
    out = []
    for name, vals in save.ints.items():
        f = F.get(name)
        if f is None or not f.is_ip:
            continue
        v = vals[0] if isinstance(vals, list) else vals
        if v:
            out.append((f, int(v), cost_of(int(v))))
    out.sort(key=lambda x: -x[1])
    return out


def unknown_addons(save):
    """存档里有、字段库没登记的整数升级字段 —— 显式报出来，不静默丢"""
    F = fieldlib.all_fields()
    out = []
    for name in save.ints:
        if name in F:
            continue
        if name.endswith('Improvment') or name.endswith('Improvement'):
            out.append(name)
    return sorted(out)


def adapts(save):
    """已启用的适应性 -> [(Field, 当前值)]"""
    F = fieldlib.all_fields()
    out = []
    for f in F.values():
        if not f.is_adapt:
            continue
        cur = save.get_bool(f.name, default=None)
        if cur is not None:
            out.append((f, cur))
    out.sort(key=lambda x: (x[0].unit_zh, x[0].item))
    return out


def unlocks(save):
    F = fieldlib.all_fields()
    out = []
    for f in F.values():
        if not f.is_unlock:
            continue
        cur = save.get_bool(f.name, default=None)
        if cur is not None:
            out.append((f, cur))
    out.sort(key=lambda x: (x[0].unit_zh, x[0].item))
    return out


def effective(f, pts, table=None):
    """算加点后的生效值

    -> dict(variants=[(形态标签, 每点原值, 是否百分比, 每点折算值, 总增量)],
            rows=[(行名, 基础值, 生效值, 显示方式)], col_zh, in_table)
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
        for rn, row in rows_of(f.row_prefix, table):
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


def delta_text(f, variants):
    """总增量文本：+1.1 / +10% / -10 秒"""
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


def eff_text(rows):
    """生效值行业文本"""
    if not rows:
        return ''
    if len(rows) == 1 or all(r[2] == rows[0][2] for r in rows):
        return fmt(rows[0][2], rows[0][3])
    return ' / '.join('Lv%d %s' % (i, fmt(r[2], r[3])) for i, r in enumerate(rows, 1))


# ------------------------------------------------------------------ 蚁皇浆余额

def jelly_slots(path):
    """读存档里的 RoyalJelly 槽位 -> [(值偏移, 当前值, OwningPlayer)]

    一个 LevelData.sav 里通常有多个槽位（自己在玩的巢 + 空巢），
    OwningPlayer = 0 的那个才是玩家的。找不到 OwningPlayer 就是 None。
    """
    if not path or not os.path.isfile(path):
        return []
    d = open(path, 'rb').read()
    owners = gvas.find(d, 'OwningPlayer', 'IntProperty')      # [(模式起点, 值偏移)]
    res = []
    for _s, voff in gvas.find(d, 'RoyalJelly', 'IntProperty'):
        prev = [o for o in owners if o[1] < voff]
        own = gvas.read_at(d, prev[-1][1], 'IntProperty') if prev else None
        res.append((voff, gvas.read_at(d, voff, 'IntProperty'), own))
    return res


def main_jelly(path):
    """玩家那个槽位的余额（优先 OwningPlayer=0，其次取最小余额）"""
    slots = jelly_slots(path)
    if not slots:
        return None
    own = [s for s in slots if s[2] == 0]
    return own[0][1] if own else min(s[1] for s in slots)


def set_jelly(path, value, only_main=False):
    """改写蚁皇浆槽位 -> (SaveFile, [(旧值, 新值)])"""
    sf = gvas.SaveFile(path)
    changed = []
    for voff, old, own in jelly_slots(path):
        if only_main and own != 0:
            continue
        gvas.write_at(sf.data, voff, 'IntProperty', int(value))
        changed.append((old, int(value)))
    sf.dirty = sf.dirty or bool(changed)
    return sf, changed
