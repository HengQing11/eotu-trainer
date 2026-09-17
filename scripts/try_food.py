# -*- coding: utf-8 -*-
"""食物地址定位器 —— 命令行交互版

为什么需要这个脚本
------------------
「改存档」对关卡内的食物**完全没用**：食物是纯运行时的东西，存档里压根
没有这个字段（蚁皇浆那种才在存档里）。所以想动食物，只有一条路 ——
改游戏进程的内存。而改内存的前提是**先把地址找出来**，这个脚本就干这件事。

上次的教训（务必先读，别重复踩）
--------------------------------
《地下蚁国》界面上的食物数**不是内存里的一个汇总字段**，而是「所有粮仓
格子加起来」算出来的。也就是说内存里很可能**根本没有这个数**。
判定标准很简单：如果反复精扫（第 2 项）好几次，候选数收敛不到 10 个以内，
就说明确实没有汇总字段 —— 那就该换路线了（用 CE 抓「谁写入了食物」，
一路摸到格子数组），**不要在这里硬耗**。

安全参数（踩过大坑）
--------------------
16 线程全量扫 4.5 GB，把用户机器的桌面合成器扫崩过（游戏内存大多躺在
页面文件里，读它们等于等磁盘 → I/O 风暴 → DWM 超时）。所以这里固定：
    threads = 4，并且跳过 >512MB 的巨块
真扫不到再手动用第 5 项把强度放开，别一上来就全力。

用法
----
双击 mod\\试食物.bat，或在 mod\\ 目录下：
    python scripts\\try_food.py
游戏要先打开，并且**已经进入了一关**（能看到食物数的那个界面）。
"""
import json
import os
import struct
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_MOD = os.path.normpath(os.path.join(_HERE, os.pardir))
sys.path.insert(0, os.path.join(_MOD, 'gui'))

from core import memscan                                              # noqa: E402

try:
    sys.stdout.reconfigure(errors='replace')
except Exception:                                                     # noqa: BLE001
    pass

GAME_EXE = 'EotU-Win64-Shipping.exe'
LOG_PATH = os.path.join(_MOD, 'food_scan.log')
CAND_PATH = os.path.join(_MOD, 'food_candidates.json')

# 扫描强度（默认「标准」，别一上来全力）
THREADS = 4
MAX_REGION_MB = 512
KIND = 'int32'

_FMT = {'int32': '<i', 'uint32': '<I', 'int64': '<q', 'float': '<f', 'double': '<d'}
_SIZE = {'int32': 4, 'uint32': 4, 'int64': 8, 'float': 4, 'double': 8}

_LOG = None
_EOF = [False]


# ------------------------------------------------------------------ 小工具

def log(msg=''):
    print(msg)
    if _LOG:
        _LOG.write(msg + '\n')
        _LOG.flush()


def fmt(a):
    return '0x%X' % a


def rule(title=''):
    log('')
    log('=' * 64)
    if title:
        log(title)
        log('=' * 64)


def _input(prompt=''):
    """带 EOF 保护的 input —— 被重定向/管道跑的时候不至于抛异常"""
    try:
        return input(prompt)
    except EOFError:
        _EOF[0] = True
        return ''


def ask(prompt):
    """读一个整数；空输入返回 None"""
    while True:
        if _EOF[0]:
            return None
        s = _input(prompt).strip().replace(',', '').replace('，', '')
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            print('  “%s” 不是整数，再试一次（直接回车 = 放弃）' % s)


def pause(msg='按回车继续'):
    if _EOF[0]:
        return
    _input('\n' + msg + ' …')


# ------------------------------------------------------------------ 进程

def connect():
    pids = memscan.find_pids(GAME_EXE)
    if not pids:
        log('  ✗ 没找到游戏进程 %s' % GAME_EXE)
        log('    先把游戏打开，并且**进入一关**（要能看到食物数）。')
        return None
    proc = memscan.Process(pids[0])
    log('  ✓ 已连上 %s   PID=%d' % (GAME_EXE, pids[0]))
    regs = proc.regions(writable_only=True)
    total = sum(s for _b, s in regs)
    log('    可写内存 %.2f GB，共 %d 个区域' % (total / 2 ** 30, len(regs)))
    return proc


# ------------------------------------------------------------------ 扫描

