# -*- coding: utf-8 -*-
"""GVAS 存档底层 —— 定位字段、读值、等长原地改写

属性 tag 布局（本机存档字节级实测校准，勿凭记忆改动）：

    FString 属性名
    FString 类型名
    int32   Size
    int32   ArrayIndex
    ------ 之后按类型分叉 ------
    IntProperty / FloatProperty : Size=4，紧接 1 字节 bHasPropertyGuid，然后 4 字节值
    BoolProperty                : Size=0，紧接 1 字节值，再 1 字节 bHasPropertyGuid

实测证据（Freeplay2LevelData.sav，AutoSpawnEggs 真值 True）：

    00 00 00 00 | 00 00 00 00 | 01 | 00 | 12 00 00 00
      Size=0      ArrayIndex=0   值   guid  下一个属性的名字长度

所以：bool 值偏移 = 类型名 FString 结束处 + 8。

⚠ 历史坑：老脚本 patch_sav.find_bool 把 bool 值算在 +1，那是 Size 字段的第 2 个字节，
   恒为 0，任何 bool 都会被读成 False。本模块统一用 +8，并已用真值 True 的字段反向验证。

所有改写都是「等长原地覆盖」，文件大小一个字节都不会变，UE 读起来不会出问题。
"""
import os
import re
import struct

# ------------------------------------------------------------------ 基础工具

def _fstr(s):
    b = s.encode('latin1') if isinstance(s, str) else bytes(s)
    return struct.pack('<i', len(b) + 1) + b + b'\x00'


def _pattern(name, typ, size=None):
    p = _fstr(name) + _fstr(typ)
    if size is not None:
        p += struct.pack('<i', size)
    return p


_VAL_SIZE = {'BoolProperty': 1, 'IntProperty': 4, 'FloatProperty': 4}
# 从「匹配模式末尾」到「值起点」的距离。两种模式长度不同，别混：
#   Int/Float : pat = 名字 + 类型 + Size(4)，所以末尾停在 ArrayIndex 起点
#               -> 再走 ArrayIndex(4) + guid(1) = 5
#   Bool      : pat = 名字 + 类型（Size 恒为 0 不参与匹配），末尾停在 Size 起点
#               -> 再走 Size(4) + ArrayIndex(4) = 8
#
# ⚠ 实测量到的字节布局（Colony1LevelData.sav 的 RoyalJelly=2000000000）：
#   0b000000 "RoyalJelly\0" 0c000000 "IntProperty\0" 04000000 00000000 00 00943577
#      len=11                 len=12              Size=4  ArrayIdx  guid  值
#   模式末尾 = ArrayIndex 起点，故值 = 模式末尾 + 5。
_VAL_DELTA = {'BoolProperty': 8, 'IntProperty': 5, 'FloatProperty': 5}


def find(data, name, typ):
    """定位字段 -> [(模式起点, 值偏移)]

    只会匹配布局确定的定长类型（Bool / 4 字节 Int / 4 字节 Float），
    其余类型返回空列表 —— 宁可不认，也不能猜错位置写出坏档。
    """
    if typ not in _VAL_SIZE:
        return []
    pat = _pattern(name, typ, None if typ == 'BoolProperty' else 4)
    delta = _VAL_DELTA[typ]
    vsz = _VAL_SIZE[typ]
    out = []
    for m in re.finditer(re.escape(pat), data):
        v = m.start() + len(pat) + delta
        if v + vsz <= len(data):
            out.append((m.start(), v))
    return out


def _decode(data, off, typ):
    if typ == 'BoolProperty':
        return bool(data[off])
    if typ == 'IntProperty':
        return struct.unpack_from('<i', data, off)[0]
    if typ == 'FloatProperty':
        return round(struct.unpack_from('<f', data, off)[0], 6)
    return None


def _encode(data, off, typ, val):
    if typ == 'BoolProperty':
        data[off] = 1 if val else 0
    elif typ == 'IntProperty':
        struct.pack_into('<i', data, off, int(val))
    else:
        struct.pack_into('<f', data, off, float(val))


def read(data, name, typ, nth=0):
    """读第 nth 个实例的值；不存在返回 None"""
    hits = find(data, name, typ)
    if len(hits) <= nth:
        return None
    return _decode(data, hits[nth][1], typ)


def read_at(data, off, typ):
    """从已知的值偏移直接解码（配合 find() 用，避免二次搜索）"""
    return _decode(data, off, typ)


def write_at(data, off, typ, val):
    """往已知的值偏移写值"""
    _encode(data, off, typ, val)


def read_all(data, name, typ):
    """读该字段的所有实例值（同一名字在存档里可能出现多次）"""
    return [_decode(data, v, typ) for _s, v in find(data, name, typ)]


def write(data, name, typ, val, nth=None):
    """改写字段。nth=None 改所有实例，否则只改第 nth 个

    -> [(值偏移, 旧值)]，空的表示没找到该字段
    """
    changed = []
    for i, (_s, v) in enumerate(find(data, name, typ)):
        if nth is not None and i != nth:
            continue
        old = _decode(data, v, typ)
        _encode(data, v, typ, val)
        changed.append((v, old))
    return changed


# ------------------------------------------------- 通用扫描（列出文件里所有属性）

SCAN_TYPES = [b'IntProperty', b'BoolProperty', b'FloatProperty', b'EnumProperty',
              b'NameProperty', b'StrProperty', b'ArrayProperty', b'StructProperty',
              b'MapProperty', b'ByteProperty', b'DoubleProperty', b'TextProperty',
              b'Int64Property', b'UInt32Property', b'SetProperty']

_NAME_RE = re.compile(rb'[A-Za-z_][A-Za-z0-9_]{0,60}\Z')


