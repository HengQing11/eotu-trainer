# -*- coding: utf-8 -*-
"""生成《地下蚁国》蚁皇浆升级总表（HTML + CSV）

数据来源三方交叉验证：
  1) 游戏主程序 EotU-Win64-Shipping.exe 里的字段名（64 个改进项 + 9 个等级上限）
  2) 玩家存档 Colony1.sav / Freeplay1-2.sav 的实际字段（Bool=适应性开关, Int=改进等级）
  3) 官方 wiki 的 Formicarium Adaptation 页（花费 / 等级 / 效果 / 微调数值）
"""
import csv, io, os, sys, re

HERE = os.path.dirname(os.path.abspath(__file__))
MODDIR = os.path.abspath(os.path.join(HERE, '..'))

# 每个单位:
#   zh/en        名称
#   unlock       解锁花费说明
#   variant      变体开关字段(可选)
#   adapt        适应性 4 选 2: (显示名, 花费, 类型, 效果, 存档Bool字段)
#   minor        微调(IP): (属性, 每点效果, 存档Int字段, 字段后缀类型)
#   maxlv        等级上限字段
UNITS = [
 dict(zh='蚁后', en='Queen', unlock='无需解锁（开局即有）',
      variant=None, maxlv=None,
      adapt=[
        ('Second wind 二次风', 50, 'Ability', '血量降到 75% 时触发：无敌 30 秒，5 秒内回复 300 HP。冷却 300', 'bGeneTheifQueenSecondWind'),
        ('Fierce mother 狂暴母体', 50, 'Ability', '血量降到 75% 时触发：半径 2600 内敌人混乱 10 秒。冷却 300', 'bGeneTheifQueenFierceMother'),
        ('（wiki 名：Royal guard 皇家卫兵）', 100, 'Ability', '血量降到 75% 时触发：每个蚁后房间立刻产出 2 只皇家卫兵、仅存活 60 秒；5 秒内产卵不需食物与工蚁。冷却 300', 'bGeneTheifQueenStrongCarpiece'),
        ('（wiki 名：Royal decree 皇家敕令）', 100, 'Ability', '血量降到 75% 时触发：20 秒内产卵不需食物与工蚁。冷却 300', 'bGeneTheifQueenResistantCarpiece'),
      ]),

 dict(zh='工蚁', en='Worker', unlock='升级：Lv2 = 10，Lv3 = 15',
      variant=None, maxlv='WorkerMaxUpgradeLevel',
      adapt=[
        ('Nimble 敏捷', 30, 'Stat', '脱战闪避 +60%；被发现的距离更短；脱战时不显示在小地图与血条上', 'bGeneTheifWorkerStrongMandibles'),
        ('Defensive 防御', 30, 'Stat', '单次最大受伤 20；物理抗性 +20%；毒抗 +20%', 'bGeneTheifWorkerStrongCarpiece'),
        ('Aggressive brood 好斗虫群', 40, 'Stat', '普攻伤害 +200%', 'bGeneTheifWorkerAggressiveBrood'),
        ('Efficient brood 高效虫群', 40, 'Stat', '移速 +40；搬运量 +10；工作完成速度 +2；走在非高速通道上不受减速与毒素影响', 'bGeneTheifWorkerEfficientBrood'),
      ]),

 dict(zh='黑蚁兵', en='Black ant soldier', unlock='解锁 Lv1 = 75；升级 Lv2 = 15，Lv3 = 20',
      variant='bBlackAnt（单位解锁）', maxlv='BlackAntMaxUpgradeLevel',
      adapt=[
        ('Dangerous 危险', 50, 'Stat', '普攻攻速 +20%', 'bBlackAntDangerous'),
        ('Meat wall 肉盾', 50, 'Stat', '物理抗性 +50%', 'bBlackAntMeatWall'),
        ('Self preservation 自保', 70, 'Ability', '血量降到 40% 时触发：脱离战斗 0.5 秒', 'bBlackAntSelfPreservation'),
        ('Self repair 自修', 70, 'Stat', '治疗速度 +4', 'bBlackAntSelfRepair'),
      ]),

 dict(zh='木蚁射手', en='Wood ant shooter', unlock='解锁 Lv1 = 150；升级 Lv2 = 30，Lv3 = 40',
      variant='bWoodAnt / bWoodAntMelee / bWoodAntVarient（射手 / 近战 二选一）', maxlv='WoodAntMaxUpgradeLevel',
      adapt=[
        ('Corrosive 腐蚀', 80, 'Effect', '酸液额外造成毒伤：迫击型每 0.1 秒 1.2、持续 0.5 秒；速射型每 0.1 秒 0.2', 'bWoodAntCorrosive'),
        ('High pressure 高压', 80, 'Effect', '酸液额外物理伤害：迫击型 +4.5；速射型 +0.75', 'bWoodAntHighPressure'),
        ('Crippling 致残', 100, 'Effect', '目标受到的物理伤害 +40%（迫击 1.5 秒 / 速射 0.4 秒）；可叠加至 +100%', 'bWoodAntCrippling'),
        ('Weakening 弱化', 100, 'Effect', '目标受到的毒伤 +40%（迫击 1.5 秒 / 速射 0.4 秒）；可叠加至 +100%', 'bWoodAntWeakening'),
      ]),

 dict(zh='切叶蚁大工', en='Leafcutter ant major', unlock='解锁 Lv1 = 300；升级 Lv2 = 50，Lv3 = 60',
      variant='bLeafcutterMedia / bLeafcutterMajor / bLeafcutterVarient / bLeafcutterSuperMajor', maxlv='LeafcutterMaxUpgradeLevel',
      adapt=[
        ('Durable 坚韧', 100, 'Stat', '护甲 +3', 'bLeafcutterDurable'),
        ('Shockproof 抗震', 100, 'Stat', '单次最大受伤 20', 'bLeafcutterShockProof'),
        ('Sharp 锋利', 200, 'Ability', '半径 250 内的友军把所受伤害的 30% 反弹给攻击者', 'bLeafcutterSharp'),
        ('Resilient 恢复', 200, 'Ability', '半径 250 内的友军物理抗性与毒抗 +30%', 'bLeafcutterResilient'),
      ]),

 dict(zh='火蚁兵', en='Fire ant soldier', unlock='解锁 Lv1 = 500；升级 Lv2 = 70，Lv3 = 80',
      variant='bFireAnt（单位解锁）/ bFireAntVarient（变体）', maxlv='FireAntMaxUpgradeLevel',
      adapt=[
        ('Surefooted 稳足', 200, 'Stat', '骑乘蜇刺伤害 +10', 'bFireAntSurefooted'),
        ('Evasive 闪避', 200, 'Stat', '闪避 +30%', 'bFireAntEvasive'),
        ('Last stand 背水一战', 300, 'Ability', '血量归零且未骑乘时触发：0.5 秒内回复 50 HP，攻速只剩 50%，5 秒后阵亡。冷却 15', 'bFireAntLastStand'),
        ('Last laugh 临死一击', 300, 'Ability', '血量归零且未骑乘时触发：造成 20 毒伤。冷却 60', 'bFireAntLastLaugh'),
      ]),

 dict(zh='马塔贝勒医疗蚁', en='Matabele ant medic', unlock='解锁 Lv1 = 800；升级 Lv2 = 90，Lv3 = 100',
      variant='bMatabeleAnt / bMatabeleAntVariant / bMatabeleAntSoldier', maxlv='MatabeleAntMaxUpgradeLevel',
      adapt=[
        ('Sustain 维持', 400, 'Effect', '未骑乘时每次攻击后治疗半径 250 内友军 3 HP', 'bMatabeleAntSustain'),
        ('Preserve 保全', 400, 'Ability', '半径 250 内友军脱战回血速度 +1 HP/秒，最多叠 5 层', 'bMatabeleAntPreserve'),
        ('Field medic 战地医疗', 600, 'Stat', '拾取阵亡蚂蚁 5 秒后立刻复活它', 'bMatabeleAntFieldMedic'),
        ('Surgeon 外科医生', 600, 'Stat', '被复活的蚂蚁保留 85% 生命与伤害（配合 Field medic）', 'bMatabeleAntSurgeon'),
      ]),

 dict(zh='子弹蚁兵', en='Bullet ant soldier', unlock='仅解锁 Lv3 = 2000',
      variant='bBulletAnt（单位解锁）', maxlv='BulletAntMaxUpgradeLevel',
      adapt=[
        ('Lean pupation 精简羽化', 600, 'Stat', '孵化花费 -100', 'bBulletAntLeanPupation'),
        ('Fast recovery 快速恢复', 600, 'Stat', '治疗速度 +10', 'bBulletAntFastRecovery'),
        ('Reinforced carapace 强化甲壳', 700, 'Stat', '护甲 +1', 'bBulletAntReinforcedCarapace'),
        ('Sealed carapace 密封甲壳', 700, 'Stat', '毒抗 +50%', 'bBulletAntSealedCarapace'),
      ]),

 dict(zh='爆炸蚁小兵', en='Exploding ant minor soldier', unlock='解锁 Lv1 = 800；升级 Lv2 = 90，Lv3 = 100',
      variant='bExplodingAntSoldier（单位解锁）', maxlv='ExplodingAntSoldierMaxUpgradeLevel',
      adapt=[
        ('Controlled blast 可控爆破', 400, 'Stat', '爆炸伤害 +50%；毒液分泌伤害 +50%', 'bExplodingAntSoldierControlledBlast'),
        ('Violent blast 剧烈爆破', 400, 'Stat', '爆炸半径 +50%；毒液分泌半径 +50%', 'bExplodingAntSoldierViolentBlast'),
        ('Chain reaction 连锁反应', 600, 'Effect', '爆炸使附近爆炸蚁小兵的爆炸伤害 +20%，可叠加', 'bExplodingAntSoldierChainReaction'),
        ('Persistent secretions 持久分泌', 600, 'Effect', '爆炸在地面留下毒液，半径 200，每秒造成相当于爆炸伤害 12.5% 的毒伤，持续 4 秒', 'bExplodingAntSoldierPersistentSecretions'),
      ]),

 dict(zh='爆炸白蚁工', en='Exploding termite worker', unlock='解锁 Lv1 = 500；升级 Lv2 = 70，Lv3 = 80',
      variant='bExplodingTermiteWorker（单位解锁）', maxlv='ExplodingTermiteWorkerMaxUpgradeLevel',
      adapt=[
        ('Rapid maturity 快速成熟', 300, 'Stat', '成熟时间 -50%', 'bExplodingTermiteWorkerRapidMaturity'),
        ('Accelerated gland filling 加速腺体充能', 300, 'Stat', '最大增益时间 -50%', 'bExplodingTermiteWorkerRapidGladFilling'),
        ('Extreme toxins 极限毒素', 400, 'Stat', '持续伤害时长 +50%', 'bExplodingTermiteWorkerExtremeToxins'),
        ('Extreme confusion 极限混乱', 400, 'Stat', '混乱时长 +50%', 'bExplodingTermiteWorkerExtremeConfusion'),
      ]),

 # ---------- 进阶单位：只有 Lv3 解锁 + 微调，没有适应性 ----------
 dict(zh='木蚁兵（近战型）', en='Wood ant soldier', unlock='仅解锁 Lv3 = 120',
      variant='bWoodAntMelee', maxlv=None, adapt=[]),

 dict(zh='切叶蚁中工', en='Leafcutter ant media', unlock='仅解锁 Lv3 = 240',
      variant='bLeafcutterMedia', maxlv=None, adapt=[]),

 dict(zh='马塔贝勒兵蚁', en='Matabele ant soldier', unlock='仅解锁 Lv3 = 600',
      variant='bMatabeleAntSoldier', maxlv=None, adapt=[]),

 dict(zh='白蚁小兵', en='Termite minor soldier', unlock='仅解锁 Lv3 = 400',
      variant='bTermiteSoldier', maxlv=None, adapt=[]),

 dict(zh='白蚁大兵', en='Termite major soldier', unlock='仅解锁 Lv3 = 600',
      variant='bTermiteMajorSoldier', maxlv=None, adapt=[]),

 dict(zh='爆炸蚁大兵', en='Exploding ant major soldier', unlock='仅解锁 Lv3 = 500',
      variant='bExplodingAntMajorSoldier', maxlv=None, adapt=[]),

 dict(zh='爆炸白蚁兵', en='Exploding termite soldier', unlock='仅解锁 Lv3 = 500',
      variant='bExplodingTermiteSoldier', maxlv=None, adapt=[]),
]

