# -*- coding: utf-8 -*-
"""读《升级项字段库.csv》—— 升级字段的唯一权威源

为什么要单独一个模块：
    以前「字段 -> 单位/项目/每点效果/对应数值表哪一列」这层信息散落在
    gen_ngp_report.py（FIELD_ROW 手写 8 条）、merge_html.py（BADGES 手写 7 条）、
    gen_jelly_table.py（UNITS.minor）三个地方，互相不知道对方。
    结果就是：存档里出现一个没登记进映射表的字段，报告会**静默漏掉它**
    （切叶蚁中工那 85 点就是这么丢的）。

现在三处统一 import 本模块：
    from field_lib import all_fields, Field

以后加新字段，只改 CSV 一行，三处自动认。
"""
import csv
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.abspath(os.path.join(HERE, '..'))
CSV_PATH = os.path.join(MOD, '升级项字段库.csv')

KIND_IP = 'IP微调'
KIND_ADAPT = '适应性'
KIND_UNLOCK = '解锁开关'

_cache = {}


class Field(object):
    """一个升级字段"""

    __slots__ = ('name', 'kind', 'unit_zh', 'unit_en', 'row_prefix',
                 'item', 'per', 'col', 'source', 'note')

    def __init__(self, r):
        self.name = (r.get('字段名') or '').strip()
        self.kind = (r.get('类型') or '').strip()
        self.unit_zh = (r.get('单位中文') or '').strip()
        self.unit_en = (r.get('单位英文') or '').strip()
        self.row_prefix = (r.get('数据表行前缀') or '').strip()
        self.item = (r.get('项目中文') or '').strip()
        self.per = (r.get('每点效果') or '').strip()
        self.col = (r.get('数值表列') or '').strip()
        self.source = (r.get('数据来源') or '').strip()
        self.note = (r.get('备注') or '').strip()

    @property
    def is_ip(self):
        return self.kind == KIND_IP

    @property
    def is_adapt(self):
        return self.kind == KIND_ADAPT

    @property
    def is_unlock(self):
        return self.kind == KIND_UNLOCK

    @property
    def in_stat_table(self):
        """这一项能不能落到基础数值表的某一列上（否则只能显示加了多少点）"""
        return bool(self.col)

    def per_values(self):
        """解析「每点效果」文本 -> [(数值, 是否百分比, 形态标签)]

        例：'每点 +0.08（迫击）/ +0.02（速射）' -> [(0.08,False,'迫击'), (0.02,False,'速射')]
            '每点 -0.5 秒'                       -> [(-0.5, False, '')]
            '每点 +0.5%'                         -> [(0.5, True, '')]
        """
        if not self.per:
            return []
        labels = re.findall(r'（([^）]+)）', self.per)
        nums = re.findall(r'([+-]?\d+(?:\.\d+)?)\s*(%?)', self.per)
        out = []
        for i, (v, pct) in enumerate(nums):
            out.append((float(v), pct == '%', labels[i] if i < len(labels) else ''))
        return out

    def per_text(self):
        """每点效果去掉'每点 '前缀，用于行内展示"""
        return self.per.replace('每点 ', '')

    def per_suffix(self):
        """每点效果里的单位后缀，如 ' 秒'（'每点 -0.5 秒' -> ' 秒'）

        仅当这一项只有单一形态时可用；多形态（迫击/速射）返回空串。
        """
        if not self.per or len(self.per_values()) != 1:
            return ''
        m = re.search(r'[+-]?\d+(?:\.\d+)?\s*%?\s*(.*)$', self.per)
        s = (m.group(1) or '').strip() if m else ''
        return (' ' + s) if s else ''

    def __repr__(self):
        return '<Field %s %s %s>' % (self.name, self.kind, self.unit_zh)


def load(path=None):
    p = path or CSV_PATH
    out = {}
    if not os.path.isfile(p):
        return out
    for r in csv.DictReader(open(p, encoding='utf-8-sig')):
        f = Field(r)
        if f.name:
            out[f.name] = f
    return out


def all_fields():
    """{字段名: Field}，带缓存"""
    key = CSV_PATH
    if key not in _cache:
        _cache[key] = load()
    return _cache[key]


def by_kind(kind):
    return [f for f in all_fields().values() if f.kind == kind]


def for_unit(unit_zh, kind=KIND_IP):
    """某单位下的所有字段（按 CSV 里的顺序）"""
    return [f for f in all_fields().values() if f.unit_zh == unit_zh and f.kind == kind]


def unit_names():
    """字段库里出现过的单位，按首次出现顺序"""
    seen = []
    for f in all_fields().values():
        if f.unit_zh not in seen:
            seen.append(f.unit_zh)
    return seen


def card_marker(unit_zh, unit_en):
    """单位卡片的 <h3> 标记（与 gen_jelly_table.py 产出的结构一致）"""
    m = unit_en or ''
    return '<h3>%s<small>%s</small></h3>' % (unit_zh, m)
