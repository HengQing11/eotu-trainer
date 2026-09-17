"""生成《官方数值_覆盖表.csv》—— 被第三方 mod 改过的那 9 行，官方（Hooded Horse wiki）原值。

背景
----
本项目的数值表 `物种数值表_CreatureStats.csv` 是从社区 mod《BushCricketColony》的
pak 包里解析出来的。UE4 改数据表必须**整表打包**，所以那个 mod 带来了完整 281 行，
作者动过的 9 行（小黑蚁兵 / 陷阱颚蚁兵 / 奴役蚁兵 各 Lv1-3）之外，其余 272 行是官方原值。

那 9 行必须换成官方值。来源 = 官方 wiki 的 Notable stats（Hooded Horse 是发行商，
wiki 是官方维护的）。本脚本把 wiki 数据落成 CSV，`official_overrides.py` 再拿它去
修正数值表，`gen_jelly_table.py` 拿它去渲染网页。

口径说明（重要）
----------------
- wiki 只公布「Notable stats」。没写的两列 —— **挖掘量 DigAmmount** 与
  **单次最大受伤 MaxSingleDamage** —— 本表不覆盖，仍保留来源 mod 的值，网页里会标注。
- wiki 写 "Damage modifications: None" ⇒ 护甲 / 物抗 / 毒抗 / AOE抗 / 闪避 / 穿刺
  一律按默认值 0 收录（并记在「出处」列里，便于复核）。
- wiki 的 **Attack speed 是显示值**（1.5 表示每秒 1.5 次），本表 `AttackSpeed` 列存的是
  **倍率**，换算 = 显示值 ÷ 1.5。已用未被 mod 动过的行验证过：工蚁 / 白蚁小兵 / 木蚁射手
  wiki 都写 1.5，本表都是 1 ✅。

用法
----
    python build_official_overrides.py            # 写 mod/官方数值_覆盖表.csv
    python build_official_overrides.py --check    # 只打印，不写
"""
import csv
import os
import sys

MODDIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
OUT_CSV = os.path.join(MODDIR, '官方数值_覆盖表.csv')

# 注意：DataTable 里 AttackSpeed 是倍率，wiki 显示值 ÷1.5 才是它
AS = 1.0 / 1.5