# ---------------------------------------------------------------------------
#  每个单位的属性微调项（minor）从《升级项字段库.csv》读，不再写在这里。
#  CSV 是升级字段的唯一权威源（见 field_lib.py）。
#  以后要加新字段：在 mod\升级项字段库.csv 末尾加一行、填好单位与每点效果，
#  这里和另外两个脚本都会自动长出来，不用改代码。
# ---------------------------------------------------------------------------
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import field_lib as _fl                                              # noqa: E402

for _u in UNITS:
    _u['minor'] = [(f.item, f.per, f.name)
                   for f in _fl.for_unit(_u['zh'], _fl.KIND_IP)]

# 蚁巢级（挑战关卡用）环境抗性升级
ENV = [('HeatResistanceUpgradeLevel', '耐热'),
       ('LaserReflectivityUpgradeLevel', '激光反射'),
       ('ElectricalGroundingUpgradeLevel', '电气接地'),
       ('ChemicalResistanceUpgradeLevel', '化学抗性')]

# 非蚁巢物种解锁开关（自定义局面可用，非蚁皇浆升级）
SPECIES_UNLOCK = ['bSlaveMaker', 'bTrapjaw', 'bArmyAnt', 'bArmyAntMajor',
                  'bBigHeadedMajor', 'bBigHeadedSuperSoldier', 'bLittleBlackAnt',
                  'bTermiteSoldier', 'bTermiteMajorSoldier', 'bTermiteMajorWorker',
                  'bDriverAntWorker', 'bDriverAntSoldier', 'bDriverAntLargeSoldier',
                  'bStinkAnt']

