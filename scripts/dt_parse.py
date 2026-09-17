"""解析 UE4 DataTable (.uasset + .uexp) -> CSV"""
import struct, sys, os, json, csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue4dt import parse_header, parse_names


class R:
    def __init__(self, d, p=0):
        self.d = d; self.p = p

    def i32(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]; self.p += 4; return v

    def u8(self):
        v = self.d[self.p]; self.p += 1; return v

    def f32(self):
        v = struct.unpack_from('<f', self.d, self.p)[0]; self.p += 4; return v

    def raw(self, n):
        b = self.d[self.p:self.p + n]; self.p += n; return b


def fname(r, names):
    idx = r.i32(); num = r.i32()
    if idx < 0 or idx >= len(names):
        raise ValueError('FName idx out of range: %d (at %d)' % (idx, r.p - 8))
    s = names[idx]
    return s if num == 0 else '%s_%d' % (s, num - 1)


TAGS = []


def parse_props(r, names, depth=0):
    """读取一段 tagged properties，返回 dict；遇到 Name=='None' 结束"""
    out = {}
    while True:
        _p0 = r.p
        name = fname(r, names)
        if name == 'None':
            return out
        typ = fname(r, names)
        struct_name = None
        bool_val = None
        enum_name = None
        inner = None
        if typ == 'StructProperty':
            struct_name = fname(r, names)
        elif typ == 'BoolProperty':
            bool_val = r.u8()
        size = r.i32()
        arr_idx = r.i32()
        # 注意：EnumName / InnerType 在 Size+ArrayIndex 之后
        if typ in ('EnumProperty', 'ByteProperty'):
            enum_name = fname(r, names)
        elif typ in ('ArrayProperty', 'SetProperty'):
            inner = fname(r, names)
        elif typ == 'MapProperty':
            inner = fname(r, names); fname(r, names)
        has_guid = r.u8()
        if has_guid:
            r.raw(16)
        start = r.p
        TAGS.append((_p0, depth, name, typ, size, arr_idx, bool_val, struct_name,
                     enum_name, start))
        if typ == 'BoolProperty':
            val = bool_val
            if size:
                r.raw(size)
        elif typ == 'StructProperty':
            if size > 0 and depth < 6:
                sub = R(r.d, r.p)
                try:
                    val = parse_props(sub, names, depth + 1)
                except Exception:
                    val = r.raw(size).hex()
            else:
                val = r.raw(size).hex()
            r.p = start + size
        elif typ == 'FloatProperty':
            val = struct.unpack_from('<f', r.d, r.p)[0]
        elif typ == 'IntProperty':
            val = struct.unpack_from('<i', r.d, r.p)[0]
        elif typ == 'EnumProperty':
            sub = R(r.d, r.p)
            try:
                val = fname(sub, names)
            except Exception:
                val = r.raw(size).hex()
        elif typ == 'ByteProperty':
            val = r.raw(size).hex()
        elif typ in ('ArrayProperty', 'SetProperty', 'MapProperty', 'StrProperty', 'NameProperty'):
            val = r.raw(size).hex()
        else:
            val = r.raw(size).hex()
        r.p = start + size
        out[name] = val


def parse_table(uasset, uexp, verbose=True):
    a = open(uasset, 'rb').read()
    h = parse_header(a)
    names, _ = parse_names(a, h['name_off'], h['name_count'])
    d = open(uexp, 'rb').read()
    r = R(d)
    # 1) UObject 自身的 tagged properties（RowStruct 等），以 'None' 结束
    uobj = parse_props(r, names)
    if verbose:
        print('UObject 属性:', uobj, ' 结束于', r.p)
    # 2) 两个 int32（第一个恒为 0），第二个是行数
    _zero = r.i32()
    nrows = r.i32()
    if verbose:
        print('前导 int32 =', _zero, ' NumRows =', nrows, ' uexp大小 =', len(d))
    rows = []
    for i in range(nrows):
        rn = fname(r, names)
        props = parse_props(r, names)
        rows.append((rn, props))
        if verbose and i < 2:
            print('--- 行 %d: %s ---' % (i, rn))
            for k, v in list(props.items())[:16]:
                print('     %-30s = %s' % (k, v))
    if verbose:
        print('解析结束位置 %d / %d  残余 %d 字节' % (r.p, len(d), len(d) - r.p))
    return names, rows


if __name__ == '__main__':
    ua, ux = sys.argv[1], sys.argv[2]
    names, rows = parse_table(ua, ux)
    keys = []
    for _, p in rows:
        for k in p:
            if k not in keys:
                keys.append(k)
    print()
    print('字段数 =', len(keys), keys)
    out = sys.argv[3] if len(sys.argv) > 3 else None
    if out:
        with open(out, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['RowName'] + keys)
            for rn, p in rows:
                w.writerow([rn] + [p.get(k, '') for k in keys])
        print('已写出 ->', out, len(rows), '行')
