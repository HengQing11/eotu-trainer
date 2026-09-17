# -*- coding: utf-8 -*-
"""蚁皇浆 · 运行时补满（不碰存档文件，游戏开着也能改）

用法（双击 mod\\运行时补满蚁皇浆.bat 即可）
------------------------------------------
    python scripts/jelly_live.py                ★ 锚点定位（推荐，不用输数字、不挑档）
    python scripts/jelly_live.py --auto         旧办法：扫"十亿量级的大整数" + 指纹
    python scripts/jelly_live.py 1234567890     手动给"游戏里显示的数"
    python scripts/jelly_live.py --check        只定位不写（任何模式都能加）
    python scripts/jelly_live.py --yes          不确认直接写

★ 锚点定位（2026-09-16 标定，最终方案）
--------------------------------------
殖民地对象身上有：
    +0x4FC = 食物 / +0x500 = 容量（后面 16 个 0 再一个 1.0f）
    +0x86C = 累计采集资源   +0x8B4 = 已挖掘格数
    +0x89C = **蚁皇浆**                ← 本文件的核心常量
    vtable RVA = 0x3CCDDB0             ← 跨关卡实测一致
所以定位 = 遍历关卡 Actor 表 → 找 vtable 匹配的殖民地对象 → 读 +0x89C。
**与蚁皇浆的值无关 → 新建档（浆=0）也能用**，这是它比 --auto 强的地方。

标定怎么来的（三重验证）
------------------------
① 对象 class/vtable 与另一档（aa）的殖民地对象完全相同
② 食物记录签名命中（[食物, 容量, 0×16, 1.0f]）
③ **蚁皇浆 − 340 = 85**，正是 20:35 记录过的加点点数，分毫不差

⚠️ 一关里通常有 **2 个** 殖民地对象（实测：一个是玩家在玩的，一个有痕迹全 0）。
选择依据（打分，见 `_score`）：累计采集/已挖掘 > 0、加点等级多、食物在合理区间。
若两处同分（全新档），取 Actor 表里靠前的那个 —— 两处的蚁皇浆值是同步的
（实测：只写过一处，两处都变成了 20 亿）。

⚠️ 边界
- 非关卡界面（大地图/主菜单）找不到殖民地对象 → 返回 4
- 若将来游戏大版本更新导致 vtable RVA 变化，会用"食物记录签名"兜底；
  两条都不中就是 4（定位失败），**绝不盲写**

⚠️⚠️ 事故留痕（2026-09-16 20:15）
拿**猜的 137** 当输入试跑，引擎仍"定位成功"并把 20 亿写到一张编号表上（已还原原值）。
**铁律：绝不用"猜的值"当输入**。
"""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.abspath(os.path.join(HERE, os.pardir))
GUI = os.path.join(MOD, 'gui')
sys.path.insert(0, GUI)
sys.path.insert(0, HERE)

from core import live                                              # noqa: E402

# ---------------------------------------------------------------- 常量
JELLY_OFF = 0x89C          # ★ 蚁皇浆在殖民地对象内的偏移（2026-09-16 标定）
LEDGER_OFF = 0x4FC         # 食物字段（对象识别用）
TOT_RES_OFF = 0x86C        # 累计采集资源（判断"哪个是在玩的巢"）
TILES_OFF = 0x8B4          # 已挖掘格数
COLONY_VT_RVA = 0x3CCDDB0  # 殖民地对象 vtable 的 RVA

WINDOW = 1024              # 指纹交叉验证窗口（老默认 16KB 太大，见文件头事故记录）
MIN_KINDS = 3              # 手动模式：至少命中几种指纹
AUTO_MIN_KINDS = 4         # 自动模式更严（没有"已知当前值"这重保险）
MAX_HITS = 200             # 手动模式：候选数上限（值必须够独特）
MAX_INT32 = 2_147_483_647
AUTO_LO = 1_000_000        # 自动模式扫描的数值下限
MAX_REGION_MB = 1          # 只扫 ≤1MB 的区域（沿用"跳过巨块"的安全约定）
ADDON_LEVELS = (10, 20, 22, 30, 85)   # 加点等级值的样本（用来认出"玩家自己的巢"）

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NO_LEVEL = 2
EXIT_NO_FINGERPRINT = 3
EXIT_LOCATE_FAIL = 4
EXIT_VERIFY_FAIL = 5