def do_scan(proc, value, kind=None, cap=None):
    kind = kind or KIND
    cap = MAX_REGION_MB if cap is None else cap
    shown = [0]

    def prog(done, total):
        pct = done * 100 // max(total, 1)
        if pct >= shown[0] + 20:
            shown[0] = pct - pct % 20
            log('    …扫描 %d%%' % shown[0])

    t0 = time.time()
    hits = proc.scan_value(value, kind, writable_only=True, threads=THREADS,
                           max_region_mb=cap or 0, limit=300000, progress=prog)
    dt = time.time() - t0
    log('    扫完：命中 %d 个地址，用时 %.1f 秒' % (len(hits), dt))
    return hits


def read_many(proc, addrs, kind=None):
    """批量读 —— 相邻地址合并成一次系统调用

    几十万个候选逐个 ReadProcessMemory 要好几分钟；合并后通常剩几千次。
    """
    kind = kind or KIND
    sz, f = _SIZE[kind], _FMT[kind]
    addrs = sorted(addrs)
    out = {}
    i = 0
    while i < len(addrs):
        base = addrs[i]
        j = i
        while j + 1 < len(addrs) and addrs[j + 1] - base < 4096:
            j += 1
        data = proc.read(base, addrs[j] + sz - base)
        if data:
            for a in addrs[i:j + 1]:
                off = a - base
                if off + sz <= len(data):
                    out[a] = struct.unpack_from(f, data, off)[0]
        i = j + 1
    return out


def refine(proc, addrs, value, kind=None):
    """只留下「现在读出来正好等于 value」的候选"""
    t0 = time.time()
    vals = read_many(proc, addrs, kind)
    keep = [a for a, v in vals.items() if v == value]
    log('    精扫完：%d → %d 个，用时 %.1f 秒'
        % (len(addrs), len(keep), time.time() - t0))
    return keep


def neighbors(proc, addr, span=64, kind=None):
    """读候选附近的内存，返回 [(相对偏移个数, 值), ...]"""
    kind = kind or KIND
    sz, f = _SIZE[kind], _FMT[kind]
    base = addr - span
    data = proc.read(base, span * 2 + sz)
    if not data:
        return []
    out = []
    for off in range(0, len(data) - sz + 1, sz):
        if (base + off - addr) % sz:
            continue
        out.append(((base + off - addr) // sz,
                    struct.unpack_from(f, data, off)[0]))
    return out


def cluster(addrs, gap=4096):
    """把挨得近的地址归成一簇 —— 食物格子是数组，会挤在一起"""
    if not addrs:
        return []
    addrs = sorted(addrs)
    out = [[addrs[0]]]
    for a in addrs[1:]:
        if a - out[-1][-1] <= gap:
            out[-1].append(a)
        else:
            out.append([a])
    return out


def look_like_numbers(vals):
    """这串值看起来像「一片普通整数」吗（而不是指针/浮点垃圾）"""
    ok = 0
    for _rel, v in vals:
        if 0 <= v <= 10_000_000:
            ok += 1
    return ok / max(len(vals), 1)


# ------------------------------------------------------------------ 各项操作

def op_first(proc, st):
    log('')
    log('  现在游戏里显示的食物是多少？（不确定就把鼠标放到食物图标上看）')
    v = ask('  食物 = ')
    if v is None:
        return
    if v < 0:
        log('  食物不会是负数吧…')
        return
    log('  正在扫 %s == %d 的地址（跳过 >%sMB 的块，%d 线程）'
        % (KIND, v, MAX_REGION_MB or '不限', THREADS))
    hits = do_scan(proc, v)
    st['cands'], st['value'] = hits, v
    if not hits:
        log('  ⚠ 一个都没扫到 —— 说明这个数在内存里不是 %s 存的。' % KIND)
        log('    可以用第 5 项把类型换成 float 再扫一次。')
    elif len(hits) > 5000:
        log('  候选很多（小整数在内存里满地都是），继续第 2 项精扫。')
    else:
        log('  候选不多，可以直接第 3 项看看它们长什么样。')


