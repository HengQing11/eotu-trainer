"""《官方数值_覆盖表.csv》的读取与套用。

- 读取：`OFFICIAL[(数据表行名, CSV列名)] = 官方值`，`SOURCE_BY_BASE[行名前缀] = 出处`
- `--apply`：把官方值写进 `物种数值表_CreatureStats.csv` 与 `CreatureStats_Freeplay.csv`
  （只覆盖官方公布过的格子；首次执行前把「来自 mod 包」的原始表备份到 sources/）
- `--check`：只对比、不写盘

为什么需要它：那 9 行是从社区 mod 包里解析出来的、被该作者改写过的值，
不是官方原值。详见 build_official_overrides.py 的说明。
"""
import csv
import os
import shutil
import sys

MODDIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
OVERRIDE_CSV = os.path.join(MODDIR, '官方数值_覆盖表.csv')
TABLES = [
    (os.path.join(MODDIR, '物种数值表_CreatureStats.csv'), 'ID(游戏内部名)',
     '物种数值表_CreatureStats.来自mod包.csv'),
    (os.path.join(MODDIR, 'CreatureStats_Freeplay.csv'), 'RowName',
     'CreatureStats_Freeplay.来自mod包.csv'),
]
SNAPDIR = os.path.join(MODDIR, 'sources')

ROWNUM = {'1': 1, '2': 2, '3': 3}


def _num(s):
    try:
        f = float(s)
    except (TypeError, ValueError):
        return s
    return int(f) if f == int(f) else f


def load():
    """-> OFFICIAL[(rn, col)], SRC[rn], NOTES(list), UNCOVERED(list)"""
    official, src, notes, uncovered = {}, {}, [], []
    if not os.path.exists(OVERRIDE_CSV):
        return official, src, notes, uncovered
    with open(OVERRIDE_CSV, encoding='utf-8-sig', newline='') as f:
        for row in csv.reader(f):
            if not row or not row[0]:
                continue
            if row[0].startswith('#'):
                if len(row) > 4 and row[4]:
                    (uncovered if row[0].startswith('# 未覆盖') else notes).append(row[4])
                continue
            if len(row) < 4 or row[1] == 'CSV列名':       # 表头
                continue
            rn, col, _lv, val, where = row[0], row[1], row[2], row[3], row[4]
            official[(rn, col)] = _num(val)
            src[rn] = where
    return official, src, notes, uncovered


OFFICIAL, SRC, NOTES, UNCOVERED = load()

# 官方 wiki 的 Notable stats 没有公布、因此本表不覆盖的两列 (CSV列名, 中文名)
# 与 build_official_overrides.py 里的 UNCOVERED 保持一致
HOLES = [('DigAmmount', '挖掘量'), ('MaxSingleDamage', '单次最大受伤')]


def official_of(rn, col):
    """该行的这一列有没有官方值；没有返回 None"""
    return OFFICIAL.get((rn, col))


def source_of(rn):
    return SRC.get(rn, '')


def covered_rows():
    return sorted({rn for rn, _ in OFFICIAL})


# 行名前缀 -> (中文名, {等级: {CSV列: 官方值}}, 出处)
def orig_by_base():
    out = {}
    for (rn, col), val in OFFICIAL.items():
        base, lv = rn[:-1], rn[-1]
        if lv not in ROWNUM:
            continue
        d = out.setdefault(base, {})
        d.setdefault(ROWNUM[lv], {})[col] = val
    return out


def _snapshot(path, name):
    os.makedirs(SNAPDIR, exist_ok=True)
    dst = os.path.join(SNAPDIR, name)
    if not os.path.exists(dst):
        shutil.copy2(path, dst)
        return dst
    return None


def apply(write=True):
    """把官方值套进数值表。返回 [(表名, 覆盖格子数)]"""
    report = []
    for path, key, snapname in TABLES:
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8-sig', newline='') as f:
            rd = csv.reader(f)
            rows = list(rd)
        if not rows:
            continue
        header = rows[0]
        idx = {c: i for i, c in enumerate(header)}
        if key not in idx:
            report.append((os.path.basename(path), -1))
            continue
        n = 0
        for row in rows[1:]:
            rn = row[idx[key]]
            for (r, col), val in OFFICIAL.items():
                if r != rn or col not in idx:
                    continue
                row[idx[col]] = ('%g' % val) if isinstance(val, (int, float)) else str(val)
                n += 1
        if write and n:
            _snapshot(path, snapname)
            with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                csv.writer(f).writerows(rows)
        report.append((os.path.basename(path), n))
    return report


if __name__ == '__main__':
    check = '--check' in sys.argv
    if not OFFICIAL:
        print('没读到 %s，先跑 build_official_overrides.py' % OVERRIDE_CSV)
        raise SystemExit(1)
    print('覆盖表：%d 个格子，涉及 %d 行：%s'
          % (len(OFFICIAL), len(covered_rows()), '、'.join(covered_rows())))
    for n in NOTES:
        print('  注：%s' % n)
    for u in UNCOVERED:
        print('  未覆盖：%s' % u)
    print()
    for name, n in apply(write=not check):
        print('%s %s：%d 个格子' % ('[check]' if check else '[写入]', name, n))