def out(msg=''):
    sys.stdout.write(msg + '\n')


# ---------------------------------------------------------------- 存档信息（报告用）
def saves_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    return os.path.join(base, 'EotU', 'Saved', 'SaveGames')


def _gvas_str(data, name):
    """取 GVAS 里 StrProperty 的值（**只用于报告**）

    ⚠️ 必须从「键名之后」开始扫；从键名本身开始会把键名当值返回（踩过）。
    """
    key = name.encode('latin1') + b'\x00'
    i = data.find(key)
    if i < 0:
        return None
    for m in re.finditer(rb'[\x20-\x7e]{3,}', data[i + len(key): i + len(key) + 400]):
        s = m.group().decode('latin1')
        if s in ('StrProperty', 'None'):
            continue
        return s
    return None


def active_colony():
    """游戏当前在玩哪个殖民档 —— 读 LevelSetup.sav 的 FormicSaveToLoad（如 'Colony2'）"""
    sd = saves_dir()
    p = os.path.join(sd, 'LevelSetup.sav')
    name = None
    if os.path.isfile(p):
        try:
            name = _gvas_str(open(p, 'rb').read(), 'FormicSaveToLoad')
        except OSError:
            name = None
    if name:
        cand = name if name.lower().endswith('.sav') else name + '.sav'
        if os.path.isfile(os.path.join(sd, cand)):
            return cand
    return 'Colony1.sav' if os.path.isfile(os.path.join(sd, 'Colony1.sav')) else None


def active_level():
    """当前关卡路径（报告用）"""
    p = os.path.join(saves_dir(), 'LevelSetup.sav')
    if os.path.isfile(p):
        try:
            return _gvas_str(open(p, 'rb').read(), 'LevelToLoad')
        except OSError:
            pass
    return None


# ---------------------------------------------------------------- ★ 锚点定位
def _score(proc, obj):
    """给一个殖民地候选打分（判断"是不是玩家在玩的那个巢"）

    实测一关里有 2 个殖民地对象：真的那个有采集/挖掘记录、加点齐全；
    另一个（大概是敌方/备用巢）三项全 0。全新档两边都 0 → 同分，取靠前的。
    """
    s, detail = 0, {}
    tot = proc.read_value(obj + TOT_RES_OFF, 'int32')
    til = proc.read_value(obj + TILES_OFF, 'int32')
    jel = proc.read_value(obj + JELLY_OFF, 'int32')
    d = proc.read(obj, 0x2000)
    lv = sorted({struct.unpack_from('<i', d, o)[0]
                 for o in range(0x40, len(d) - 3, 4)
                 if struct.unpack_from('<i', d, o)[0] in ADDON_LEVELS}) if d else []
    if isinstance(tot, int) and tot > 0:
        s += 3
    if isinstance(til, int) and til > 0:
        s += 2
    if len(lv) >= 3:
        s += 2
    if isinstance(jel, int) and jel > 0:
        s += 1
    detail = dict(total=tot, tiles=til, jelly=jel, levels=lv)
    return s, detail


