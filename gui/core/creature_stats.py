# -*- coding: utf-8 -*-
"""生物数值表的读 / 改 / 还原本层（纯数据，不依赖界面）

数据来自工作区里的 `CreatureStats`（游戏本体数据表的解包副本）：
    EotU/Content/Assets/Data/CreatureStats                      战役模式
    EotU/Content/Assets/Data/FreeplayStats/CreatureStats_Freeplay  自由模式

为什么改的是「工作区副本 + 打包成新 pak」而不是直接改游戏：
  官方 pak 的索引是 AES 加密的，解不开也打不回去。
  所以只能新增一个 pak 去覆盖同名资产 —— 游戏加载时后面的 pak 优先。

性能约定
  `load()` 解析一次约 4 MB 的 uexp，结果**按表缓存**（战役 / 自由各一份）。
  改值走 `apply_edits()`，它直接把新值写进内存副本并落盘，
  调用方拿返回值更新界面即可，**不需要重新解析**。
"""
import os
import struct

from . import pakbuild, ueasset

BASE = 'EotU/Content/Assets/Data/CreatureStats'
FREE_BASE = 'EotU/Content/Assets/Data/FreeplayStats/CreatureStats_Freeplay'

# 22 个可改属性，顺序即数据表里的顺序
COLUMNS = [
    ('Health', '生命', '总血量'),
    ('AttackDamage', '普攻伤害', '每次普通攻击造成的伤害'),
    ('AttackSpeed', '攻速系数', '倍率。游戏内显示的攻速 ≈ 1.5 × 该值'),
    ('Speed', '移速', '移动速度'),
    ('Armour', '护甲', '按数值减伤'),
    ('PhysicalResist', '物理抗性', '0~1，1 = 完全免疫物理'),
    ('VenomResist', '毒抗', '0~1'),
    ('SlowResist', '减速抗性', '0~1'),
    ('AOEResist', 'AOE 抗性', '0~1'),
    ('Evasion', '闪避', '0~1'),
    ('Piercing', '穿刺', '无视护甲的比例，0~1'),
    ('MaxSingleDamage', '单次最大受伤', '0 = 不限制'),
    ('HealthPerSecond', '每秒回血', '脱战时每秒回血'),
    ('DigAmmount', '挖掘量', '一次挖掘的进度'),
    ('DigSpeed', '挖掘速度', ''),
    ('FoodCarryMax', '搬运上限', '一次能搬多少食物'),
    ('FoodHarvestTime', '采集耗时', ''),
    ('FoodValue', '食物价值', ''),
    ('PickupTime', '拾取耗时', ''),
    ('WanderDistance', '游荡距离', ''),
    ('TargetRadius', '视野半径', '发现目标的距离'),
    ('PointValue', '点数', '击杀获得的分数'),
]
COL_ZH = {c[0]: c[1] for c in COLUMNS}
COL_DESC = {c[0]: c[2] for c in COLUMNS}
COL_KEY = {c[1]: c[0] for c in COLUMNS}

# 显示用的列预设（列太多，横着放不下，让用户选）
PRESETS = [
    ('常用', ['Health', 'AttackDamage', 'AttackSpeed', 'Speed',
              'PointValue', 'FoodCarryMax', 'TargetRadius', 'Armour']),
    ('战斗', ['Health', 'AttackDamage', 'AttackSpeed', 'Armour', 'PhysicalResist',
              'VenomResist', 'AOEResist', 'Evasion', 'Piercing', 'MaxSingleDamage']),
    ('采集行动', ['Speed', 'DigAmmount', 'DigSpeed', 'FoodCarryMax', 'FoodHarvestTime',
                  'FoodValue', 'PickupTime', 'WanderDistance', 'TargetRadius']),
    ('全部', [c[0] for c in COLUMNS]),
]

# ---------------------------------------------------------------- 缓存
_cache = {}          # key -> (rows, table)
_uexp = {}           # key -> (bytearray, 路径)


class StatsError(Exception):
    """数值表读写失败"""


def _key(freeplay):
    return 'free' if freeplay else 'main'