# ============================================================================
#  当前游戏数值层：从 CreatureStats 数据表取每个单位 Lv1/Lv2/Lv3 的实际数值
#  主表 = 战役模式（Formicarium），CreatureStats_Freeplay = 自定义模式
# ============================================================================
STORY_CSV = os.path.join(MODDIR, '物种数值表_CreatureStats.csv')
FREE_CSV = os.path.join(MODDIR, 'CreatureStats_Freeplay.csv')

# 展示列: (CSV 列名, 表头, 显示方式)
#   'num' 普通数值 / 'pct' 0~1 存成百分数 / 'cap' 0 表示不限制
STAT_COLS = [
    ('Health',          '生命',         'num'),
    ('AttackDamage',    '普攻伤害',      'num'),
    ('AttackSpeed',     '攻速系数',      'num'),
    ('Speed',           '移速',         'num'),
    ('Armour',          '护甲',         'num'),
    ('PhysicalResist',  '物抗',         'pct'),
    ('VenomResist',     '毒抗',         'pct'),
    ('AOEResist',       'AOE抗',       'pct'),
    ('Evasion',         '闪避',         'pct'),
    ('Piercing',        '穿刺',         'pct'),
    ('MaxSingleDamage', '单次最大受伤',   'cap'),
    ('HealthPerSecond', '回血/秒',       'num'),
    ('DigAmmount',      '挖掘量',       'num'),
    ('FoodCarryMax',    '搬运上限',      'num'),
    ('TargetRadius',    '视野半径',      'num'),
    ('PointValue',      '点数',         'num'),
]