def op_refine(proc, st):
    if st['cands'] is None:
        log('  还没首扫过，先做第 1 项。')
        return
    log('')
    log('  ⚠ 现在去游戏里让食物**明显变化**：随便花掉一些、或者再挖一点。')
    log('    变化幅度越大越好（最好 50 以上）—— 变得越多，越能筛掉碰巧相同的地址。')
    log('    变完再回来，把新的食物数填进来。')
    v = ask('  新的食物 = ')
    if v is None:
        return
    if v == st['value']:
        log('  ⚠ 和上次一模一样，这样筛不掉任何东西。换个数再来。')
        return
    keep = refine(proc, st['cands'], v)
    st['cands'], st['value'] = keep, v
    if not keep:
        log('  ⚠ 全被筛掉了 —— 两种可能：')
        log('     a) 食物值输错了（用第 1 项重来一次）；')
        log('     b) 界面那个数确实是**算出来的**（所有格子求和），内存里没有')
        log('        这个字段 —— 那就得换路线（CE 抓写入者），别继续在这里试。')
    elif len(keep) <= 10:
        log('  ✓ 收敛到 %d 个 —— 有戏！下一步第 3 项看邻居，第 4 项试写。' % len(keep))
    else:
        log('  还剩 %d 个。建议**再变化一次食物、再精扫一次**（第 2 项可以重复用）。'
            % len(keep))


def op_show(proc, st):
    if not st['cands']:
        log('  没有候选。先做第 1、2 项。')
        return
    cands = st['cands']
    log('')
    log('  存活候选 %d 个' % len(cands))
    cl = cluster(cands, gap=4096)
    log('  按「挨得近」归成 %d 簇（挤在一起 = 很可能是同一个数组，也就是粮仓格子）'
        % len(cl))
    log('')
    big = sorted(cl, key=lambda c: (-len(c), c[0]))
    for ci, c in enumerate(big[:8], 1):
        span = c[-1] - c[0]
        mark = ' ★ 像数组' if len(c) >= 3 and span <= 4096 else ''
        log('  【簇 %d】%d 个，%s ~ %s，跨度 %d 字节%s'
            % (ci, len(c), fmt(c[0]), fmt(c[-1]), span, mark))
        for a in c[:6]:
            log('      %s' % fmt(a))
        if len(c) > 6:
            log('      …（还有 %d 个）' % (len(c) - 6))
        nb = neighbors(proc, c[0])
        if nb:
            txt = ' '.join('%d:%d' % (rel, v) for rel, v in nb)
            log('      邻居（相对 4 字节个数 : 值，0 是候选本身）：')
            log('        %s' % txt)
            log('      这块内存「像整数」的比例：%.0f%%' % (look_like_numbers(nb) * 100))
            d = dict(nb)
            # 容量是个小整数（每格 10 / 总量几十上百），必须卡上限，
            # 否则一堆 ASCII/指针垃圾也会触发（试跑时踩过）
            if (d.get(1) is not None and d.get(0) is not None
                    and 0 <= d[0] <= d[1] <= 1000000):
                log('      ★ 紧跟着的那格（+4）是个更大的数 %d —— 这正是本项目'
                    '之前验证过的「[食物, 容量]」指纹，命中率很高' % d[1])
        log('')
    if len(big) > 8:
        log('  …还有 %d 簇没显示（候选太多说明还没筛干净，回去多精扫几次）'
            % (len(big) - 8))


def op_write(proc, st):
    cands = st['cands']
    if not cands:
        log('  没有候选，先扫描。')
        return
    log('')
    show = cands[:20]
    for i, a in enumerate(show):
        v = proc.read_value(a, KIND)
        log('  [%2d] %s   当前值 %s' % (i, fmt(a), v))
    if len(cands) > len(show):
        log('  …（只列前 %d 个）' % len(show))
    i = ask('  选第几个试写？（回车取消）')
    if i is None:
        return
    if not (0 <= i < len(show)):
        log('  序号不对。')
        return
    addr = show[i]
    tgt = ask('  要写进去的值（建议 99999 这种一眼能认出来的） = ')
    if tgt is None:
        return
    before = proc.read_value(addr, KIND)
    ok, after = proc.write_value(addr, tgt, KIND)
    log('')
    log('  %s  写入 %d：%s → %s（回读校验 %s）'
        % (fmt(addr), tgt, before, after, '通过' if after == tgt else '失败'))
    log('')
    log('  ⚠ 现在切回游戏看：')
    log('     · 食物数变成了 %s  → **找到了**，就是这个地址' % tgt)
    log('     · 一点没变        → 这是个无关的内存，回第 4 项试下一个')
    log('     · 界面数字没变、但蚂蚁搬东西时才变 → 找对了半格（那是格子或容量）')
    save_addr(addr, tgt)


def save_addr(addr, value):
    try:
        with open(os.path.join(_MOD, 'food_addr.txt'), 'a', encoding='utf-8') as f:
            f.write('%s  试写值=%s  %s\n'
                    % (fmt(addr), value, time.strftime('%Y-%m-%d %H:%M:%S')))
        log('  （地址已追加到 mod\\food_addr.txt）')
    except OSError:
        pass