def table_label(freeplay):
    return '自由模式数值' if freeplay else '战役数值'


def load(freeplay=False, force=False):
    """解析数值表 -> (rows, table)

    rows  = {行名: {属性: 值}}                 界面展示、批量计算用
    table = {(行名, 属性): (值偏移, 旧值)}      真正改值要用偏移
    解析结果按表缓存；`force=True` 才重新解析。
    """
    k = _key(freeplay)
    if not force and k in _cache:
        return _cache[k]

    base = FREE_BASE if freeplay else BASE
    ua, ux = pakbuild.uasset_pair(base)
    if not os.path.isfile(ux):
        raise StatsError('找不到数值表资产：%s' % ux)

    data, table = ueasset.collect_floats(ua, ux)
    rows = {}
    for (rn, attr), (_off, val) in table.items():
        rows.setdefault(rn, {})[attr] = val

    _cache[k] = (rows, table)
    _uexp[k] = (data, ux)
    return _cache[k]


def invalidate():
    """丢弃缓存（工作区被重置、或文件被外部改动后调用）"""
    _cache.clear()
    _uexp.clear()


def names(freeplay=False):
    return sorted(load(freeplay)[0])


def count_editable(freeplay=False):
    return len(load(freeplay)[1])


def overview(freeplay=False):
    """给界面顶部用的一行摘要"""
    rows, table = load(freeplay)
    species = {rn.rstrip('0123456789') or rn for rn in rows}
    return {'rows': len(rows), 'species': len(species), 'cells': len(table)}


def ranges(freeplay=False):
    """每列的取值分布 -> {属性: (最小, 最大, 平均)}，用于批量操作前的提示"""
    rows, _ = load(freeplay)
    out = {}
    for attr, _zh, _d in COLUMNS:
        vals = [r[attr] for r in rows.values() if attr in r]
        if vals:
            out[attr] = (min(vals), max(vals), sum(vals) / len(vals))
    return out


# ---------------------------------------------------------------- 改值

def apply_edits(edits, freeplay=False):
    """把 {(行名, 属性): 新值} 写进内存副本并落盘

    -> 真正生效的 [(行名, 属性, 旧值, 新值)]
       调用方拿这个列表去更新界面 / 记撤销栈，**不要再重新 load()**。
    """
    rows, table = load(freeplay)
    data, ux = _uexp[_key(freeplay)]

    applied = []
    for (rn, attr), new in edits.items():
        hit = table.get((rn, attr))
        if not hit:
            continue
        off, old = hit
        new = float(new)
        if abs(old - new) < 1e-9:
            continue
        struct.pack_into('<f', data, off, new)
        table[(rn, attr)] = (off, new)          # 同步缓存，避免下次算错
        if rn in rows:
            rows[rn][attr] = new
        applied.append((rn, attr, old, new))

    if applied:
        with open(ux, 'wb') as f:
            f.write(bytes(data))
    return applied


def undo(applied, freeplay=False):
    """把 apply_edits 返回的列表倒回去（原地撤销）"""
    if not applied:
        return []
    back = {(rn, attr): old for rn, attr, old, _new in applied}
    return apply_edits(back, freeplay)


def scale(sel_rows, attr, factor, freeplay=False):
    """选中行的某属性 × 系数 -> edits（不落盘）"""
    rows, _ = load(freeplay)
    out = {}
    for rn in sel_rows:
        r = rows.get(rn)
        if r and attr in r:
            out[(rn, attr)] = r[attr] * factor
    return out


def set_all(sel_rows, attr, value, freeplay=False):
    """选中行的某属性 = 固定值 -> edits（不落盘）"""
    rows, _ = load(freeplay)
    return {(rn, attr): float(value) for rn in sel_rows
            if rn in rows and attr in rows[rn]}


# ---------------------------------------------------------------- 显示

def fmt(v, short=False):
    """把浮点显示得好看：0.05000000074505806 -> 0.05"""
    if v is None:
        return '—'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f):
        return '%d' % int(f)
    if short:
        return ('%.3f' % f).rstrip('0').rstrip('.')
    return ('%.6f' % f).rstrip('0').rstrip('.')