def find_colony(proc, base, size, verbose=True):
    """遍历关卡 Actor 表找殖民地对象 -> (对象基址, 该对象里的蚁皇浆值) 或 (None, None)

    判据（按优先级）：
      ① vtable 的 RVA == COLONY_VT_RVA（最强，跨关卡实测一致）
      ② 兜底：含"食物记录"签名（[食物, 容量, 0×16, 1.0f]）且值合理
    两条都不中 → (None, None)，调用方必须停下来，**不许猜**。
    """
    try:
        import ue_walk as uw
    except ImportError:
        if verbose:
            out('  [!] 找不到 ue_walk.py（对象遍历模块），无法做锚点定位')
        return None, None

    gw_raw = proc.read(base + uw.G_WORLD_RVA, 8)
    if not gw_raw:
        return None, None
    gw = struct.unpack('<Q', gw_raw)[0]
    wd = proc.read(gw, 0x200)
    if not wd:
        return None, None
    level = uw.u64(wd, 0x30)
    ld = proc.read(level, 0x100)
    if not ld:
        return None, None
    aptr, anum = uw.u64(ld, 0x98), uw.u32(ld, 0xA0)
    if not (0 < anum < 200000):
        return None, None
    raw = proc.read(aptr, anum * 8)
    if not raw or len(raw) < anum * 8:
        return None, None

    by_vt, by_sig = [], []
    for i in range(anum):
        a = uw.u64(raw, 8 * i)
        if not uw.looks_ptr(a):
            continue
        h = proc.read(a, 8)
        if not h:
            continue
        if uw.u64(h, 0) - base == COLONY_VT_RVA:
            by_vt.append(a)
            continue
        fd = proc.read(a + LEDGER_OFF - 4, 32)
        if fd and len(fd) >= 32 and fd[12:32] == b'\x00' * 16 + struct.pack('<f', 1.0):
            food, cap = struct.unpack_from('<i', fd, 4)[0], struct.unpack_from('<i', fd, 8)[0]
            if 0 <= food <= 100000 and 0 <= cap <= 100000:
                by_sig.append(a)

    cands = by_vt or by_sig
    how = 'vtable 精确匹配' if by_vt else '食物记录签名兜底'
    if verbose:
        out('  关卡里 %d 个对象 → 殖民地候选 %d 个（%s）' % (anum, len(cands), how))
    if not cands:
        return None, None

    scored = []
    for a in cands:
        s, detail = _score(proc, a)
        j = detail.get('jelly')
        if j is None or not (0 <= j <= MAX_INT32):
            continue
        scored.append((s, a, j, detail))
    if not scored:
        return None, None
    scored.sort(key=lambda t: -t[0])            # 分数高的优先；同分保持 Actor 表顺序

    if verbose:
        for s, a, j, detail in scored:
            out('      %s  得分 %d  → 蚁皇浆 %s   （采集 %s / 挖掘 %s / 加点 %s）'
                % (hex(a), s, '{:,}'.format(j), detail.get('total'),
                   detail.get('tiles'), detail.get('levels') or '无'))
    top = scored[0]
    if verbose and len(scored) > 1 and scored[1][0] == top[0]:
        out('      （两处同分 —— 取靠前的那个；实测两处的蚁皇浆值是同步的）')
    return top[1], top[2]


def locate_anchor(proc, base, size, verbose=True):
    """锚点定位 -> (蚁皇浆地址, 当前值) 或 (None, None)"""
    obj, val = find_colony(proc, base, size, verbose=verbose)
    if obj is None:
        return None, None
    return obj + JELLY_OFF, val


# ---------------------------------------------------------------- 旧办法（扫值 + 指纹）
def auto_scan(proc, lo=AUTO_LO, hi=MAX_INT32, max_region_mb=MAX_REGION_MB):
    """按数值区间扫可写内存 -> [地址]（**不需要知道确切值**）"""
    hits = []
    cap = max_region_mb * 1024 * 1024
    for base, size in proc.regions(writable_only=True):
        if size > cap:
            continue
        d = proc.read(base, size)
        if not d:
            continue
        for i in range(0, len(d) - 3, 4):
            v = struct.unpack_from('<i', d, i)[0]
            if lo <= v <= hi:
                hits.append(base + i)
    return hits


def rank_by_fingerprint(proc, addrs, known, window=WINDOW):
    """给候选按"±window 内命中的加点点数种类数"打分 -> [(分数, 地址)] 降序"""
    known = set(known)
    rank = []
    for a in addrs:
        d = proc.read(max(a - window, 0), window * 2)
        kinds = set()
        if d:
            for i in range(0, len(d) - 3, 4):
                v = struct.unpack_from('<i', d, i)[0]
                if v in known:
                    kinds.add(v)
        rank.append((len(kinds), a))
    rank.sort(reverse=True)
    return rank