def _load(fp, key):
    if not os.path.exists(fp):
        return {}
    return {r[key]: r for r in csv.DictReader(open(fp, encoding='utf-8-sig'))}


STORY = _load(STORY_CSV, 'ID(游戏内部名)')
FREE = _load(FREE_CSV, 'RowName')


def fmt(v, kind):
    if v is None or v == '':
        return '—'
    try:
        f = float(v)
    except ValueError:
        return str(v)
    if kind == 'pct':
        return ('%g%%' % round(f * 100, 1))
    if kind == 'cap':
        return '不限' if f == 0 else '%g' % round(f, 2)
    if f == int(f):
        return '%d' % int(f)
    return ('%.2f' % f).rstrip('0').rstrip('.')


def rows_of(base):
    return [base + str(i) for i in (1, 2, 3)]


# 单位 -> (数据表行名列表, 备注)  行名为 3 条即 Lv1/2/3
UNIT_STATS = {
    '蚁后':           (['Queen1'], '蚁后在数据表里只有一行（没有 Lv2/Lv3）'),
    '工蚁':           (rows_of('WorkerAnt'), ''),
    '黑蚁兵':         (rows_of('BlackAnt'), ''),
    '木蚁射手':        (rows_of('WoodAntA'), '远程酸液伤害不在本表（存在 Abilities 技能表里），这里显示的是普攻。迫击型；速射型（WoodAntB）数值完全相同'),
    '切叶蚁大工':      (rows_of('LeafcutterMajorTaunt'), '嘲讽型。震晕型（LeafcutterMajorStun）数值完全相同'),
    '火蚁兵':         (rows_of('FireAntVigorous'), '勇猛型。扩散型（FireAntPervasive）数值完全相同'),
    '马塔贝勒医疗蚁':   (rows_of('MatabeleMedicAnesthetist'), '麻醉师型。快速响应型移速 400/410/420、Lv3 多 40% 脱战闪避'),
    '子弹蚁兵':        (rows_of('BulletAnt'), ''),
    '爆炸蚁小兵':      (rows_of('ExplodingAntSoldier'), ''),
    '爆炸白蚁工':      (rows_of('ExplodingTermiteWorker'), ''),
    '木蚁兵（近战型）': (rows_of('WoodAntMelee'), ''),
    '切叶蚁中工':      (rows_of('LeafcutterMedia'), ''),
    '马塔贝勒兵蚁':     (rows_of('MatabeleSoldier'), ''),
    '白蚁小兵':        (rows_of('TermiteSoldier'), ''),
    '白蚁大兵':        (rows_of('TermiteMajorSoldier'), ''),
    '爆炸蚁大兵':      (rows_of('ExplodingAntMajorSoldier'), ''),
    '爆炸白蚁兵':      (rows_of('ExplodingTermiteSoldier'), ''),
}