# 行名前缀 -> 官方数据
#   cols: CSV 列名 -> [Lv1, Lv2, Lv3]
WIKI = {
    'TrapjawAnt': dict(
        zh='陷阱颚蚁兵',
        src='官方 wiki「Trap-jaw Ant」→ Notable stats → Trap-jaw ant soldier',
        cost='90 [6]',
        cols={
            'Health':          [65, 75, 90],
            'AttackDamage':    [6, 8, 11],
            'AttackSpeed':     [1.5 * AS, 1.5 * AS, 1.5 * AS],   # 显示 1.5/1.5/1.5
            'Speed':           [320, 320, 320],
            'FoodCarryMax':    [15, 15, 15],           # wiki: Harvest amount
            'HealthPerSecond': [0.1, 0.1, 0.1],        # wiki: Healing speed
            'TargetRadius':    [400, 400, 400],        # wiki: Vision radius
            'PointValue':      [14, 20, 24],           # wiki: Score
            'Armour':          [0, 0, 0],
            'PhysicalResist':  [0, 0, 0],
            'VenomResist':     [0, 0, 0],
            'AOEResist':       [0, 0, 0],
            'Evasion':         [0, 0, 0],
            'Piercing':        [0, 0, 0],
        },
        note='wiki 原话：Damage modifications None、Immunities None；'
             'Attack speed 1.5/1.5/1.5（显示值）',
    ),
    'SlaveMakerAnt': dict(
        zh='奴役蚁兵',
        src='官方 wiki「Slave-maker Ant」→ Notable stats → Slave-maker ant soldier',
        cost='65 [5]',
        cols={
            'Health':          [50, 80, 120],
            'AttackDamage':    [3, 4.4, 7],
            'AttackSpeed':     [1.5 * AS, 1.8 * AS, 2.2 * AS],   # 显示 1.5/1.8/2.2
            'Speed':           [280, 300, 320],
            'FoodCarryMax':    [15, 15, 15],
            'HealthPerSecond': [0.1, 0.15, 0.2],
            'TargetRadius':    [400, 400, 400],
            'PointValue':      [15, 18, 22],
            'Armour':          [0, 0, 0],
            'PhysicalResist':  [0, 0, 0],
            'VenomResist':     [0, 0, 0],
            'AOEResist':       [0, 0, 0],
            'Evasion':         [0, 0, 0],
            'Piercing':        [0, 0, 0],
        },
        note='wiki 原话：Damage modifications None、Immunities None；'
             'Attack speed 1.5/1.8/2.2（显示值）。同页奴役蚁-偷卵者 SlaverAnt1 未被 mod 改动',
    ),
    'LittleBlackAnt': dict(
        zh='小黑蚁兵',
        src='官方 wiki「Little Black Ant」→ Notable stats → Little black ant soldier',
        cost='24 [2]',
        cols={
            'Health':          [25, 30, 40],
            'AttackDamage':    [1.5, 2, 3],
            'AttackSpeed':     [1.5 * AS, 1.5 * AS, 2.5 * AS],   # 显示 1.5/1.5/2.5
            'Speed':           [300, 300, 300],
            'FoodCarryMax':    [15, 15, 15],
            'HealthPerSecond': [0.1, 0.1, 0.1],
            'TargetRadius':    [400, 400, 400],
            'PointValue':      [5, 7, 10],
            'Armour':          [0, 0, 0],
            'PhysicalResist':  [0, 0, 0],
            'VenomResist':     [0, 0, 0],
            'AOEResist':       [0.2, 0.2, 0.2],     # wiki: Area resistance 20%
            'Evasion':         [0, 0, 0],
            'Piercing':        [0, 0, 0],
        },
        note='wiki 原话：Damage modifications 只有 Area resistance 20%/20%/20%、Immunities None；'
             'Attack speed 1.5/1.5/2.5（显示值）。'
             '⚠️ 同页「Little black ant worker（工蚁）」是另一档：'
             '生命 25/35/45、伤害 0.6/0.8/1、移速 300/340/380、点数 5/8/12 —— '
             '数据表里只有一组 LittleBlackAnt1/2/3，按兵蚁口径收录（与 mod 拿它改造成兵蚁一致）',
    ),
}

# 官方 wiki 没有公布、因此本表不覆盖的两列
UNCOVERED = [
    ('DigAmmount', '挖掘量'),
    ('MaxSingleDamage', '单次最大受伤'),
]

HEADER = ['数据表行名', 'CSV列名', '等级', '官方值', '出处']


def build_rows():
    rows = []
    for base, d in WIKI.items():
        for col, vals in d['cols'].items():
            for i, v in enumerate(vals, 1):
                rows.append(['%s%d' % (base, i), col, 'Lv%d' % i,
                             ('%g' % round(v, 6)), d['src']])
    return rows


def main():
    rows = build_rows()
    if '--check' in sys.argv:
        print('将写入 %d 条覆盖：' % len(rows))
        for r in rows[:12]:
            print('   ', r)
        print('    ...')
        return
    with open(OUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for base, d in WIKI.items():
            w.writerow(['# %s（%s）：%s；成本 %s' % (base, d['zh'], d['src'], d['cost']),
                        '', '', '', d['note']])
        for r in rows:
            w.writerow(r)
        w.writerow(['# 未覆盖', '', '', '',
                    '；'.join('%s（%s）' % (c, z) for c, z in UNCOVERED)
                    + ' —— 官方 wiki 的 Notable stats 没有公布，本表保留来源 mod 的值，网页里会标注'])
    print('写入 %s（%d 条）' % (OUT_CSV, len(rows)))
    print('物种：' + '、'.join(d['zh'] for d in WIKI.values()))


if __name__ == '__main__':
    main()