def pick_auto(proc, known, verbose=True):
    """自动定位蚁皇浆 -> (地址, 当前值, 指纹种数, 候选总数) 或 (None, ...)"""
    hits = auto_scan(proc)
    if verbose:
        out('  自动扫描：可写内存里"≥%d 的整数"共 %d 个地址' % (AUTO_LO, len(hits)))
    if not hits:
        return None, 0, 0, 0
    rank = rank_by_fingerprint(proc, hits, known)
    best_kinds, best = rank[0]
    second = rank[1][0] if len(rank) > 1 else -1
    val = proc.read_value(best, 'int32')
    if verbose:
        out('  指纹打分前 3：%s' % [('命中%d种' % k, hex(a)) for k, a in rank[:3]])
    if best_kinds < AUTO_MIN_KINDS:
        if verbose:
            out('  ✗ 最佳候选只命中 %d 种指纹（要求 ≥%d）—— 不敢写'
                % (best_kinds, AUTO_MIN_KINDS))
        return None, val, best_kinds, len(hits)
    if best_kinds <= second:
        if verbose:
            out('  ✗ 最高分并列（%d 种），无法唯一确定 —— 不敢写' % best_kinds)
        return None, val, best_kinds, len(hits)
    return best, val, best_kinds, len(hits)


def locate_manual(proc, value, known):
    """手动模式：拿"游戏里显示的数"扫 -> (地址, 指纹种数, 候选数)"""
    hits = proc.scan_value(value, 'int32', writable_only=True,
                           max_region_mb=MAX_REGION_MB, threads=8)
    if not hits:
        return None, 0, 0
    rank = rank_by_fingerprint(proc, hits, known)
    return rank[0][1], rank[0][0], len(hits)