# 14 个「其他物种」解锁开关 -> (中文名, 数据表行名)
SPECIES_STATS = [
    ('bSlaveMaker',           '奴役蚁兵（造奴）',  rows_of('SlaveMakerAnt')),
    ('bTrapjaw',              '陷阱颚蚁兵',      rows_of('TrapjawAnt')),
    ('bArmyAnt',              '行军蚁（中型）',   rows_of('ArmyAnt')),
    ('bArmyAntMajor',         '行军蚁大兵',      rows_of('ArmyAntMajor')),
    ('bBigHeadedMajor',       '大头蚁兵',        rows_of('BigHeadedMajor')),
    ('bBigHeadedSuperSoldier', '大头蚁超级兵',    rows_of('BigHeadedSuperSoldier')),
    ('bLittleBlackAnt',       '小黑蚁',          rows_of('LittleBlackAnt')),
    ('bTermiteSoldier',       '白蚁小兵',        rows_of('TermiteSoldier')),
    ('bTermiteMajorSoldier',  '白蚁大兵',        rows_of('TermiteMajorSoldier')),
    ('bTermiteMajorWorker',   '白蚁大工',        rows_of('TermiteMajorWorker')),
    ('bDriverAntWorker',      '矛蚁工',          rows_of('DriverAntWorker')),
    ('bDriverAntSoldier',     '矛蚁兵',          rows_of('DriverAntSoldier')),
    ('bDriverAntLargeSoldier', '矛蚁大兵',        rows_of('DriverAntLargeSoldier')),
    ('bStinkAnt',             '臭蚁',            rows_of('StinkAnt')),
]

# ── 已知被第三方 mod 改过、不是原版数值的行 ────────────────────────────────
# 定性证据（三重，互相印证）：
#   1) mod 自带的名称表把自己这几项显示名改成了 Baby / Small / Medium / Large spiny devil，
#      科学名统一改成 Panacanthus varius（刺魔螽斯）——只涉及 3 个物种
#   2) mod 包只带了这 3 个物种的蓝图：LittleBlackAnt×5、TrapjawAnt×2、SlaveMaker×3
#   3) 这 9 行数值与官方 wiki 的原版值差距很大（对照见 WIKI_ORIG）
# 同物种的另外 2 行（LittleBlackAntQueen1 / SlaverAnt1）与 wiki 逐项吻合 → 未被改动
MODDED_ROWS = {
    'LittleBlackAnt1', 'LittleBlackAnt2', 'LittleBlackAnt3',
    'TrapjawAnt1', 'TrapjawAnt2', 'TrapjawAnt3',
    'SlaveMakerAnt1', 'SlaveMakerAnt2', 'SlaveMakerAnt3',
}

# ── 官方原值（唯一权威源：mod/官方数值_覆盖表.csv）─────────────────────────
#  下面这 3 个物种的 9 行，最早是从社区 mod 包里解析出来的、被该作者改写过的值。
#  现已按**官方 wiki** 换成原值：数值表本身由 scripts/official_overrides.py 修正，
#  修正前的「来自 mod 包」原始表备份在 sources/ 下，这里读它来做对照。
#   行名前缀 -> (中文名, {等级: {CSV列: 官方值}}, 出处)
import official_overrides as _OO                                    # noqa: E402

ORIG_ZH = {'TrapjawAnt': '陷阱颚蚁兵', 'SlaveMakerAnt': '奴役蚁兵',
           'LittleBlackAnt': '小黑蚁兵'}
OFFICIAL_BASE = _OO.orig_by_base()
WIKI_ORIG = {base: (ORIG_ZH.get(base, base), lvmap, _OO.source_of(base + '1'))
             for base, lvmap in sorted(OFFICIAL_BASE.items())}
OFFICIAL_HEAD = _OO.NOTES
OFFICIAL_HOLES = _OO.HOLES
SNAPDIR = os.path.join(MODDIR, 'sources')


def _snapshot(fp, name):
    """读「来自 mod 包」的原始表；不存在则回退到当前表"""
    p = os.path.join(SNAPDIR, name)
    return _load(p if os.path.exists(p) else fp, 'ID(游戏内部名)' if '物种' in name
                 else 'RowName')


