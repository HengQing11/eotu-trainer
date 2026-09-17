# -*- coding: utf-8 -*-
"""读《升级项字段库.csv》—— 升级字段的唯一权威源（GUI 版）

与 scripts/field_lib.py 是同一份数据，只是路径改成可移植的查找方式：
打包成 exe 后字段库会放在 exe 同级 data/ 下，用户可以直接编辑扩充。
"""
import csv
import os
import re
import shutil

from . import paths

KIND_IP = 'IP微调'
KIND_ADAPT = '适应性'
KIND_UNLOCK = '解锁开关'

CSV_NAME = '升级项字段库.csv'
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
        return bool(self.col)

    def per_values(self):
        """解析「每点效果」-> [(数值, 是否百分比, 形态标签)]"""
        if not self.per:
            return []
        labels = re.findall(r'（([^）]+)）', self.per)
        nums = re.findall(r'([+-]?\d+(?:\.\d+)?)\s*(%?)', self.per)
        return [(float(v), pct == '%', labels[i] if i < len(labels) else '')
                for i, (v, pct) in enumerate(nums)]

    def per_text(self):
        return self.per.replace('每点 ', '')

    def per_suffix(self):
        """'每点 -0.5 秒' -> ' 秒'（仅单形态时有效）"""
        if not self.per or len(self.per_values()) != 1:
            return ''
        m = re.search(r'[+-]?\d+(?:\.\d+)?\s*%?\s*(.*)$', self.per)
        s = (m.group(1) or '').strip() if m else ''
        return (' ' + s) if s else ''

    def __repr__(self):
        return '<Field %s %s %s>' % (self.name, self.kind, self.unit_zh)


def csv_path():
    """字段库位置

    优先可写目录（用户能自己加字段）。打包态第一次跑时那里还没有，
    就从 exe 内嵌的副本释放一份过去 —— find_data(writable=True) 只认可写目录，
    不查 PyInstaller 的 _MEIPASS，所以这一步必须显式做。
    """
    p = paths.find_data(CSV_NAME, writable=True)
    # 打包态下 MOD_DIR 就是 PyInstaller 的解包目录（每次运行都换一个 _MEIxxxx），
    # 命中它并不等于「可写」—— 那种情况下必须释放一份到 exe 同级的 data/，
    # 否则用户改了字段库，下次运行又变回内嵌的旧版。
    in_bundle = bool(p) and paths.FROZEN and os.path.dirname(p) == paths.bundle_dir()
    if p and not in_bundle:
        return p
    src = p or paths.find_data(CSV_NAME)
    if not src:
        return None
    if not paths.FROZEN:
        return src
    dst = os.path.join(paths.ensure_data_dir(), CSV_NAME)
    try:
        shutil.copy2(src, dst)
        return dst
    except OSError:
        return src


def load(path=None):
    out = {}
    p = path or csv_path()
    if not p or not os.path.isfile(p):
        return out, []
    order = []
    with open(p, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            fld = Field(r)
            if fld.name:
                if fld.name not in out:
                    order.append(fld.name)
                out[fld.name] = fld
    return out, order


def all_fields():
    """{字段名: Field}，带缓存"""
    key = csv_path() or ''
    if key not in _cache:
        _cache[key] = load()[0]
    return _cache[key]


def ordered_fields():
    """[(Field, 原始行号)]，保留 CSV 里的顺序"""
    key = csv_path() or ''
    if key + '#ord' not in _cache:
        d, order = load()
        _cache[key + '#ord'] = [(d[n], i) for i, n in enumerate(order)]
    return _cache[key + '#ord']


def reload():
    _cache.clear()
    return all_fields()


def by_kind(kind):
    return [f for f in all_fields().values() if f.kind == kind]


def units(kind=None):
    """出现过的单位，按 CSV 顺序 -> [(中文, 英文, [Field...])]"""
    out = []
    seen = {}
    for f, _i in ordered_fields():
        if kind and f.kind != kind:
            continue
        key = f.unit_zh
        if key not in seen:
            seen[key] = len(out)
            out.append((f.unit_zh, f.unit_en, []))
        out[seen[key]][2].append(f)
    return out


def unknown_hint(name):
    """存档里有、字段库里没有时给出的提示"""
    return ('%s 还没登记进字段库，加点效果不会被计算。'
            '在 升级项字段库.csv 里加一行就能认它。' % name)