# ---------------------------------------------------------------- 主流程
def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:                                              # noqa: BLE001
        pass

    a = sys.argv[1:]
    auto = '--auto' in a
    anchor = '--anchor' in a
    dry = '--check' in a
    yes = '--yes' in a
    force = '--force' in a
    colony = None
    if '--colony' in a:
        try:
            colony = a[a.index('--colony') + 1]
        except IndexError:
            out('  [!] --colony 后面要跟存档文件名（如 Colony1.sav）'); return EXIT_USAGE
    nums = []
    for x in a:
        if x.startswith('--') or x == colony:
            continue
        try:
            nums.append(int(x))
        except ValueError:
            pass

    out('=' * 64)
    out('  蚁皇浆 · 运行时补满' + ('   [只定位，不写]' if dry else ''))
    out('=' * 64)
    out()

    proc = live.game_proc()
    if proc is None:
        out('  [!] 游戏没开 —— 没开时直接用 补满蚁皇浆.bat 改存档更省事')
        return EXIT_USAGE

    colony = colony or active_colony()
    known = live.known_addon_values(colony) if colony else []
    lvl = active_level()
    out('  当前活跃档：%s%s' % (colony or '（读不到）',
                              ('   关卡：%s' % os.path.basename(lvl)) if lvl else ''))
    out('  指纹（加点点数）：%s' % (known or '【空】'))
    out('  目标：补满到 %s' % '{:,}'.format(live.JELLY_CAP))
    out()

    modes = []
    if anchor or (not auto and not nums):
        modes.append('anchor')                      # 默认就走锚点
    if auto:
        modes.append('auto')
    if nums:
        modes.append('manual')
    if not modes:
        modes = ['anchor']

    addr = before = None
    note = ''
    for mode in modes:
        if mode == 'anchor':
            out('  ① 锚点定位（遍历关卡对象，不看浆的值）…')
            from core import memscan as _ms
            pl = _ms.find_pids(live.GAME_EXE)
            if not pl:
                out('     ✗ 游戏进程不见了')
                continue
            try:
                import ue_walk as uw
                base, size = uw.module_info(pl[0])
            except ImportError:
                out('     ✗ 缺 ue_walk.py，跳过锚点')
                continue
            if not base:
                out('     ✗ 读不到游戏模块基址')
                continue
            addr, before = locate_anchor(proc, base, size)
            if addr:
                note = '锚点'
                out('  ✓ 锚点定位成功：%s' % hex(addr))
                out('      当前蚁皇浆 = %s' % '{:,}'.format(before or 0))
                break
            out('     ✗ 锚点没找到（可能没进关卡，或游戏版本变了）')

        elif mode == 'auto':
            out('  ② 自动定位（扫十亿量级的大整数 + 指纹）…')
            if not known and not force:
                out('     ✗ 这个档还没有加点点数，没有指纹可交叉验证')
                continue
            addr, before, kinds, nhits = pick_auto(proc, known)
            if addr:
                note = '自动（指纹 %d 种，候选 %d 个）' % (kinds, nhits)
                out('  ✓ 自动定位成功：%s' % hex(addr))
                out('      当前 = %s' % '{:,}'.format(before or 0))
                if not (AUTO_LO <= before <= MAX_INT32):
                    out('      ⚠ 值不在预期区间，已停止（不写）')
                    addr = None
                else:
                    break
            else:
                out('     ✗ 自动定位失败')

        elif mode == 'manual':
            current = nums[0]
            if current == 0 and not force:
                out('  ⚠ 手动值给了 0 —— 0 在内存里几十万个，定位不了，跳过')
                continue
            if not known and not force:
                out('  ⚠ 这个档还没有加点点数，没有指纹可交叉验证，跳过')
                continue
            addr, kinds, nhits = locate_manual(proc, current, known)
            if addr is None:
                out('     ✗ 定位失败（候选 %d 个）' % nhits)
                continue
            if (nhits > MAX_HITS or kinds < MIN_KINDS) and not force:
                out('     ✗ 拒绝：候选 %d 个 / 指纹 %d 种，不够可信' % (nhits, kinds))
                addr = None
                continue
            before = proc.read_value(addr, 'int32')
            note = '手动（指纹 %d 种，候选 %d 个）' % (kinds, nhits)
            out('  ✓ 手动定位成功：%s' % hex(addr))
            break

    if not addr:
        out()
        out('  ── 未能定位 ──')
        out('  请确认：① 已进入一关（不是大地图）② 游戏没有被暂停掉')
        out('  还不行的话，把上面这几行发我。')
        proc.close()
        return EXIT_LOCATE_FAIL

    out('  定位方式：%s' % note)
    out()

    if dry:
        out('  （--check：没有写入）')
        proc.close()
        return EXIT_OK

    if not yes:
        ans = input('  确认把蚁皇浆写成 %s？(Y/N) ' % '{:,}'.format(live.JELLY_CAP))
        if ans.strip().lower() not in ('y', 'yes', '是'):
            out('  已取消。')
            proc.close()
            return EXIT_OK

    # ★ 写入前复核对象身份：堆地址会随游戏内部重建而变（实测两次定位地址就不同），
    #   绝不能往"已经不是殖民地对象"的地址上写（对象释放后内存会被复用）。
    if note == '锚点':
        h = proc.read(addr - JELLY_OFF, 8)
        try:
            import ue_walk as _uw
            from core import memscan as _ms
            _p = _ms.find_pids(live.GAME_EXE)
            _b, _ = _uw.module_info(_p[0]) if _p else (None, None)
        except ImportError:
            _b = None
        if not h or not _b or struct.unpack('<Q', h)[0] - _b != COLONY_VT_RVA:
            out('  ✗ 写入前复核失败：目标对象已经变了（地址被复用）—— 已停止，未写入')
            proc.close()
            return EXIT_LOCATE_FAIL

    ok, after = live.write_jelly(proc, addr, live.JELLY_CAP)
    out('  写入 %s → 回读 %s  %s'
        % ('{:,}'.format(live.JELLY_CAP), '{:,}'.format(after or 0),
           'OK' if after == live.JELLY_CAP else '失败'))
    if after == live.JELLY_CAP:
        out()
        out('  完成。切回游戏打开「生物适应」面板即可看到（面板有缓存，需重开）。')
        out('  游戏下次存盘会自己落档 —— 这条改动是持久的。')
        proc.close()
        return EXIT_OK
    out('  回读对不上 —— 这个地址可能不是蚁皇浆，**别继续用**，把这个结果告诉我。')
    proc.close()
    return EXIT_VERIFY_FAIL


if __name__ == '__main__':
    sys.exit(main())