def diff_note(rows):
    """主表与自定义模式表的差异（只挑展示列里有意义的），带 Lv 前缀"""
    out = []
    multi = (len(rows) == 3)
    for i, rn in enumerate(rows, 1):
        a, b = STORY.get(rn), FREE.get(rn)
        if not a or not b:
            continue
        lv = ('Lv%d ' % i) if multi else ''
        for col, zh, kind in STAT_COLS:
            if a[col] != b[col]:
                out.append('%s%s：战役 %s → 自定义 %s' % (lv, zh, fmt(a[col], kind), fmt(b[col], kind)))
    return out


def stat_table_html(rows, title='等级'):
    """渲染一个单位的 Lv1/2/3 数值表"""
    h = io.StringIO()
    have = [rn for rn in rows if rn in STORY]
    if not have:
        return ''
    h.write('<div class="scroll"><table class="tbl2">\n<tr><th class="lv">%s</th>' % title)
    for col, zh, kind in STAT_COLS:
        h.write('<th>%s</th>' % zh)
    h.write('</tr>\n')
    for i, rn in enumerate(have, 1):
        lv = 'Lv%d' % i if len(have) == 3 else '唯一档'
        r = STORY[rn]
        cls = ' class="modded"' if rn in MODDED_ROWS else ''
        h.write('<tr%s><td class="lv"><span>%s</span><br><small class="f">%s</small></td>' % (cls, lv, rn))
        for col, zh, kind in STAT_COLS:
            h.write('<td>%s</td>' % fmt(r[col], kind))
        h.write('</tr>\n')
    h.write('</table></div>\n')
    dn = diff_note(have)
    if dn:
        h.write('<p class="sub">自定义模式差异：%s</p>\n' % '；'.join(dn))
    return h.getvalue()


ALL_FIELDS = []
for u in UNITS:
    for a in u['adapt']:
        ALL_FIELDS.append((a[4], 'BoolProperty', u['zh']))
    for m in u['minor']:
        ALL_FIELDS.append((m[2], 'IntProperty', u['zh']))
    if u['maxlv']:
        ALL_FIELDS.append((u['maxlv'], 'IntProperty', u['zh'] + '（等级上限）'))


