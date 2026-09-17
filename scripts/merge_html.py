# -*- coding: utf-8 -*-
"""
把「蚁皇浆升级总表.html」与「你的二周目档_实际数值.html」合并成一份 HTML。

用法:
python merge_html.py <总表.html> <二周目档.html> <输出.html>

默认参数指向 mod/sources/ 下的两张分表:
  sources/蚁皇浆升级总表.html        ← gen_jelly_table.py 产出
  sources/你的二周目档_实际数值.html  ← gen_ngp_report.py 产出
（找不到时回退到 backup/ 里的原始单表备份）
输出默认写到 mod/蚁皇浆升级总表.html —— 交付目录里只保留这一份 HTML。

合并后结构:
  标题 + 说明 → 目录 → ★你的存档(本周目)实际数值 → 一~二 单位表(含"你已加点"标记)

  ⚠️ 原「四、其他物种解锁开关」与「附、被 mod 改过的 9 行」已删除（2026-09-15，用户要求）：
     那 14 个物种不能用蚁皇浆升级，不属于本表范围。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)

if HERE not in sys.path:
    sys.path.insert(0, HERE)

import jelly_calc as JC          # noqa: E402  存档 × 字段库 × 基础数值表
from field_lib import all_fields  # noqa: E402

SRC = os.path.join(MOD, 'sources')
DEF_A = os.path.join(SRC, '蚁皇浆升级总表.html')
DEF_B = os.path.join(SRC, '你的本周目档_实际数值.html')
ALT_A = os.path.join(MOD, 'backup', '蚁皇浆升级总表_原始单表.html')
ALT_B = os.path.join(MOD, 'backup', '你的二周目档_原始单表.html')
DEF_OUT = os.path.join(MOD, '蚁皇浆升级总表.html')


def pick(pref, alt):
    """优先用 sources/ 的分表, 没有就回退到 backup/"""
    return pref if os.path.isfile(pref) else alt


def load(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def inner_body(html):
    """取出 <body> 里的内容, 并剥掉最外层 <div class="wrap">"""
    m = re.search(r'<body[^>]*>(.*)</body>', html, re.S)
    c = m.group(1).strip()
    c = re.sub(r'^<div class="wrap">', '', c)
    c = re.sub(r'</div>$', '', c.strip())
    return c.strip()


def style_of(html):
    m = re.search(r'<style[^>]*>(.*?)</style>', html, re.S)
    return m.group(1).strip()


def add_anchor(html, h2_text, anchor_id):
    """给文字为 h2_text 的那个 <h2> 加上 id"""
    pat = re.compile(r'<h2([^>]*?)>(' + re.escape(h2_text) + r')')

    def rep(m):
        attrs = m.group(1)
        if 'id=' in attrs:
            return m.group(0)
        return '<h2%s id="%s">%s' % (attrs, anchor_id, m.group(2))

    return pat.sub(rep, html, count=1)


# ---------------------------------------------------------------- NG+ 追加样式
NGP_CSS = """
/* ===== 合并进来: 你的存档(二周目) 部分 ===== */
.ngp h2{font-size:16.5px;margin:26px 0 10px;padding-left:10px;border-left:3px solid #4a7fd4}
.ngp .card{background:#fff;border:1px solid #e2e6ec;border-radius:10px;padding:16px 18px;margin:12px 0}
.ngp .kpis{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}
.ngp .kpi{background:#fff;border:1px solid #e2e6ec;border-radius:10px;padding:12px 18px;min-width:132px}
.ngp .kpi .n{font-size:21px;font-weight:700;color:#2f6fd0}
.ngp .kpi .l{font-size:12px;color:#6b7480;margin-top:2px}
.ngp table{width:100%;border-collapse:collapse;font-size:13px;background:#fff}
.ngp th,.ngp td{border:1px solid #e6e9ee;padding:7px 9px;text-align:left;vertical-align:top}
.ngp th{background:#f0f3f7;color:#3b4550;font-weight:600;font-size:13px;white-space:normal}
.ngp td.f,.ngp .f{font-family:Consolas,Menlo,monospace;font-size:12px;color:#8a5a00;word-break:break-all}
.ngp .b{font-family:Consolas,Menlo,monospace;font-size:12px;color:#1c6b4a;font-weight:400}
.ngp .up{color:#c0392b;font-weight:600}
.ngp .dn{color:#1e7a4d;font-weight:600}
.ngp .note{background:#fff8e6;border:1px solid #f0dfae;border-radius:8px;padding:12px 16px;font-size:13px;margin:16px 0}
.ngp .note b{color:#8a6a1f}
.ngp .warn{background:#fdf0f0;border:1px solid #f0c9c9}
.ngp .warn b{color:#a33}
.ngp .sub{color:#6b7480;font-size:12.5px}
.ngp .fix{background:#eef5ff;border:1px solid #c9dcf5}
.ngp .fix b{color:#2f6fd0}
.ngp code{background:#f0f2f5;padding:1px 5px;border-radius:4px;font-size:12.5px}
"""

EXTRA_CSS = """
/* ===== 合并版新增: 目录 / 加点标记 ===== */
.toc{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px 18px 14px;margin:0 0 22px;font-size:13px}
.toc b{display:block;color:var(--acc);font-size:12.5px;letter-spacing:.5px;margin-bottom:7px}
.toc a{display:inline-block;color:#2c5d8f;text-decoration:none;margin:3px 16px 3px 0;
padding-bottom:1px;border-bottom:1px dashed #c9dcf5}
.toc a:hover{color:var(--acc);border-bottom-color:var(--acc2)}
.toc a.star{color:#b4791f;font-weight:600;border-bottom-color:#e8cf9a}
.yjbadge{background:#eef5ff;border:1px solid #c9dcf5;border-left:3px solid #2f6fd0;
border-radius:8px;padding:8px 12px;font-size:12.5px;margin:0 0 10px;color:#2c5d8f}
.yjbadge b{color:#c0392b}
.yjbadge a{color:#2f6fd0;font-weight:600;text-decoration:none;border-bottom:1px dashed #9dc0ea}
.yjbadge a:hover{color:var(--acc);border-bottom-color:var(--acc2)}
.note.pending{margin-bottom:20px}
.note.pending table{margin-top:10px;width:100%;border-collapse:collapse;font-size:12.5px;background:#fff}
.note.pending th,.note.pending td{border:1px solid #e6e9ee;padding:6px 9px;text-align:left;vertical-align:top}
.note.pending th{background:#f7ecec;color:#7a2c2c;font-weight:600}
footer code{background:#eef0f3;padding:1px 6px;border-radius:4px;font-size:12px}
"""

# ------------------------------------------------- 单位卡片上的"你已加点"标记
BADGE_LINK = ' ｜ <a href="#ngp-eff">看详细推导 →</a>'


def build_badges():
    """从存档 + 字段库**现算**「★ 你已加点」标记

    以前这里是 7 条手写死的字符串，连 220/260/420 这些数字都是手打进代码的。
    后果：你存档一变、或者给别的单位加了点，表上什么都不会发生。
    现在完全按存档现算 —— 你给哪个单位加了点，哪个单位的卡片就自动长出一条；
    加的是哪一项、加了多少，都从字段库和基础数值表里查出来。
    """
    try:
        ints, _ = JC.read_save(JC.CUR)
    except OSError as e:
        print('  [warn] 读不到存档，跳过加点标记: %s' % e)
        return []

    grouped, order = {}, []
    for f, pts in JC.points(ints):
        e = JC.effective(f, pts)
        key = (f.unit_zh, f.unit_en)
        if key not in grouped:
            grouped[key] = {'calc': [], 'noc': []}
            order.append(key)
        if e['in_table']:
            grouped[key]['calc'].append(
                '%s <b>+%d 点</b>（每点 %s = <b>%s</b>）→ %s'
                % (f.item, pts, f.per_text(),
                   JC.delta_text(f, e['variants']), JC.eff_text(e['rows'])))
        else:
            # 不在基础数值表里（技能 / 特殊攻击）：还是把总增量算给看
            # 例如蚁后的技能冷却「每点 -0.5 秒 × 20 点 = -10 秒」，
            # 没有基础值可加，但这 -10 秒本身就是有用的结论。
            d = JC.delta_text(f, e['variants'])
            grouped[key]['noc'].append(
                '%s <b>+%d 点</b>（每点 %s = <b>%s</b>）' % (f.item, pts, f.per_text(), d)
                if d else '%s <b>+%d 点</b>' % (f.item, pts))

    out = []
    for zh, en in order:
        g = grouped[(zh, en)]
        lines = ['★ 你已加点：' + s for s in g['calc']]
        if g['noc']:
            lines.append('★ 你已加点：' + '、'.join(g['noc'])
                         + ' —— 这几项属技能/特殊攻击表，不在下面这张基础属性表里')
        out.append(('<h3>%s<small>%s</small></h3>' % (zh, en),
                    '<br>'.join(lines) + BADGE_LINK))
    return out


def inject_pending_alert(html):
    """存档里有、字段库没登记的字段 -> 页面顶部显式告警

    这是「切叶蚁中工那 85 点被静默漏掉」的根治办法：
    以后不许再悄悄少一项。表收不下的时候必须自己举手，
    把字段名和值摊出来，让人一眼看见"这一行我还不认识"。
    """
    try:
        ints, bools = JC.read_save(JC.CUR)
    except OSError:
        return html
    unk_i = JC.unknown_ints(ints)
    unk_b = JC.unknown_bools(bools)
    if not unk_i and not unk_b:
        return html

    rows = ''.join(
        '<tr><td class="f">%s</td><td>Int</td><td><b>%d</b></td>'
        '<td>已加点 <b>%d</b> 点 —— 还没登记进字段库</td></tr>' % (f, ints[f], ints[f])
        for f in unk_i)
    rows += ''.join(
        '<tr><td class="f">%s</td><td>Bool</td><td><b>true</b></td>'
        '<td>已启用的开关 —— 还没登记进字段库</td></tr>' % f
        for f in unk_b)

    # 注意：这里不能用 % 格式化 —— 模板里的 width:40% 会被当成格式符
    box = (
        '\n<div class="note warn pending"><b>有 ' + str(len(unk_i) + len(unk_b))
        + ' 个字段还没登记，表里暂时收不下它们：</b>'
        '下面这些字段出现在你的存档里，但 <code>升级项字段库.csv</code> 里查不到，'
        '所以它们的加点效果<b>没有被算进</b>各表。'
        '要补上，只需在 <code>mod\\升级项字段库.csv</code> 末尾加一行、填好'
        '<code>单位中文 / 项目中文 / 每点效果 / 数值表列</code>，'
        '下次重跑这张表会自动认它。'
        '<table><tr><th style="width:40%">字段名</th><th style="width:8%">类型</th>'
        '<th style="width:10%">值</th><th>说明</th></tr>' + rows + '</table></div>\n')

    k = html.find('<nav class="toc">')
    if k == -1:
        k = html.find('<h2')
    return html[:k] + box + html[k:] if k != -1 else html + box

NEW_TITLES = [
    '1 · 你存档里读出来的数字（原文）',
    '2 · 已解锁的物种（12 个开关全开）',
    '3 · 已启用的适应性（每个单位 2 个，共 14 个）',
    '4 · 这些升级让你游戏里实际变成多少',
]


def main():
    a_path = sys.argv[1] if len(sys.argv) > 1 else pick(DEF_A, ALT_A)
    b_path = sys.argv[2] if len(sys.argv) > 2 else pick(DEF_B, ALT_B)
    out_path = sys.argv[3] if len(sys.argv) > 3 else DEF_OUT
    print('总表   :', os.path.relpath(a_path, MOD))
    print('存档表 :', os.path.relpath(b_path, MOD))

    html_a, html_b = load(a_path), load(b_path)
    c_a, c_b = inner_body(html_a), inner_body(html_b)
    css_a = style_of(html_a)

    # ---- 切出「你的存档」文档的正文块 --------------------------------------
    first_h2 = c_b.index('<h2')
    pre_b = c_b[:first_h2].strip()
    blocks = [x for x in re.split(r'(?=<h2)', c_b[first_h2:]) if x.strip()]
    assert len(blocks) >= 4, '存档报告结构变了, h2 块数 = %d' % len(blocks)

    def cut(b):
        m = re.match(r'<h2[^>]*>(.*?)</h2>(.*)', b, re.S)
        return m.group(1), m.group(2)

    sub_parts = []
    for i in range(4):
        _, rest = cut(blocks[i])
        the_id = ' id="ngp-eff"' if i == 3 else ''
        sub_parts.append('<h2%s>%s</h2>%s' % (the_id, NEW_TITLES[i], rest))

    # 去掉 pre_b 里的 <h1>（合并版有统一大标题）
    pre_b = re.sub(r'<h1>.*?</h1>', '', pre_b, count=1, flags=re.S).strip()

    yoursave = (
        '<h2 class="sec" id="yoursave">★ 你的存档（本周目）实际数值</h2>\n'
        '<div class="ngp">\n' + pre_b + '\n' + '\n'.join(sub_parts) + '\n</div>\n'
    )

    # ---- 主文档: 插目录 / 插"你的存档" / 加锚点 -------------------
    c_a = c_a.replace(
        '<h1>地下蚁国 · 蚁皇浆（Royal Jelly）升级总表</h1>',
        '<h1>地下蚁国 · 蚁皇浆（Royal Jelly）升级总表 <span style="font-size:15px;'
        'color:var(--sub);font-weight:400;letter-spacing:0">＋ 你的存档实际数值</span></h1>',
        1)

    c_a = c_a.replace(
        '你本机存档实际字段、官方 Hooded Horse wiki。</p>',
        '你本机存档实际字段、官方 Hooded Horse wiki。'
        '<b>本页已把原来的两张表合为一份</b>：总表 + 你存档的实际数值。</p>',
        1)

    toc = """
<nav class="toc"><b>目录</b>
<a class="star" href="#yoursave">★ 你的存档（本周目）实际数值</a>
<a href="#sec1">一、主力单位</a>
<a href="#sec2">二、进阶单位</a>
</nav>
"""
    lead_end = c_a.index('</p>', c_a.index('<p class="lead">')) + 4
    c_a = c_a[:lead_end] + '\n' + toc + c_a[lead_end:]

    root = '<h2 class="sec">一、主力单位（有适应性 + 属性微调）</h2>'
    c_a = c_a.replace(root, yoursave + root, 1)

    # 锚点（标题必须与 gen_jelly_table.py 里写的一字不差）
    for text, aid in [
        ('一、主力单位（有适应性 + 属性微调）', 'sec1'),
        ('二、进阶单位（只有 Lv3 解锁 + 属性微调，无适应性）', 'sec2'),
    ]:
        c_a = add_anchor(c_a, text, aid)

    # 单位卡片加"你已加点"标记（按存档现算）
    badges = build_badges()
    hits = 0
    for marker, text in badges:
        if marker not in c_a:
            print('  [warn] 未找到卡片: %s' % marker)
            continue
        i = c_a.index(marker)
        j = c_a.find('<p class="stathead">', i)
        if j == -1:
            k = c_a.find('<p class="meta">', i)
            j = c_a.index('</p>', k) + 4
        c_a = c_a[:j] + '<p class="yjbadge">%s</p>\n' % text + c_a[j:]
        hits += 1

    # 「库里有但没登记」的字段 —— 显式告警，绝不静默丢
    c_a = inject_pending_alert(c_a)

    out = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">\n'
        '<title>地下蚁国 · 蚁皇浆升级总表（含你的本周目档实际数值）</title>\n'
        '<style>\n' + css_a + '\n' + NGP_CSS + EXTRA_CSS + '\n</style></head><body><div class="wrap">\n'
        + c_a + '\n</div></body></html>\n'
    )

    # 交叉引用 / 页脚 收尾
    out = out.replace('（见第一节）', '（见上方「1 · 你存档里读出来的数字」）')
    out = out.replace(
        '<footer>生成自本机游戏文件 + 存档 + 官方 wiki 交叉验证</footer>',
        '<footer>单文件合并版 ｜ 总表：本机游戏文件 + 官方 wiki 交叉验证 ｜ '
        '你的存档部分：本机 <code>Colony1.sav</code> / <code>Colony1LevelData.sav</code> 实测</footer>')

    # 本页不假定存档一定是二周目 —— 统一用更通用的「本周目」说法
    out = out.replace('二周目', '本周目')

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(out)

    print('已生成: %s' % out_path)
    print('  大小: %.1f KB' % (len(out.encode('utf-8')) / 1024))
    print('  加点标记插入: %d/%d' % (hits, len(badges)))


if __name__ == '__main__':
    main()
