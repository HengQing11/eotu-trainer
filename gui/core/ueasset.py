# -*- coding: utf-8 -*-
"""UE4 uasset / uexp 解析 —— 读名字表、遍历 DataTable、定位浮点数值

UE4.26/4.27 的 DataTable 存法：
  .uasset 里是包头 + 名字表（所有字符串）
  .uexp 里是数据本身：[UObject 属性...None] + int32(恒0) + int32(行数) + 各行数据

行数据 = FName 行名 + 一串 tagged properties。
每个属性 = FName 属性名 / FName 类型名 / int32 Size / int32 ArrayIndex /
           [EnumProperty: FName 枚举名 / ArrayProperty: FName 元素类型]
           1 字节 有无GUID / Size 字节的值

数值就是定长 4 字节，所以改数值是**等长原地覆盖**，文件大小不变。
"""
import csv
import os
import struct

TAG = 0x9E2A83C1


class R(object):
    def __init__(self, d, p=0):
        self.d = d
        self.p = p

    def i32(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]
        self.p += 4
        return v

    def u32(self):
        v = struct.unpack_from('<I', self.d, self.p)[0]
        self.p += 4
        return v

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def f32(self):
        v = struct.unpack_from('<f', self.d, self.p)[0]
        self.p += 4
        return v

    def raw(self, n):
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

    def fstr(self):
        n = self.i32()
        if n == 0:
            return ''
        if n < 0:
            n = -n
            s = self.d[self.p:self.p + n * 2 - 2].decode('utf-16le', 'replace')
            self.p += n * 2
            return s
        s = self.d[self.p:self.p + n - 1].decode('latin1', 'replace')
        self.p += n
        return s


def parse_header(d):
    r = R(d)
    if r.u32() != TAG:
        raise ValueError('不是 UE 资产文件（包头魔数不对）')
    legacy = r.i32()
    if legacy != -4:
        r.i32()
    ue4ver = r.i32()
    r.i32()
    if legacy <= -8:
        r.i32()
    if legacy <= -2:
        cnt = r.i32()
        r.p += cnt * 20
    r.i32()                                    # TotalHeaderSize
    pkgname = r.fstr()
    r.u32()                                    # PackageFlags
    name_count = r.i32()
    name_off = r.i32()
    if ue4ver >= 459:
        r.i32()
        r.i32()
    out = dict(legacy=legacy, ue4ver=ue4ver, pkgname=pkgname,
               name_count=name_count, name_off=name_off, header_end=r.p)
    if ue4ver >= 510:
        out['softobj_count'] = r.i32()
        out['softobj_off'] = r.i32()
    out['export_count'] = r.i32()
    out['export_off'] = r.i32()
    out['import_count'] = r.i32()
    out['import_off'] = r.i32()
    return out


def parse_names(d, off, cnt):
    r = R(d, off)
    names = []
    for _ in range(cnt):
        names.append(r.fstr())
        r.p += 4                               # 两个 hash
    return names, r.p


def fname(r, names):
    idx = r.i32()
    num = r.i32()
    if idx < 0 or idx >= len(names):
        raise ValueError('FName 索引越界: %d (位置 %d)' % (idx, r.p - 8))
    s = names[idx]
    return s if num == 0 else '%s_%d' % (s, num - 1)


TAGS = []


def parse_props(r, names, depth=0):
    """读一段 tagged properties，遇到 None 结束"""
    out = {}
    while True:
        p0 = r.p
        name = fname(r, names)
        if name == 'None':
            return out
        typ = fname(r, names)
        struct_name = bool_val = enum_name = None
        if typ == 'StructProperty':
            struct_name = fname(r, names)
        elif typ == 'BoolProperty':
            bool_val = r.u8()
        size = r.i32()
        arr_idx = r.i32()
        if typ in ('EnumProperty', 'ByteProperty'):
            enum_name = fname(r, names)
        elif typ in ('ArrayProperty', 'SetProperty'):
            fname(r, names)
        elif typ == 'MapProperty':
            fname(r, names)
            fname(r, names)
        has_guid = r.u8()
        if has_guid:
            r.raw(16)
        start = r.p
        TAGS.append((p0, depth, name, typ, size, arr_idx, bool_val,
                     struct_name, enum_name, start))
        if typ == 'BoolProperty':
            val = bool_val
            if size:
                r.raw(size)
        elif typ == 'StructProperty':
            if 0 < size and depth < 6:
                try:
                    val = parse_props(R(r.d, r.p), names, depth + 1)
                except Exception:              # noqa: BLE001
                    val = r.raw(size).hex()
            else:
                val = r.raw(size).hex()
        elif typ == 'FloatProperty':
            val = struct.unpack_from('<f', r.d, r.p)[0]
        elif typ == 'IntProperty':
            val = struct.unpack_from('<i', r.d, r.p)[0]
        elif typ == 'EnumProperty':
            try:
                val = fname(R(r.d, r.p), names)
            except Exception:                  # noqa: BLE001
                val = r.raw(size).hex()
        else:
            val = r.raw(size).hex()
        r.p = start + size
        out[name] = val


def load_names(uasset):
    a = open(uasset, 'rb').read()
    h = parse_header(a)
    names, _ = parse_names(a, h['name_off'], h['name_count'])
    return a, h, names


def parse_table(uasset, uexp, want_rows=None):
    """-> (names, [(行名, {属性: 值})])"""
    _a, _h, names = load_names(uasset)
    d = open(uexp, 'rb').read()
    r = R(d)
    parse_props(r, names)
    r.i32()
    nrows = r.i32()
    rows = []
    for _ in range(nrows):
        rn = fname(r, names)
        props = parse_props(r, names)
        if want_rows is None or rn in want_rows:
            rows.append((rn, props))
    return names, rows


def collect_floats(uasset, uexp):
    """定位所有可改的 4 字节浮点 -> (bytearray, {(行名, 属性): (值偏移, 旧值)})

    只收顶层属性（depth==0），嵌套在结构里的不动。
    """
    _a, _h, names = load_names(uasset)
    d = bytearray(open(uexp, 'rb').read())
    r = R(d)
    parse_props(r, names)
    r.i32()
    nrows = r.i32()
    table = {}
    for _ in range(nrows):
        rn = fname(r, names)
        TAGS.clear()
        parse_props(r, names)
        for t in TAGS:
            if t[1] != 0:
                continue
            _off, _dep, pname, ptyp, psize, _ai, _bv, _sn, _en, voff = t
            if ptyp == 'FloatProperty' and psize == 4:
                table[(rn, pname)] = (voff, struct.unpack_from('<f', d, voff)[0])
    return d, table


def list_strings(uasset):
    """uasset 名字表里的全部字符串（用于找 /Game/... 资产引用）"""
    _a, _h, names = load_names(uasset)
    return names


def table_csv(uasset, uexp, out_csv):
    names, rows = parse_table(uasset, uexp)
    keys = []
    for _rn, p in rows:
        for k in p:
            if k not in keys:
                keys.append(k)
    with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['RowName'] + keys)
        for rn, p in rows:
            w.writerow([rn] + [p.get(k, '') for k in keys])
    return keys, len(rows)