def build_html(path):
    h = io.StringIO()
    h.write('''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>地下蚁国 · 蚁皇浆升级总表</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2024;--sub:#5b6470;--line:#e3e6ea;
--acc:#7a5c2e;--acc2:#a9853f;--bool:#2f6f4f;--int:#2c5d8f;--warn:#a33;}
*{box-sizing:border-box}
body{margin:0;padding:32px 20px 60px;background:var(--bg);color:var(--ink);
font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB",-apple-system,"Segoe UI",sans-serif;
line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:27px;margin:0 0 6px;letter-spacing:.5px}
.lead{color:var(--sub);font-size:14px;margin-bottom:22px}
.lead code{background:#eef0f3;padding:1px 6px;border-radius:4px;font-size:12.5px}
.rules{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--acc2);
border-radius:10px;padding:16px 20px;margin-bottom:26px;font-size:13.5px}
.rules h2{margin:0 0 10px;font-size:15px;color:var(--acc)}
.rules ul{margin:0;padding-left:20px}
.rules li{margin:4px 0}
.rules b{color:var(--acc)}
.unit{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px 20px 6px;margin-bottom:16px}
.unit > h3{margin:0 0 2px;font-size:16.5px}
.unit > h3 small{font-weight:400;color:var(--sub);font-size:12.5px;margin-left:8px}
.meta{font-size:12.5px;color:var(--sub);margin:0 0 10px}
.meta b{color:var(--acc)}
.tagrow{margin:0 0 10px}
.tag{display:inline-block;background:#f0ece3;color:var(--acc);border-radius:20px;
padding:1px 10px;font-size:11.5px;margin:0 6px 6px 0}
table{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:12px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:#fafbfc;color:var(--sub);font-weight:600;font-size:12px;white-space:nowrap}
td.f{font-family:Consolas,Menlo,monospace;font-size:11.5px;color:var(--int);word-break:break-all}
td.cost{text-align:right;color:var(--acc);font-weight:600;white-space:nowrap}
.b{color:var(--bool);font-weight:600}
.i{color:var(--int);font-weight:600}
.sub{color:var(--sub);font-size:12px}
.note{background:#fff8e6;border:1px solid #f0dfae;border-radius:8px;padding:12px 16px;
font-size:13px;margin:20px 0}
.note b{color:#8a6a1f}
.scroll{overflow-x:auto;margin:0 0 8px}
table.tbl2{font-size:12px;margin-bottom:4px;min-width:100%}
table.tbl2 th,table.tbl2 td{padding:5px 7px;white-space:nowrap;text-align:right}
table.tbl2 th{position:sticky;top:0}
table.tbl2 th.lv,table.tbl2 td.lv{text-align:left;position:sticky;left:0;background:var(--card);
box-shadow:1px 0 0 var(--line)}
table.tbl2 td.lv span{font-weight:600;color:var(--acc)}
table.tbl2 td.lv small{color:var(--sub);font-size:10.5px;font-family:Consolas,Menlo,monospace}
table.tbl2 tr.modded td{background:#fff4f4}
table.tbl2 tr.modded td.lv{background:#fff4f4}
.stathead{font-size:12.5px;color:var(--acc);font-weight:600;margin:12px 0 4px}
h2.sec{font-size:18px;margin:34px 0 12px;padding-bottom:7px;border-bottom:2px solid var(--line)}
footer{margin-top:36px;color:var(--sub);font-size:12px;text-align:center}
</style></head><body><div class="wrap">
<h1>地下蚁国 · 蚁皇浆（Royal Jelly）升级总表</h1>
<p class="lead">按蚂蚁单位分组 · 含花费 / 效果 / 对应存档字段。数据来自三方交叉验证：游戏主程序字段名、
你本机存档实际字段、官方 Hooded Horse wiki。</p>

<h2 class="sec">一、主力单位（有适应性 + 属性微调）</h2>
''')

    for u in UNITS:
        if not u['adapt']:
            continue
        h.write('<div class="unit">\n<h3>%s<small>%s</small></h3>\n' % (u['zh'], u['en']))
        h.write('<p class="meta"><b>解锁/升级花费：</b>%s</p>\n' % u['unlock'])
        if u['variant']:
            h.write('<div class="tagrow"><span class="tag">存档开关：%s</span></div>\n' % u['variant'])
        rows, note = UNIT_STATS.get(u['zh'], (None, ''))
        if rows:
            h.write('<p class="stathead">当前游戏数值（Lv1 / Lv2 / Lv3）</p>\n')
            h.write(stat_table_html(rows))
            if note:
                h.write('<p class="sub">%s</p>\n' % note)
        if u['adapt']:
            h.write('<table><tr><th>适应性（4 选 2）</th><th>花费</th><th>类型</th><th>效果</th><th>存档字段（Bool）</th></tr>\n')
            for name, cost, typ, eff, field in u['adapt']:
                h.write('<tr><td>%s</td><td class="cost">%d</td><td class="sub">%s</td><td>%s</td>'
                        '<td class="f"><span class="b">%s</span></td></tr>\n' % (name, cost, typ, eff, field))
            h.write('</table>\n')
        h.write('<table><tr><th>可微调属性（IP）</th><th>每点效果</th><th>存档字段（Int）</th><th>值域</th></tr>\n')
        for attr, per, field in u['minor']:
            h.write('<tr><td>%s</td><td>%s</td><td class="f"><span class="i">%s</span></td>'
                    '<td class="sub">0 ~ 上限（可自定义）</td></tr>\n' % (attr, per, field))
        h.write('</table>\n')
        if u['maxlv']:
            h.write('<p class="sub">等级上限字段：<span class="f">%s</span></p>\n' % u['maxlv'])
        h.write('</div>\n')

    h.write('<h2 class="sec">二、进阶单位（只有 Lv3 解锁 + 属性微调，无适应性）</h2>\n')
    for u in UNITS:
        if u['adapt']:
            continue
        h.write('<div class="unit">\n<h3>%s<small>%s</small></h3>\n' % (u['zh'], u['en']))
        h.write('<p class="meta"><b>解锁花费：</b>%s</p>\n' % u['unlock'])
        if u['variant']:
            h.write('<div class="tagrow"><span class="tag">存档开关：%s</span></div>\n' % u['variant'])
        rows, note = UNIT_STATS.get(u['zh'], (None, ''))
        if rows:
            h.write('<p class="stathead">当前游戏数值（Lv1 / Lv2 / Lv3）</p>\n')
            h.write(stat_table_html(rows))
            if note:
                h.write('<p class="sub">%s</p>\n' % note)
        h.write('<table><tr><th>可微调属性（IP）</th><th>每点效果</th><th>存档字段（Int）</th><th>值域</th></tr>\n')
        for attr, per, field in u['minor']:
            h.write('<tr><td>%s</td><td>%s</td><td class="f"><span class="i">%s</span></td>'
                    '<td class="sub">0 ~ 上限（可自定义）</td></tr>\n' % (attr, per, field))
        h.write('</table>\n</div>\n')

    # ── 已删除（2026-09-16，按用户要求）────────────────────────────────
    # 「三、蚁巢级环境抗性升级」：只在实验室那个特定关卡里有用，而且那一关的蚁皇浆是
    #   BOSS 在关卡过程中发给你的，与蚁巢里自己攒/自己买的那套不是一回事 —— 不属本表范围。
    # 「四、改哪里 · 怎么改」「五、这些数值从哪来」：用户要求删掉。
    # 另外「其他物种解锁开关」与「附：被 mod 改过的 9 行」已于 2026-09-15 删除
    #   （那 14 个物种不能用蚁皇浆升级）。
    # 结果：本表只剩「一、主力单位」+「二、进阶单位」，恰好都是能用蚁皇浆买到的。
    h.write('<footer>生成自本机游戏文件 + 存档 + 官方 wiki 交叉验证</footer>\n'
            '</div></body></html>\n')

    open(path, 'w', encoding='utf-8').write(h.getvalue())