def op_power(st):
    global MAX_REGION_MB, THREADS, KIND
    log('')
    log('  现在的强度：跳过 >%sMB 的块 / %d 线程 / 类型 %s'
        % (MAX_REGION_MB or '不限', THREADS, KIND))
    log('''
  [1] 温和   跳过 >256MB 的块（最安全，卡顿最小）
  [2] 标准   跳过 >512MB 的块（默认）
  [3] 放开   不限区域大小（慢，而且伤机器 —— 上次就是这么把桌面扫崩的）
  [4] 类型   int32 <-> float 切换''')
    c = _input('  选 = ').strip() or '0'
    if c == '1':
        MAX_REGION_MB = 256
    elif c == '2':
        MAX_REGION_MB = 512
    elif c == '3':
        MAX_REGION_MB = 0
        log('  ⚠ 已放开：全量扫可能几分钟，也可能让桌面卡死。真卡了就耐心等，别强杀。')
    elif c == '4':
        KIND = 'float' if KIND == 'int32' else 'int32'
    log('  现在是：跳过 >%sMB / %d 线程 / %s' % (MAX_REGION_MB or '不限', THREADS, KIND))
    st['cands'] = None


def op_save(st):
    if not st['cands']:
        log('  没有候选可存。')
        return
    try:
        with open(CAND_PATH, 'w', encoding='utf-8') as f:
            json.dump({'value': st['value'], 'kind': KIND,
                       'addrs': [hex(a) for a in st['cands']]}, f, indent=1)
        log('  已存到 %s（%d 个）' % (CAND_PATH, len(st['cands'])))
    except OSError as e:
        log('  存不了：%s' % e)


# ------------------------------------------------------------------ 主流程

def main():
    global _LOG
    _LOG = open(LOG_PATH, 'a', encoding='utf-8')
    _LOG.write('\n\n########## %s ##########\n' % time.strftime('%Y-%m-%d %H:%M:%S'))

    rule('地下蚁国 · 食物地址定位器')
    log('''
这一步只做一件事：把「游戏里显示的食物数」在内存里找出来。
找出来之后才谈得上改。脚本平时**只读**，只有你选第 4 项时才会动内存。

动手前：
  1) 游戏已经打开、已经**进入某一关**（能看到食物数）
  2) 最好把食物弄到一个**不常见的数**（比如 137、233）
     —— 小整数在内存里满地都是，数字越独特，首扫噪音越少
  3) 别在教程关试（教程关可能锁着资源不给改），挑正式战役关

    ''')

    proc = connect()
    if proc is None:
        pause('按回车退出')
        return 1

    st = {'cands': None, 'value': None}
    while not _EOF[0]:
        rule()
        if st['cands'] is None:
            log('  状态：还没扫描')
        else:
            log('  状态：候选 %d 个（以食物值 %s 为准）'
                % (len(st['cands']), st['value']))
        log('''
  [1] 首扫           输入游戏里当前的食物数，开始找
  [2] 精扫           在游戏里改变食物后输新数，缩小范围（可重复）
  [3] 看候选 + 邻居   打印存活地址、聚类，以及附近内存长什么样
  [4] 试写           挑一个候选写个值，回游戏看变没变
  [5] 扫描强度       现在：跳过 >%sMB / %d 线程 / %s
  [6] 存候选         把候选存盘（同一局游戏里地址不变，可留着继续）
  [7] 退出
''' % (MAX_REGION_MB or '不限', THREADS, KIND))
        c = _input('  选 = ').strip() or '0'
        if _EOF[0]:
            break
        try:
            if c == '1':
                op_first(proc, st)
            elif c == '2':
                op_refine(proc, st)
            elif c == '3':
                op_show(proc, st)
            elif c == '4':
                op_write(proc, st)
            elif c == '5':
                op_power(st)
            elif c == '6':
                op_save(st)
            elif c == '7':
                break
            else:
                log('  没有这一项。')
        except memscan.MemError as e:
            log('  ✗ 内存操作失败：%s' % e)
            log('    （游戏可能关掉了 —— 那就重开脚本）')
        except KeyboardInterrupt:
            log('  已中断。')
            break
        pause()

    proc.close()
    log('')
    log('  完整记录在 %s —— 把它发给我。' % LOG_PATH)
    log('  如果是「试写生效了」，**先别关游戏**，我们接着做锁定和指针链。')
    if _LOG:
        _LOG.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