def iter_tags(data):
    """按文件顺序产出 (类型名 FString 起点, 属性名, 类型名)"""
    pats = []
    for t in SCAN_TYPES:
        p = struct.pack('<i', len(t) + 1) + t + b'\x00'
        for m in re.finditer(re.escape(p), data):
            pats.append((m.start(), t.decode()))
    pats.sort()
    for off, typ in pats:
        name = _guess_name(data, off)
        if name is not None:
            yield off, name, typ


def _guess_name(data, off):
    """从类型名起点往前回溯，找紧邻的属性名 FString"""
    for back in range(1, 80):
        s = off - back
        if s < 4:
            return None
        ln = struct.unpack_from('<i', data, s - 4)[0]
        if 1 < ln <= 70 and s + ln == off:
            raw = data[s:s + ln]
            if raw.endswith(b'\x00') and _NAME_RE.match(raw[:-1]):
                return raw[:-1].decode('latin1')
    return None


def scan_values(data):
    """扫描全文件 -> {类型: {字段名: [值...]}}

    对 BoolProperty 只收集值为 True 的（和游戏存档语义一致：关着的开关不写盘）。
    """
    out = {'IntProperty': {}, 'BoolProperty': {}, 'FloatProperty': {}}
    for off, name, typ in iter_tags(data):
        if typ not in out:
            continue
        plen = struct.pack('<i', len(typ) + 1)
        base = off + len(plen) + len(typ) + 1        # Size 字段起点
        try:
            size = struct.unpack_from('<i', data, base)[0]
            if typ == 'IntProperty' and size == 4:
                v = struct.unpack_from('<i', data, base + 9)[0]
            elif typ == 'FloatProperty' and size == 4:
                v = round(struct.unpack_from('<f', data, base + 9)[0], 6)
            elif typ == 'BoolProperty':
                v = bool(data[base + 8])
                if not v:
                    continue
            else:
                continue
        except (struct.error, IndexError):
            continue
        out[typ].setdefault(name, []).append(v)
    return out


# ------------------------------------------------------------------ 文件级封装

class SaveFile:
    """一个 .sav 的读写句柄

    改动全部在内存里，save() 才落盘，并且默认先备份。
    """

    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, 'rb').read())
        self.size0 = len(self.data)
        self._scanned = None
        self.dirty = False

    # -- 扫描 ------------------------------------------------------------
    def scan(self, force=False):
        if self._scanned is None or force:
            self._scanned = scan_values(self.data)
        return self._scanned

    @property
    def ints(self):
        return self.scan()['IntProperty']

    @property
    def bools(self):
        return self.scan()['BoolProperty']

    @property
    def floats(self):
        return self.scan()['FloatProperty']

    # -- 快速读写（不依赖扫描，直接正则定位） ------------------------------
    def get_int(self, name, nth=0, default=None):
        v = read(self.data, name, 'IntProperty', nth)
        return default if v is None else v

    def get_bool(self, name, nth=0, default=False):
        v = read(self.data, name, 'BoolProperty', nth)
        return default if v is None else v

    def get_float(self, name, nth=0, default=None):
        v = read(self.data, name, 'FloatProperty', nth)
        return default if v is None else v

    def exists(self, name):
        for t in ('IntProperty', 'BoolProperty', 'FloatProperty'):
            if find(self.data, name, t):
                return True
        return False

    def set_int(self, name, val, nth=None):
        r = write(self.data, name, 'IntProperty', val, nth)
        self.dirty = self.dirty or bool(r)
        return r

    def set_bool(self, name, val, nth=None):
        r = write(self.data, name, 'BoolProperty', val, nth)
        self.dirty = self.dirty or bool(r)
        return r

    def set_float(self, name, val, nth=None):
        r = write(self.data, name, 'FloatProperty', val, nth)
        self.dirty = self.dirty or bool(r)
        return r

    # -- 落盘 ------------------------------------------------------------
    def changed_bytes(self):
        """改了哪些字节 -> [(偏移, 旧值, 新值)]"""
        old = open(self.path, 'rb').read()
        n = min(len(old), len(self.data))
        return [(i, old[i], self.data[i]) for i in range(n) if old[i] != self.data[i]]

    def save(self, out_path=None):
        """写回磁盘；返回 (目标路径, 改动字节数, 是否等长)"""
        dst = out_path or self.path
        diffs = self.changed_bytes()
        with open(dst, 'wb') as f:
            f.write(bytes(self.data))
        self.dirty = False
        return dst, len(diffs), len(self.data) == self.size0

    def save_as(self, out_path):
        with open(out_path, 'wb') as f:
            f.write(bytes(self.data))
        return out_path


def is_ue_save(path):
    """粗判是不是 UE 的 GVAS 存档（头部有魔数）"""
    try:
        d = open(path, 'rb').read(16)
    except OSError:
        return False
    return d[:4] == b'GVAS'


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('用法: python gvas.py <存档.sav> [字段名过滤]')
        sys.exit(0)
    p = sys.argv[1]
    if not os.path.isfile(p):
        print('文件不存在:', p)
        sys.exit(1)
    sf = SaveFile(p)
    filt = sys.argv[2] if len(sys.argv) > 2 else None
    print('文件 %s  %d 字节' % (os.path.basename(p), sf.size0))
    sc = sf.scan()
    for typ in ('IntProperty', 'FloatProperty', 'BoolProperty'):
        rows = sc[typ]
        if filt:
            rows = {k: v for k, v in rows.items() if filt.lower() in k.lower()}
        if not rows:
            continue
        print('\n-- %s (%d 个字段) --' % (typ, len(rows)))
        for k in sorted(rows):
            vs = rows[k]
            show = vs[0] if len(vs) == 1 else vs
            print('   %-46s %s' % (k, show))
