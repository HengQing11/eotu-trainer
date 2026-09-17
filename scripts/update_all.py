# -*- coding: utf-8 -*-
"""一键更新：读存档 -> 重算 -> 重新合并成一张 HTML -> 打开

由 更新表格.bat 调用（bat 里只有纯 ASCII，中文都在这里，避免编码问题）。

为什么先跑 build_field_lib：
    它会拿你的存档和字段库对一遍，凡是"存档里有、字段库里查不到"的字段
    都会被点名列出来。这类字段就是以前的静默漏洞（切叶蚁中工那 85 点），
    所以放在第一步先报警。
"""
import json
import os
import subprocess
import sys
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)

OUT_HTML = os.path.join(MOD, '蚁皇浆升级总表.html')
STAMP = os.path.join(MOD, 'backup', '上次更新状态.json')

STEPS = [
    ('build_field_lib.py', '刷新字段库（并检查存档里有没有我还不认识的字段）'),
    ('gen_jelly_table.py', '生成总表分表（单位定义 + 游戏基础数值）'),
    ('gen_ngp_report.py',  '读你的存档，算每一项实际生效多少'),
    ('merge_html.py',      '合并成一张 HTML'),
]


def game_running():
    """检测游戏是否在跑

    注意：tasklist 在中文 Windows 下输出是 GBK，用 text=True 会解码失败，
    所以这里按字节匹配。存盘只在游戏保存时发生，游戏在跑读到的多半是旧数据。
    """
    try:
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq EotU-Win64-Shipping.exe'],
                           capture_output=True, timeout=10)
        return b'EotU-Win64-Shipping.exe' in (r.stdout or b'')
    except Exception:
        return False


def snapshot():
    """读一遍存档，给个摘要；顺便和上次比，看有没有变化"""
    sys.path.insert(0, HERE)
    try:
        import jelly_calc as JC
        ints, bools = JC.read_save(JC.CUR)
    except Exception as e:
        return None, '读存档失败: %s' % e

    pts = JC.points(ints)
    cur = {
        'jelly_pts': sum(p for _f, p in pts),
        'items': sorted('%s=%d' % (f.name, p) for f, p in pts),
        'jelly_total': ints.get('RoyalJelly'),
        'ngp': ints.get('NewGamePlusLevel'),
    }
    old = None
    if os.path.isfile(STAMP):
        try:
            old = json.load(open(STAMP, encoding='utf-8'))
        except Exception:
            old = None
    os.makedirs(os.path.dirname(STAMP), exist_ok=True)
    json.dump(cur, open(STAMP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return (cur, old), None


def main():
    # 让本脚本的输出和子脚本的输出按顺序显示（否则管道下会交错）
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    no_open = '--no-open' in sys.argv
    line = '=' * 64
    print(line)
    print('  地下蚁国 · 蚁皇浆升级总表   一键更新')
    print(line)
    print()

    if game_running():
        print('  [注意] 游戏正在运行 —— 存档只在游戏存盘时才写到磁盘，')
        print('         现在读到的可能还是上一次存盘的内容。')
        print('         建议退出游戏后再点一次这个脚本。')
        print()

    for i, (script, desc) in enumerate(STEPS, 1):
        print('[%d/%d] %s' % (i, len(STEPS), desc))
        r = subprocess.run([sys.executable, os.path.join(HERE, script)], cwd=MOD)
        if r.returncode != 0:
            print()
            print('  ！这一步失败（%s），后面的步骤已停下。' % script)
            print('    把上面那段红字发给我就行。')
            return 1
        print()

    snap, err = snapshot()
    if err:
        print('[摘要] %s' % err)
    else:
        cur, old = snap
        print('-' * 64)
        print('  已加点：%d 项，合计 %d 点' % (len(cur['items']), cur['jelly_pts']))
        if cur['jelly_total'] is not None:
            print('  蚁皇浆余额：%d' % cur['jelly_total'])
        if cur['ngp'] is not None:
            print('  二周目等级：%s' % cur['ngp'])
        if old is None:
            print('  （第一次记录，下次更新就能对比出变化了）')
        elif old.get('items') != cur['items']:
            before = dict(x.split('=') for x in old.get('items', []))
            after = dict(x.split('=') for x in cur['items'])
            print('  与上次相比的变化：')
            for k in sorted(set(before) | set(after)):
                a, b = int(before.get(k, 0)), int(after.get(k, 0))
                if a != b:
                    print('    %-42s %d -> %d' % (k, a, b))
        else:
            print('  与上次相比：没有变化')
        print('-' * 64)
        print()

    print('完成 -> %s' % OUT_HTML)
    if not no_open:
        webbrowser.open('file:///' + OUT_HTML.replace('\\', '/'))
        print('已用默认浏览器打开。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
