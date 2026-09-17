"""读取用户「二周目」存档的真实内容，生成实际生效数值报告

数据来源（全部本机实测）：
  1. C:/Users/beimo/AppData/Local/EotU/Saved/SaveGames/Colony1.sav  —— 当前在用的蚁巢存档
  2. mod/物种数值表_CreatureStats.csv                               —— 游戏基础数值表（战役版）
  3. mod/升级项字段库.csv                                            —— 每个升级字段的含义（唯一权威源）

字段含义一律走 field_lib / jelly_calc，本脚本里不再手写任何"字段 -> 单位/属性"映射。
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
MOD = os.path.abspath(os.path.join(HERE, '..'))

import jelly_calc as JC                                  # noqa: E402
from field_lib import all_fields                          # noqa: E402

SAVES = JC.SAVES
CUR = JC.CUR
NG0 = JC.NG0

LEVEL_ZH = {'1': 'Lv1', '2': 'Lv2', '3': 'Lv3'}

# 字段含义（属于哪个单位、哪个项目、每点效果、对应数值表哪一行哪一列）
# 全部来自《升级项字段库.csv》，取用见 field_lib.all_fields() / jelly_calc。
#
# 以前这里是两张手写映射表 + 两个手写集合：
#   FIELD_ROW        只有 8 条 —— 存档里出现没登记的字段就被**静默漏掉**
#                    （切叶蚁中工那 85 点正是这么丢的，2026-09-15 才发现）
#   UNLOCK_SWITCHES  手抄 30+ 个开关名，加一个漏一个
#   UNLOCK_ZH        手抄中文名
# 现在统一读 CSV：加新字段只要在 mod\升级项字段库.csv 里加一行，三个脚本自动认。


def fmt(v, pct=False):
    if pct:
        return '%+g%%' % v
    return '%+g' % v


def main():
    ints, bools = JC.read_save(CUR)
    ng0_ints, ng0_bools = JC.read_save(NG0)

    ng_level = ints.get('NewGamePlusLevel')
    done_diff = '未知'

    # 存档里所有已加点的 IP 字段（字段含义从字段库查，不再手写映射）
    ip_items = [(f.name, f.unit_zh, f.unit_en, f.item, f.per, pts)
                for f, pts in JC.points(ints)]
    total_ip = sum(x[5] for x in ip_items)

    # 对照游戏自带的轮转备份（都是更早的存盘），找出「最近一次存盘才写进去」的字段
    newer_fields, backups = JC.backups_newer(JC.points(ints))

    # 那份 NG+0 存档里缺哪几个
    missing_in_ng0 = [f for f, *_ in ip_items if f not in ng0_ints]

    # ---- 生效数值明细（算法见 jelly_calc.effective） ----
    detail = [dict(f=f, pts=pts, eff=JC.effective(f, pts)) for f, pts in JC.points(ints)]

    # ---- 生成 HTML ----
    h = []
    w = h.append
    w('''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>本周目档实际数值 · 地下蚁国</title>
<style>
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#23272e;
margin:0;padding:28px 20px 60px;line-height:1.65}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:23px;margin:0 0 6px}
.lead{color:#5b6470;font-size:13.5px;margin:0 0 22px}
h2{font-size:16.5px;margin:30px 0 10px;padding-left:10px;border-left:3px solid #4a7fd4}
.card{background:#fff;border:1px solid #e2e6ec;border-radius:10px;padding:16px 18px;margin:12px 0}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}
.kpi{background:#fff;border:1px solid #e2e6ec;border-radius:10px;padding:12px 18px;min-width:132px}
.kpi .n{font-size:21px;font-weight:700;color:#2f6fd0}
.kpi .l{font-size:12px;color:#6b7480;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13px;background:#fff}
th,td{border:1px solid #e6e9ee;padding:7px 9px;text-align:left;vertical-align:top}
th{background:#f0f3f7;font-weight:600;color:#3b4550}
.f{font-family:Consolas,Menlo,monospace;font-size:12px;color:#8a5a00;word-break:break-all}
.b{font-family:Consolas,Menlo,monospace;font-size:12px;color:#1c6b4a}
.up{color:#c0392b;font-weight:600}
.dn{color:#1e7a4d;font-weight:600}
.note{background:#fff8e6;border:1px solid #f0dfae;border-radius:8px;padding:12px 16px;font-size:13px;margin:16px 0}
.note b{color:#8a6a1f}
.warn{background:#fdf0f0;border:1px solid #f0c9c9}
.warn b{color:#a33}
.sub{color:#6b7480;font-size:12.5px}
.fix{background:#eef5ff;border:1px solid #c9dcf5}
.fix b{color:#2f6fd0}
footer{color:#8b939d;font-size:12px;margin-top:30px;text-align:center}
code{background:#f0f2f5;padding:1px 5px;border-radius:4px;font-size:12.5px}
</style></head><body><div class="wrap">
<h1>你的存档（本周目）· 实际生效数值</h1>
<p class="lead">数据全部来自你本机文件实测：<code>Colony1.sav</code>（当前在用的蚁巢存档）＋ 游戏基础数值表 ＋ 官方 wiki 的每点效果。</p>
''')

    w('<div class="kpis">')
    w('<div class="kpi"><div class="n">二周目</div><div class="l">NewGamePlusLevel = %s</div></div>' % ng_level)
    w('<div class="kpi"><div class="n">%d 点</div><div class="l">已购属性微调(IP)合计</div></div>' % total_ip)
    w('<div class="kpi"><div class="n">%d 项</div><div class="l">受影响的微调项</div></div>' % len(ip_items))
    w('</div>')

    w('<div class="note fix"><b>先修正我上次说错的一句话：</b>'
      '我上一轮说「你主蚁巢里所有升级都是 0 / 未解锁」——<b>那是错的</b>。'
      '原因是我读存档整数的偏移量算错了 4 个字节（把 <code>ArrayIndex</code> 当成了数值），'
      '所有整数都被读成 0。现已用已知值（蚁皇浆 999999）校准，'
      '下面这些才是你存档里的真实数字。</div>')

    # 一、存档读取结果
    w('<h2>一、你存档里读出来的东西（原文数字）</h2><div class="card">')
    w('<table><tr><th style="width:36%">存档字段</th><th style="width:14%">类型</th><th style="width:12%">值</th><th>含义</th></tr>')
    for field, zh, en, attr, per, pts in ip_items:
        w('<tr><td class="f">%s</td><td>Int</td><td><b>%d</b></td><td>%s · %s（每点 %s）</td></tr>'
          % (field, pts, zh, attr, per.replace('每点 ', '')))
    w('<tr><td class="f">NewGamePlusLevel</td><td>Int</td><td><b>%s</b></td><td>二周目等级（1 = 第一轮 NG+）</td></tr>' % ng_level)
    w('</table>')
    if newer_fields:
        w('<div class="note"><b>注意这几个字段是「新出现的」：</b>'
          '游戏每次存盘都会把上一版轮转备份成 <code>Colony1-backup1~5.sav</code>。'
          '下面这些字段在<b>全部 5 份备份里都找不到</b>，也就是说它们是<b>最近一次存盘才写进 '
          '<code>Colony1.sav</code> 的</b>，之前的报告自然读不到：<br>'
          + '、'.join('<code>%s</code>' % f for f in newer_fields)
          + '<br><span class="sub">对照依据：%s（共 %d 份）</span></div>'
          % (', '.join(os.path.basename(b) for b in backups), len(backups)))
    w('</div>')

    # 二、已启用适应性 / 已解锁物种（分类和中文名都来自字段库，不再手抄）
    F = all_fields()
    unlocks, adapts = JC.unlocks(bools), JC.adapts(bools)
    unk_b = JC.unknown_bools(bools)

    w('<h2>二、已解锁的物种（共 %d 个开关，全部为 true）</h2><div class="card">' % len(unlocks))
    w('<table><tr><th style="width:46%">存档字段（Bool）</th><th>对应单位</th></tr>')
    for a in unlocks:
        w('<tr><td class="b">%s</td><td>%s</td></tr>' % (a, F[a].unit_zh or '—'))
    w('</table>')
    w('<p class="sub">二周目的规则之一就是「所有物种从开局起就可用蚁皇浆解锁」，所以这里几乎全开——'
      '包括普通战役拿不到的<b>子弹蚁</b>。</p></div>')

    w('<h2>三、已启用的适应性（每个单位 2 个，共 %d 个）</h2><div class="card">' % len(adapts))
    w('<table><tr><th style="width:46%">存档字段（Bool = true）</th><th>说明</th></tr>')
    for a in adapts:
        f = F[a]
        w('<tr><td class="b">%s</td><td>%s · %s</td></tr>' % (a, f.unit_zh, f.item))
    w('</table>')
    w('<p class="sub">每个单位有 4 个适应性、同时只能启用 2 个，所以存档里只会留下你选中的那 2 个字段。</p></div>')

    if unk_b:
        w('<div class="note warn"><b>有 %d 个开关我还没登记进字段库：</b>%s'
          '<br>这些字段在你存档里是 true，但 <code>升级项字段库.csv</code> 里查不到，'
          '所以不知道它属于谁。补一行即可，下次重跑自动认。</div>'
          % (len(unk_b), '、'.join('<code>%s</code>' % x for x in unk_b)))

    # 三、实际生效数值
    w('<h2>四、这些升级让你游戏里实际变成多少</h2>')
    w('<p class="sub">基础值取自游戏数值表（战役版）；「生效值」= 基础值 + 你的 IP 加成。'
      'Lv1/2/3 对应数值表里的 <code>行名1/2/3</code>，实际用哪一档看该单位买到的等级。</p>')
    for d in detail:
        f, pts, e = d['f'], d['pts'], d['eff']
        w('<div class="card">')
        w('<p><b>%s</b> <span class="sub">（%s）· %s ＋ <b>%d 点</b></span></p>'
          % (f.unit_zh, f.unit_en, f.item, pts))
        parts = []
        for lab, _raw, pct, _delta, tot in e['variants']:
            txt = ('%+g%%' % (tot * 100)) if pct else ('%+g' % tot)
            if lab:
                txt += '（%s型）' % lab
            parts.append('<span class="%s">%s</span>' % ('up' if tot > 0 else 'dn', txt))
        calc_txt = ' ／ '.join(parts)
        w('<p>每点 %s × %d 点 = <b>%s</b></p>' % (f.per_text(), pts, calc_txt))
        if e['in_table']:
            w('<table><tr><th>等级</th><th>数据表行名</th><th>基础值</th>'
              '<th>你的加成</th><th>生效值</th></tr>')
            for rn, base, after, kind in e['rows']:
                w('<tr><td>%s</td><td class="f">%s</td><td>%s</td>'
                  '<td class="up">%s</td><td><b>%s</b></td></tr>'
                  % (LEVEL_ZH[rn[-1]], rn, fmt(base, kind), calc_txt, fmt(after, kind)))
            w('</table>')
        elif f.note:
            w('<p class="sub">注：%s；这一项基础值不在数值表里，所以只列你的加成。</p>' % f.note)
        w('</div>')

    # 四、机制说明
    w('<h2>五、二周目到底改了什么（为什么你的数值和我上次那张表不一样）</h2>')
    w('''<div class="card">
<p>结论：<b>游戏里没有「二周目专用数值表」</b>。全部数据表只有两套 —— 战役版
<code>CreatureStats</code> 和自定义版 <code>CreatureStats_Freeplay</code>。
二周目并不是换一张表，而是在同一张表的基础上多了三件事：</p>
<table>
<tr><th style="width:20%">来源</th><th style="width:44%">内容</th><th>证据</th></tr>
<tr><td><b>你的升级开始生效</b></td>
<td>官方路线图原文：二周目下「蚁后升级、物种专属升级、属性微调，都会在战役（纪录）关卡中生效」。
也就是说普通战役里你买的这些 IP 是不生效的，<b>二周目才生效</b>。</td>
<td>你存档里的 {N} 个 <code>*Improvment</code> 字段（见第一节）</td></tr>
<tr><td><b>关卡缩放</b></td>
<td>每一关有自己的 <code>ScaleLevel</code>，并有一个 <code>PreventNewGamePlusScaleLevel</code> 开关决定该关是否随 NGP 提高难度。</td>
<td>程序内字段：<code>ScaleLevel</code> / <code>PreventNewGamePlusScaleLevel</code> /
<code>NewGamePlusLevel</code> / <code>OveriddenNewGamePlusLevel</code> / <code>ApplyScaleLevelBasedScaling</code></td></tr>
<tr><td><b>敌方蚁巢开局加强</b></td>
<td>官方 4.1 更新说明：二周目下敌方蚁巢开局拿到更多食物储存与更多工蚁，<b>幅度随 NGP 等级提高</b>；小黑蚁蚁巢额外获得更多开局资源。</td>
<td>Slug Disco 官方更新公告原文</td></tr>
</table>
<div class="note"><b>读不到的部分（诚实交代）：</b><code>ScaleLevel</code> 的具体倍率写在关卡资产里，
而关卡资产封在官方那个 4.35 GB 的加密 pak 内，<b>我读不到它到底放大了百分之多少</b>。
不过你所有关卡存档里，每个生物的 <code>CreatureScaleLevel</code> 字段实测<b>全部等于 1</b>
（也就是存档里没有记录逐生物的额外缩放），所以你在游戏里看到的差异主要来自上面第一条和第三条。</div>
</div>'''.replace('{N}', str(len(ip_items))))

    # 五、另一个存档
    w('<h2>六、顺带说明：你目录里还有一份「二周目」关联存档</h2><div class="card">')
    w('<table><tr><th style="width:34%">文件</th><th style="width:16%">蚁巢名</th><th>内容对照</th></tr>')
    w('<tr><td class="f">Colony1.sav<br><span class="sub">+ Colony1LevelData.sav</span></td>'
      '<td>pp</td><td><b>你现在在用的档</b>（蚁皇浆改在这份里生效）。'
      '<code>NewGamePlusLevel = %s</code>，已解锁子弹蚁等全部物种，IP 合计 %d 点。</td></tr>' % (ng_level, total_ip))
    w('<tr><td class="f">Colony1NewGamePlus0.sav<br><span class="sub">+ Colony1LevelDataNewGamePlus0.sav</span></td>'
      '<td>pp-NewGamePlus0</td><td>另一份二周目相关存档（9 月 11 日）。蚁皇浆 2196，'
      '<b>没有</b>子弹蚁解锁、没有这 %d 个 IP 字段（%s），且多一个 <code>FreezeProgress = true</code>（冻结标记）。'
      '黑蚁兵适应性记的是 Meat wall（你现在这份是 Dangerous）。</td></tr>'
      % (len(missing_in_ng0),
         '、'.join('<code>%s</code>' % f for f in sorted(missing_in_ng0)) or '—'))
    w('</table>')
    w('<p class="sub">这份文件的字段比你现用的少，说明它是更早的状态快照（转换二周目时冻结的那份）。'
      '现在的进度都在 <code>Colony1*</code> 里。</p></div>')

    w('<footer>生成自本机 <code>Colony1.sav</code> + 游戏数值表 + 官方 wiki 交叉核对</footer>')
    w('</div></body></html>')

    # 交付物只保留一份 HTML: 本脚本产出「分表」放进 sources/，由 merge_html.py 合并
    src = os.path.join(MOD, 'sources')
    os.makedirs(src, exist_ok=True)
    out_html = os.path.join(src, '你的本周目档_实际数值.html')
    open(out_html, 'w', encoding='utf-8').write('\n'.join(h))

    # ---- CSV ----
    out_csv = os.path.join(MOD, '你的本周目档_实际数值.csv')
    with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
        cw = csv.writer(f)
        cw.writerow(['单位(中)', '单位(英)', '微调属性', '存档字段', '你的点数', '每点效果', '累计加成',
                     '数据表行名', '基础值', '生效值'])
        for d in detail:
            f, pts, e = d['f'], d['pts'], d['eff']
            def _one(tot, pct):
                return ('%+g%%' % (tot * 100)) if pct else ('%+g' % tot)
            calc_txt = ' / '.join(_one(tot, pct) for _lab, _raw, pct, _delta, tot in e['variants'])
            head = [f.unit_zh, f.unit_en, f.item, f.name, pts, f.per]
            if e['in_table']:
                for rn, base, after, _kind in e['rows']:
                    cw.writerow(head + [calc_txt, rn, '%g' % base, '%g' % after])
            else:
                cw.writerow(head + [calc_txt, '-', '-', calc_txt])
        cw.writerow([])
        cw.writerow(['NewGamePlusLevel', ng_level])
        for a in adapts:
            cw.writerow(['适应性已启用', a])

    print('HTML ->', out_html)
    print('CSV  ->', out_csv)
    print('二周目等级 =', ng_level, ' IP 合计 =', total_ip, ' 受影响项 =', len(ip_items))


if __name__ == '__main__':
    main()
