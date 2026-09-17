# -*- coding: utf-8 -*-
"""导出《升级项字段库.csv》—— 升级字段的唯一权威源

这份 CSV 记录「每个升级字段是什么意思」，是表格能自动更新的地基：
    字段名 -> 属于哪个单位 / 哪个项目 / 每点效果 / 对应基础数值表的哪一行哪一列

以前这层信息散在三个脚本里（手写映射表、手写标记、手写说明），
存档里出现一个没登记的字段就会被静默漏掉。现在统一到这张 CSV：

    以后加新字段，只改这张 CSV 一行，三处消费方自动认它。

用法:
    python build_field_lib.py            # 生成/刷新 CSV（保留已有的人工补录列）
    python build_field_lib.py --check    # 只校验：存档里有没有未登记的字段
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

from gen_jelly_table import UNITS, UNIT_STATS, SPECIES_UNLOCK  # noqa: E402

OUT = os.path.join(MOD, '升级项字段库.csv')

SAVES = r'C:/Users/beimo/AppData/Local/EotU/Saved/SaveGames/'

# 项目中文 -> 基础数值表(CreatureStats)的列名
# 留空 = 这一项不在基础数值表里（技能/特殊攻击），只能显示"加了多少点"
ATTR_COL = {
    '生命':          'Health',
    '普攻伤害':      'AttackDamage',
    '普攻攻速':      'AttackSpeed',
    '移动速度':      'Speed',
    '护甲':          'Armour',
    '物理抗性':      'PhysicalResist',
    '毒抗':          'VenomResist',
    '范围抗性':      'AOEResist',
    '脱战闪避':      'Evasion',
    '穿刺':          'Piercing',
    '单次最大受伤':   'MaxSingleDamage',
    '搬运量':        'FoodCarryMax',
    '回血/秒':       'HealthPerSecond',
    '挖掘量':        'DigAmmount',
    '视野半径':      'TargetRadius',
    '点数':          'PointValue',
}

# 明确不在基础数值表里的项目 -> 原因
NOT_IN_TABLE = {
    '技能冷却':  '技能冷却在 Abilities 技能表，不在 CreatureStats 里',
    '射程':      '射程不体现在 CreatureStats 表的展示列里',
    '酸液伤害':  '酸液伤害属技能（Abilities 表）',
    '酸液攻速':  '酸液攻速属技能（Abilities 表）',
    '骑乘伤害':  '骑乘是特殊攻击形态，数值不在 CreatureStats 表',
    '处决伤害':  '处决是特殊攻击，数值不在 CreatureStats 表',
}

# 补充备注（原来散在 gen_ngp_report.py 的 FIELD_ROW 里，迁移过来不丢信息）
EXTRA_NOTE = {
    'LeafcutterHealthImprovment': '与震晕型（Stun）数值完全相同',
}

COLS = ['字段名', '类型', '单位中文', '单位英文', '数据表行前缀',
        '项目中文', '每点效果', '数值表列', '数据来源', '备注']
# 允许人工编辑、重新生成时要保留的列
KEEP = ['数值表列', '备注']


def prefix_of(zh):
    """单位中文名 -> CreatureStats 行名前缀（如 切叶蚁中工 -> LeafcutterMedia）"""
    rows, _ = UNIT_STATS.get(zh, (None, ''))
    if not rows:
        return ''
    return re.sub(r'\d+$', '', rows[0])


def entries():
    """产出全部字段行

    分工（避免循环依赖）：
      · IP 微调行 —— 以现有 CSV 为准。CSV 自己就是权威源，
        因为 gen_jelly_table.py 的 minor 反过来要读 CSV，不能再从那儿导出。
        「数值表列」「备注」缺了就按 ATTR_COL / NOT_IN_TABLE 兜底补。
      · 适应性 / 解锁开关行 —— 从 gen_jelly_table.py 的 UNITS 刷新（描述还在代码里）。
    """
    old = load_old()
    out, seen = [], set()

    i_col = COLS.index('数值表列')
    i_item = COLS.index('项目中文')
    i_note = COLS.index('备注')

    for r in old.values():
        if (r.get('类型') or '').strip() != 'IP微调':
            continue
        row = [(r.get(c) or '').strip() for c in COLS]
        if row[0] in seen:
            continue
        if not row[i_col]:
            row[i_col] = ATTR_COL.get(row[i_item], '')
        if not row[i_note]:
            row[i_note] = (NOT_IN_TABLE.get(row[i_item], '')
                           or EXTRA_NOTE.get(row[0], ''))
        if not row[i_col] and not row[i_note]:
            row[i_note] = '未收录：这一项属于哪个数值列还没确认'
        out.append(row)
        seen.add(row[0])

    # 适应性 / 解锁开关：从 UNITS 刷新
    #
    # 注意归属歧义：有的开关被多个单位声明 ——
    #   bLeafcutterMedia 同时出现在「切叶蚁大工」和「切叶蚁中工」的 variant 里
    #   bWoodAntMelee 同时出现在「木蚁射手」和「木蚁兵（近战型）」里
    #   bMatabeleAntSoldier 同时出现在「马塔贝勒医疗蚁」和「马塔贝勒兵蚁」里
    # 语义上它属于「专门为它准备的那个单位」= 列表里靠后的进阶单位，
    # 所以这里让后面的覆盖前面的（后写胜）。
    extra, order = {}, []
    for u in UNITS:
        pre = prefix_of(u['zh'])
        for name, _cost, _kind, _effect, field in u['adapt']:
            if field not in extra:
                order.append(field)
            extra[field] = [field, '适应性', u['zh'], u['en'], pre, name, '', '',
                            'wiki + 本机存档 Bool 字段', '']
        for field in re.findall(r'\bb[A-Z][A-Za-z]*\b', u.get('variant') or ''):
            if field not in extra:
                order.append(field)
            extra[field] = [field, '解锁开关', u['zh'], u['en'], pre, '单位/变体解锁',
                            '', '', 'wiki + 本机存档 Bool 字段',
                            '解锁该单位可用，不是蚁皇浆升级项']

    # 非蚁巢物种：只补 UNITS 里没有的（白蚁小兵/大兵在 UNITS 里也有，以单位为优先）
    for field in SPECIES_UNLOCK:
        if field in extra:
            continue
        order.append(field)
        extra[field] = [field, '解锁开关', '（非蚁巢物种）', '', '', '物种解锁', '', '',
                        'wiki + 本机存档 Bool 字段',
                        '自定义局面可用，不是蚁皇浆升级项']

    for field in order:
        if field in seen:
            continue
        seen.add(field)
        out.append(extra[field])
    return out


def load_old():
    """读回已有 CSV，保住人工补的列（数值表列 / 备注）"""
    if not os.path.isfile(OUT):
        return {}
    old = {}
    for r in csv.DictReader(open(OUT, encoding='utf-8-sig')):
        f = (r.get('字段名') or '').strip()
        if f:
            old[f] = r
    return old


def write_csv(rows):
    old = load_old()
    kept = 0
    for r in rows:
        o = old.get(r[0])
        if not o:
            continue
        for i, c in enumerate(COLS):
            if c in KEEP and (o.get(c) or '').strip():
                if r[i] != o[c]:
                    kept += 1
                r[i] = o[c]
    with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(rows)
    return kept


def check(silent=False):
    """校验：存档里出现的升级字段，字段库收全了吗"""
    try:
        from sav_props import iter_tags
    except ImportError:
        return []
    known = {r[0] for r in entries()}
    known |= set(SPECIES_UNLOCK)
    unknown = set()
    for fn in sorted(os.listdir(SAVES)) if os.path.isdir(SAVES) else []:
        if not re.match(r'Colony1(-backup\d+)?\.sav$', fn):
            continue
        d = open(SAVES + fn, 'rb').read()
        for _off, name, _typ in iter_tags(d):
            if name in known:
                continue
            if name.endswith('Improvment') or name.endswith('Improvement') \
                    or (name.startswith('b') and name[1:2].isupper()):
                unknown.add(name)
    if unknown and not silent:
        print('  [待补录] 存档里有 %d 个字段没登记进字段库：' % len(unknown))
        for u in sorted(unknown):
            print('           %s' % u)
    return sorted(unknown)


def main():
    check_only = '--check' in sys.argv
    if not check_only:
        rows = entries()
        kept = write_csv(rows)
        kinds = {}
        for r in rows:
            kinds[r[1]] = kinds.get(r[1], 0) + 1
        print('已生成: %s' % OUT)
        print('  合计 %d 个字段：%s' % (
            len(rows), ' / '.join('%s %d' % (k, kinds[k]) for k in sorted(kinds))))
        print('  映射到基础数值表: %d 个' % sum(1 for r in rows if r[7]))
        if not any(r[1] == 'IP微调' for r in rows):
            print('  [错误] 字段库里没有任何 IP 微调行 —— CSV 是不是被清空/删除了？')
            print('         请先恢复 升级项字段库.csv，否则所有加点项都会认不出来。')
        if kept:
            print('  保留人工补录: %d 处' % kept)
    check()


if __name__ == '__main__':
    main()
