"""UE4.26/4.27 uasset 包头 + 名字表 + DataTable 行解析"""
import struct, sys, os


class R:
    def __init__(self, d):
        self.d = d
        self.p = 0

    def i32(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]; self.p += 4; return v

    def i64(self):
        v = struct.unpack_from('<q', self.d, self.p)[0]; self.p += 8; return v

    def u32(self):
        v = struct.unpack_from('<I', self.d, self.p)[0]; self.p += 4; return v

    def u8(self):
        v = self.d[self.p]; self.p += 1; return v

    def fstr(self):
        n = self.i32()
        if n == 0:
            return ''
        if n < 0:
            n = -n
            s = self.d[self.p:self.p + n * 2 - 2].decode('utf-16le', 'replace')
            self.p += n * 2
            return s
        s = self.d[self.p:self.p + n - 1].decode('latin1')
        self.p += n
        return s

    def guid(self):
        b = self.d[self.p:self.p + 16]; self.p += 16; return b.hex()


def parse_header(d):
    r = R(d)
    tag = r.u32()
    if tag != 0x9E2A83C1:
        raise ValueError('bad tag %08x' % tag)
    legacy = r.i32()
    if legacy != -4:
        r.i32()                      # LegacyUE3Version
    ue4ver = r.i32()
    r.i32()                          # LicenseeUE4
    if legacy <= -8:
        r.i32()                      # FileVersionUE5
    if legacy <= -2:
        cnt = r.i32()
        r.p += cnt * 20              # FGuid(16) + i32
    total_header = r.i32()
    pkgname = r.fstr()
    flags = r.u32()
    name_count = r.i32()
    name_off = r.i32()
    if ue4ver >= 459:                # UE4.26+: GatherableTextDataCount/Offset
        r.i32(); r.i32()
    if ue4ver >= 510:                # UE4.27: softobjectpaths
        pass
    out = dict(legacy=legacy, ue4ver=ue4ver, total_header=total_header,
               pkgname=pkgname, flags=flags, name_count=name_count,
               name_off=name_off, header_end=r.p)
    if ue4ver >= 510:
        out['softobj_count'] = r.i32(); out['softobj_off'] = r.i32()
    out['export_count'] = r.i32(); out['export_off'] = r.i32()
    out['import_count'] = r.i32(); out['import_off'] = r.i32()
    return out


def parse_names(d, off, cnt):
    r = R(d); r.p = off
    names = []
    for _ in range(cnt):
        s = r.fstr()
        r.p += 4                      # NonCasePreservingHash + CasePreservingHash
        names.append(s)
    return names, r.p


if __name__ == '__main__':
    p = sys.argv[1]
    d = open(p, 'rb').read()
    print('文件:', os.path.basename(p), '大小', len(d))
    h = parse_header(d)
    for k, v in h.items():
        print('   %-14s %s' % (k, v))
    names, end = parse_names(d, h['name_off'], h['name_count'])
    print()
    print('名字数 =', len(names), ' 名字表结束偏移 =', end,
          ' importOff =', h['import_off'], ' 差 =', h['import_off'] - end)
    print('前 12:', names[:12])
    print('后 8 :', names[-8:])
    for k in ['None', 'Health', 'AttackDamage', 'FloatProperty', 'IntProperty',
              'BoolProperty', 'StructProperty', 'EnumProperty', 'ArrayProperty',
              'CreatureStat', 'Temperament']:
        print('   %-18s -> %s' % (k, names.index(k) if k in names else '不存在'))
