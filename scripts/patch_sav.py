"""UE4 GVAS 存档字段原地改写工具

用法:
  读取:  python patch_sav.py read  <存档> [字段名...]
  改写:  python patch_sav.py set   <存档> <字段名>=<值> [<字段名>=<值> ...] [--out <输出>]

原理: GVAS 里 int 字段的字节模式固定为
  int32(名字长度) + 名字 + 0x00
  + int32(12) + "IntProperty" + 0x00
  + int32(4)                      <- size
  + int32(0)                      <- ArrayIndex
  + 1 字节 有无GUID
  + int32 数值                    <- 改写目标
所以数值偏移 = 模式起点 + 模式长度 + 5。全程等长原地覆盖，文件大小不变。
"""
import struct, sys, re, os, shutil


def pattern(field, typ='IntProperty'):
    return (struct.pack('<i', len(field) + 1) + field.encode() + b'\x00'
            + struct.pack('<i', len(typ) + 1) + typ.encode() + b'\x00')


def find_int(d, field):
    """返回 [(模式起点, 数值偏移, 当前值)]"""
    pat = pattern(field) + struct.pack('<i', 4)
    out = []
    for m in re.finditer(re.escape(pat), d):
        voff = m.start() + len(pat) + 5
        if voff + 4 > len(d):
            continue
        out.append((m.start(), voff, struct.unpack_from('<i', d, voff)[0]))
    return out


def find_bool(d, field):
    """bool 字段：数值是 1 字节，在模式起点 + 模式长度 + 1 处"""
    pat = pattern(field, 'BoolProperty')
    out = []
    for m in re.finditer(re.escape(pat), d):
        voff = m.start() + len(pat) + 1
        if voff >= len(d):
            continue
        out.append((m.start(), voff, d[voff]))
    return out


def cmd_read(path, fields=None):
    d = open(path, 'rb').read()
    print('文件: %s  大小: %d' % (os.path.basename(path), len(d)))
    # 先扫出文件里出现过的所有属性名做参考
    names = sorted({m.group().decode() for m in re.finditer(rb'[A-Za-z][A-Za-z0-9_]{2,40}', d)})
    target = fields or [n for n in names if 'Jelly' in n or 'Improvment' in n]
    for f in target:
        for typ, fn, fmt in (('IntProperty', find_int, '%d'), ('BoolProperty', find_bool, '%s')):
            hits = fn(d, f)
            if hits:
                for i, (s, v, val) in enumerate(hits):
                    show = (str(bool(val)) if typ == 'BoolProperty' else str(val))
                    print('  %-32s %-14s #%d  模式@%-8d 值@%-8d = %s'
                          % (f, typ, i, s, v, show))


def cmd_set(path, pairs, out):
    d = bytearray(open(path, 'rb').read())
    for f, raw in pairs:
        hits = find_int(d, f)
        if not hits:
            print('  [!] 未找到 int 字段: %s' % f)
            continue
        val = int(raw)
        for i, (s, v, old) in enumerate(hits):
            struct.pack_into('<i', d, v, val)
            print('  %-32s #%d  %d -> %d   (值偏移 %d)' % (f, i, old, val, v))
    dst = out or path
    if out and os.path.abspath(out) != os.path.abspath(path):
        shutil.copy2(path, out)
        d2 = bytearray(open(out, 'rb').read())
        for f, raw in pairs:
            for i, (s, v, old) in enumerate(find_int(d2, f)):
                struct.pack_into('<i', d2, v, int(raw))
        d = d2
    open(dst, 'wb').write(bytes(d))
    print('已写出 -> %s  (%d 字节，与原文件%s)' %
          (dst, len(d), '等长' if len(d) == os.path.getsize(path) else '长度变化!'))


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(1)
    mode = a[0]
    if mode == 'read':
        cmd_read(a[1], a[2:] or None)
    elif mode == 'set':
        out = None
        rest = []
        i = 2
        while i < len(a):
            if a[i] == '--out':
                out = a[i + 1]; i += 2; continue
            rest.append(a[i]); i += 1
        pairs = []
        for x in rest:
            k, _, v = x.partition('=')
            pairs.append((k, v))
        cmd_set(a[1], pairs, out)
    else:
        print(__doc__)
