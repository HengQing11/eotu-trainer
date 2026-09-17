# -*- coding: utf-8 -*-
"""存档清单 —— 文件名 与 游戏里显示的名字 的对应关系

游戏把玩家起的名字存在存档的 `ColonyName` 字段里（StrProperty）。
另有一个 `LinkedSaveGame` 写明「这个档的关卡数据存在哪个文件」。
两个都直接读存档本身，**不靠命名规律猜** —— 那条规律在 NG+ 档上是错的：

    Colony1.sav            -> Colony1LevelData.sav            ✓ 规律成立
    Colony1Stage1.sav      -> Colony1LevelDataStage1.sav      ✓ 碰巧成立
    Colony1NewGamePlus0.sav -> Colony1LevelDataNewGamePlus0.sav  ✗ 规律会算出
                              Colony1NewGamePlus0LevelData.sav

StrProperty 的字节布局（实测 `ColonyName`）：
    FString 属性名 + FString "StrProperty" + int32 Size + int32 ArrayIndex
    + 1 字节 bHasGuid + FString 值(int32 长度 + UTF-8 + \\0)
所以「值」起点 = 类型名 FString 末尾 + 9。
"""
import os
import re
import struct

from . import paths

_TYPE = 'StrProperty'
_PAT = struct.pack('<i', len(_TYPE) + 1) + _TYPE.encode() + b'\x00'
_DELTA = 9              # 类型名 FString 末尾 -> 值 FString 起点
_BACK_MAX = 80          # 反查属性名时最多往回找多少字节

# 文件名里带这些词的都不是「玩家自己的档」
_SKIP = ('backup', 'leveldata', 'progress', 'levelsetup', 'customgamemeta')

# 玩家能看到的「存档槽位」：战役档就是 Colony<数字>.sav。
# 被这条排除掉的（全是游戏自己产生的，不该让用户在修改器里挑）：
#   Colony1Stage1.sav        关卡进行中的自动快照
#   Colony1NewGamePlus0.sav  NG+ 的自动快照
#   Freeplay1/2.sav          自由模式 —— 另一个玩法，跟蚁巢加点无关
# 依据：游戏自己就是这么按槽位命名的（自由模式的槽位号记在
# CustomGameMeta.sav 的 SaveNumber 里），不是我们猜的规则。
_SLOT_RE = re.compile(r'^Colony\d+\.sav$', re.I)


class SaveInfo(object):
    """一个存档文件的基本信息"""

    def __init__(self, file, colony='', leveldata='', map_name=''):
        self.file = file              # 文件名 —— 程序内部一律用它定位
        self.colony = colony          # 游戏里显示的名字（用户起的）
        self.leveldata = leveldata    # 关卡数据文件名（不带 .sav）
        self.map_name = map_name      # 自由模式用的地图名

    @property
    def label(self):
        """下拉里显示的文字。**只显示游戏里的名字**（用户要求），
        读不到才退回文件名。"""
        return self.colony or os.path.splitext(self.file)[0]

    def __repr__(self):
        return '<SaveInfo %s %r>' % (self.file, self.colony)


def _name_before(data, off):
    """从类型名起点往前回溯，找紧邻的属性名 FString"""
    for back in range(1, _BACK_MAX):
        s = off - back
        if s < 4:
            return None
        ln = struct.unpack_from('<i', data, s - 4)[0]
        if 1 < ln <= 70 and s + ln == off:
            raw = data[s:s + ln - 1]
            if raw.isascii() and re.match(rb'^[A-Za-z_][A-Za-z0-9_]*$', raw):
                return raw.decode('latin1')
    return None


def str_fields(path):
    """读一个存档里的字符串字段 -> {属性名: 值}（同名的只留第一个）"""
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return {}

    out = {}
    for m in re.finditer(re.escape(_PAT), data):
        nm = _name_before(data, m.start())
        if nm is None or nm in out:
            continue
        v = m.end() + _DELTA
        if v + 4 > len(data):
            continue
        ln = struct.unpack_from('<i', data, v)[0]
        if not (0 < ln < 200) or v + 4 + ln > len(data):
            continue
        raw = data[v + 4:v + 4 + ln - 1]
        try:
            out[nm] = raw.decode('utf-8')
        except UnicodeDecodeError:
            out[nm] = raw.decode('latin1')
    return out


def info(file, folder=None):
    """读一个存档文件的信息（不存在的文件也能安全调用）"""
    p = os.path.join(folder or paths.saves_dir(), file)
    f = str_fields(p)
    return SaveInfo(
        file=file,
        colony=f.get('ColonyName') or '',
        leveldata=f.get('LinkedSaveGame') or '',
        map_name=(f.get('MapToLoad') or '').rsplit('/', 1)[-1])


def list_all(folder=None):
    """所有「像样的」存档文件（含自动快照 / 自由模式）-> [SaveInfo]"""
    d = folder or paths.saves_dir()
    try:
        files = sorted(os.listdir(d))
    except OSError:
        return []

    out = []
    for fn in files:
        low = fn.lower()
        if not low.endswith('.sav'):
            continue
        if any(k in low for k in _SKIP):
            continue
        out.append(info(fn, d))
    out.sort(key=lambda s: s.label)
    return out


def list_saves(folder=None):
    """修改器里该显示的存档 -> [SaveInfo]

    **只返回玩家自己的槽位档**（`Colony<数字>.sav`）。游戏自动产生的
    章节快照 / NG+ 快照 / 自由模式档都不在这儿 —— 用户认的是他在游戏
    存档界面里能看到的那几个。
    """
    out = [s for s in list_all(folder) if _SLOT_RE.match(s.file)]
    out.sort(key=lambda s: s.label)
    return out


def find(folder=None):
    """-> (save_name, leveldata_name)

    `save_name` = 配置里记的那个存档；配置空或文件不在时退回第一个。
    `leveldata_name` 优先用存档自己声明的 LinkedSaveGame，读不到才按
    「X.sav -> XLevelData.sav」猜（那条规律对 NG+ 档是错的，只当兜底）。
    """
    items = list_saves(folder)
    if not items:
        return None, None
    return items[0].file, leveldata_of(items[0].file, folder)


def leveldata_of(save_file, folder=None):
    """存档 -> 它的关卡数据文件名（蚁皇浆余额就存在那个文件里）"""
    declared = info(save_file, folder).leveldata
    if declared:
        return '%s.sav' % declared
    stem, ext = os.path.splitext(save_file)
    return '%sLevelData%s' % (stem, ext or '.sav')
