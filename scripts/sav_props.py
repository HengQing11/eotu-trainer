"""GVAS 存档属性读取（已用已知值校准的正确偏移版）

属性 tag 布局（本机 Colony1LevelData.sav 用 RoyalJelly=999999 实测校准）:
    FString 属性名
    FString 类型名
    int32  Size
    int32  ArrayIndex
    1 byte bHasPropertyGuid        <- 关键：这个字节以前被漏掉了，导致所有 int 被读成 0
    Size 字节 值
    [EnumProperty: FName 枚举类型名 在 ArrayIndex 之后、guid 标志之前]

因此 int/float 值的偏移 = Size 字段偏移 + 9
"""
import struct
import re

TYPES = [b'IntProperty', b'BoolProperty', b'FloatProperty', b'EnumProperty',
         b'NameProperty', b'StrProperty', b'ArrayProperty', b'StructProperty',
         b'MapProperty', b'ByteProperty', b'DoubleProperty', b'TextProperty',
         b'Int64Property', b'UInt32Property', b'SetProperty']

_NAME_RE = re.compile(rb'[A-Za-z_][A-Za-z0-9_]{0,60}\Z')


def iter_tags(d):
    """按文件顺序产出 (类型串偏移, 属性名, 类型名)"""
    pats = []
    for t in TYPES:
        p = struct.pack('<i', len(t) + 1) + t + b'\x00'
        for m in re.finditer(re.escape(p), d):
            pats.append((m.start(), t.decode()))
    pats.sort()
    for off, typ in pats:
        name = None
        for back in range(1, 80):
            s = off - back
            if s < 4:
                break
            ln = struct.unpack_from('<i', d, s - 4)[0]
            if 1 < ln <= 70 and s + ln <= off:
                raw = d[s:s + ln]
                if raw.endswith(b'\x00') and off == s + ln and _NAME_RE.match(raw[:-1]):
                    name = raw[:-1].decode()
                    break
        if name is None:
            continue
        yield off, name, typ


def read_value(d, off, typ):
    """off = 类型名 FString 的起点"""
    plen = struct.pack('<i', len(typ) + 1)
    base = off + len(plen) + len(typ) + 1      # 指向 Size 字段
    try:
        size = struct.unpack_from('<i', d, base)[0]
        if typ == 'IntProperty' and size == 4:
            return struct.unpack_from('<i', d, base + 9)[0]
        if typ == 'FloatProperty' and size == 4:
            return round(struct.unpack_from('<f', d, base + 9)[0], 4)
        if typ == 'BoolProperty':
            # 实测布局: Size(4)=0 + ArrayIndex(4)=0 + 值(1) + guid标志(1)
            return bool(d[base + 8])
        if typ in ('NameProperty', 'StrProperty'):
            ln = struct.unpack_from('<i', d, base + 9)[0]
            if 0 < ln < 200:
                return d[base + 13:base + 13 + ln - 1].decode('latin1', 'replace')
        if typ == 'EnumProperty':
            ln = struct.unpack_from('<i', d, base + 9)[0]
            if 0 < ln < 200:
                return d[base + 13:base + 13 + ln - 1].decode('latin1', 'replace')
    except Exception:
        pass
    return None


def read_int(d, name, nth=0):
    """按属性名读取所有匹配的 int 值"""
    pat = struct.pack('<i', len(name) + 1) + name.encode() + b'\x00'
    out = []
    for m in re.finditer(re.escape(pat), d):
        v = read_value(d, m.end(), 'IntProperty')
        if v is not None:
            out.append((m.start(), v))
    return out


def show(d, name, typ=None):
    pat = struct.pack('<i', len(name) + 1) + name.encode() + b'\x00'
    for m in re.finditer(re.escape(pat), d):
        print('  %-46s @%-8d %s' % (name, m.start(), hexdump(d, m.start(), 56)))


def hexdump(d, off, n):
    seg = d[off:off + n]
    return (' '.join('%02x' % b for b in seg) + ' | ' +
            ''.join(chr(b) if 32 <= b < 127 else '.' for b in seg))


if __name__ == '__main__':
    import sys
    S = r'C:/Users/beimo/AppData/Local/EotU/Saved/SaveGames/'
    d = open(S + sys.argv[1], 'rb').read()
    filt = sys.argv[2] if len(sys.argv) > 2 else None
    for off, name, typ in iter_tags(d):
        if filt and filt.lower() not in name.lower():
            continue
        print('  %-8d %-48s %-14s %s' % (off, name, typ, read_value(d, off, typ)))