def build_csv(path):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['单位(中)', '单位(英)', '类别', '项目名', '蚁皇浆花费', '类型', '效果', '存档字段名', '字段类型', '值域'])
        for u in UNITS:
            for name, cost, typ, eff, field in u['adapt']:
                w.writerow([u['zh'], u['en'], '适应性(4选2)', name, cost, typ, eff, field, 'BoolProperty', 'true / false'])
            for attr, per, field in u['minor']:
                w.writerow([u['zh'], u['en'], '属性微调(IP)', attr, '每次×1.15', '-', per, field, 'IntProperty', '0 ~ 上限'])
            if u['maxlv']:
                w.writerow([u['zh'], u['en'], '等级上限', u['maxlv'], '-', '-', '该单位可买到的最多级数', u['maxlv'], 'IntProperty', '0 ~ 上限'])
        # 注：不再输出「14 个其他物种解锁开关」的字段行 —— 那些物种不能用蚁皇浆升级，
        # 已从本表删除。字段本身仍在 `升级项字段库.csv` 里（修改器改存档要用）。


def build_stats_csv(path):
    """单位基础数值对照表：单位 × 等级 × 全部展示属性"""
    header = ['分组', '单位(中)', '单位(英)', '数据表行名', '等级']
    header += [zh for _, zh, _ in STAT_COLS]
    header += ['战役/自定义差异', '备注']
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        items = []
        for u in UNITS:
            rows, note = UNIT_STATS.get(u['zh'], (None, ''))
            if rows:
                items.append(('蚁皇浆单位', u['zh'], u['en'], rows, note))
        for grp, zh, en, rows, note in items:
            have = [r for r in rows if r in STORY]
            for i, rn in enumerate(have, 1):
                lv = 'Lv%d' % i if len(have) == 3 else '唯一档'
                r = STORY[rn]
                line = [grp, zh, en, rn, lv] + [fmt(r[c], k) for c, _, k in STAT_COLS]
                line += ['；'.join(diff_note([rn])) or '', note]
                w.writerow(line)


# 说明：原来还有一个 build_orig_csv()，输出「被 mod 改过的那 9 行 · 原版对照」。
# 那 9 行属于**不能**用蚁皇浆升级的物种，已按用户要求从交付物里删除。
# 它们与官方原值的对照仍保留在 mod/官方数值_覆盖表.csv，原始表备份在 sources/。


if __name__ == '__main__':
    out = os.path.dirname(os.path.abspath(__file__))
    out = os.path.abspath(os.path.join(out, '..'))
    # 交付物只保留一份 HTML: 本脚本产出「分表」放进 sources/，由 merge_html.py 合并
    src = os.path.join(out, 'sources')
    os.makedirs(src, exist_ok=True)
    html = os.path.join(src, '蚁皇浆升级总表.html')
    csvp = os.path.join(out, '蚁皇浆升级项_字段对照.csv')
    statsp = os.path.join(out, '单位基础数值对照.csv')
    build_html(html)
    build_csv(csvp)
    build_stats_csv(statsp)
    print('HTML ->', html)
    print('CSV  ->', csvp)
    print('CSV2 ->', statsp)
    print('单位数:', len(UNITS), ' 字段总数:', len(ALL_FIELDS))
    print('  Bool:', sum(1 for x in ALL_FIELDS if x[1] == 'BoolProperty'),
          ' Int:', sum(1 for x in ALL_FIELDS if x[1] == 'IntProperty'))
