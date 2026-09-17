# -*- coding: utf-8 -*-
"""进程内存读写 —— 「游戏运行中生效」的基础能力

## 为什么必须有这一层
游戏运行时只认内存里的值。改存档文件它看不见，等它存盘还会用内存的值**覆盖**回去。
所以「运行中生效」只有一条路：改游戏进程的内存。

反过来还有个好处：值改在内存里之后，游戏**自己**会在下次存盘时把它写进存档。

## 能力范围
- 找进程 / 枚举可读内存区域 / 读 / 写 / 按值扫描
- 蚁皇浆、加点点数、以及后续的关卡内作弊（资源、单位）都建立在这上面

## 安全约定（调用方必须遵守）
1. **先只读、再写** —— 定位没确认唯一之前不要写
2. 写完**立刻回读校验**
3. 只改「已知类型、固定宽度」的值（int32 / float），绝不按偏移瞎写结构

仅 Windows。用 ctypes 直接调 kernel32，不需要第三方库、不需要管理员权限。
"""
import ctypes
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes

k32 = ctypes.WinDLL('kernel32', use_last_error=True)

# ------------------------------------------------------------------ 常量

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400
ACCESS = (PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
          | PROCESS_QUERY_INFORMATION)

MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
# 可读的页保护：RO / RW / WRITECOPY / EXEC_RO / EXEC_RW / EXEC_WC
# （故意不含 0x10 = PAGE_EXECUTE 和 0x01 = NOACCESS）
READABLE = 0xEE
# 可写的页保护：RW / WRITECOPY / EXEC_RW / EXEC_WC
WRITABLE_PROT = (0x04, 0x08, 0x40, 0x80)

TH32CS_SNAPPROCESS = 0x00000002
MAX_USER_ADDR = 0x7FFFFFFF0000            # 64 位用户空间上限

_TYPE_FMT = {
    'int32': '<i', 'uint32': '<I', 'int64': '<q', 'float': '<f', 'double': '<d',
}
_TYPE_SIZE = {'int32': 4, 'uint32': 4, 'int64': 8, 'float': 4, 'double': 8}


class MemError(Exception):
    """内存操作失败"""


# ------------------------------------------------------------------ 结构体

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p),
                ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wintypes.DWORD),
                ('PartitionId', wintypes.WORD),
                ('RegionSize', ctypes.c_size_t),
                ('State', wintypes.DWORD),
                ('Protect', wintypes.DWORD),
                ('Type', wintypes.DWORD)]


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD),
                ('cntUsage', wintypes.DWORD),
                ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)),
                ('th32ModuleID', wintypes.DWORD),
                ('cntThreads', wintypes.DWORD),
                ('th32ParentProcessID', wintypes.DWORD),
                ('pcPriClassBase', ctypes.c_long),
                ('dwFlags', wintypes.DWORD),
                ('szExeFile', ctypes.c_char * 260)]


k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.restype = wintypes.BOOL
k32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                               ctypes.POINTER(MEMORY_BASIC_INFORMATION),
                               ctypes.c_size_t]
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
k32.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
k32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]


# ------------------------------------------------------------------ 找进程

def find_pids(exe_name):
    """按可执行文件名找进程 id -> [pid]（不区分大小写）"""
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value or not snap:
        raise MemError('枚举进程失败')
    out = []
    try:
        ent = PROCESSENTRY32()
        ent.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = k32.Process32First(snap, ctypes.byref(ent))
        want = exe_name.lower()
        while ok:
            name = ent.szExeFile.decode('latin1', 'ignore')
            if name.lower() == want:
                out.append(int(ent.th32ProcessID))
            ok = k32.Process32Next(snap, ctypes.byref(ent))
    finally:
        k32.CloseHandle(snap)
    return out


# ------------------------------------------------------------------ 进程

class Process(object):
    """一个打开的进程句柄"""

    def __init__(self, pid, access=ACCESS):
        self.pid = pid
        h = k32.OpenProcess(access, False, pid)
        if not h:
            raise MemError('打不开进程 %d（错误码 %d）—— 可能需要更高的权限'
                           % (pid, ctypes.get_last_error()))
        self.handle = h
        self._regions = None

    def close(self):
        if self.handle:
            k32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------------------------------------------------------- 内存区域
    def regions(self, refresh=False, writable_only=False):
        """可读的已提交区域 -> [(基址, 大小)]

        writable_only=True 时只要**可写**段 —— 游戏运行时的数值（蚁皇浆、
        加点、关卡资源）都在可写堆里，代码段和只读资源段扫了纯属浪费时间。
        """
        cache_key = 'w' if writable_only else 'r'
        if self._regions is not None and self._regions[0] == cache_key and not refresh:
            return self._regions[1]

        out = []
        addr = 0
        mbi = MEMORY_BASIC_INFORMATION()
        while addr < MAX_USER_ADDR:
            n = k32.VirtualQueryEx(self.handle, ctypes.c_void_p(addr),
                                   ctypes.byref(mbi), ctypes.sizeof(mbi))
            if not n:
                break
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize or 0
            if size == 0:
                break
            prot = mbi.Protect & 0xFF
            if (mbi.State == MEM_COMMIT
                    and not (mbi.Protect & PAGE_GUARD)
                    and prot != PAGE_NOACCESS
                    and (prot & READABLE)
                    and (not writable_only or (prot in WRITABLE_PROT))):
                out.append((base, size))
            addr = base + size

        # 相邻区域合并 —— 不合并的话是上万个碎片，每个都要单独发一次
        # ReadProcessMemory，实测把速度拖到 94 MB/s。合并后块数少两个数量级。
        merged = []
        for base, size in out:
            if merged and merged[-1][0] + merged[-1][1] == base:
                merged[-1] = (merged[-1][0], merged[-1][1] + size)
            else:
                merged.append((base, size))
        self._regions = (cache_key, merged)
        return merged

    def region_bytes(self):
        return sum(s for _b, s in self.regions())

    # ---------------------------------------------------------- 读 / 写
    def read(self, addr, size):
        """读一段内存 -> bytes；读不到返回 None"""
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t()
        ok = k32.ReadProcessMemory(self.handle, ctypes.c_void_p(addr), buf,
                                   size, ctypes.byref(got))
        if not ok or got.value == 0:
            return None
        return buf.raw[:got.value]

    def read_value(self, addr, kind='int32'):
        """读一个定长值；读不到返回 None"""
        sz = _TYPE_SIZE[kind]
        raw = self.read(addr, sz)
        if not raw or len(raw) < sz:
            return None
        return struct.unpack(_TYPE_FMT[kind], raw[:sz])[0]

    def write(self, addr, data):
        """写一段字节 -> 是否成功"""
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        done = ctypes.c_size_t()
        ok = k32.WriteProcessMemory(self.handle, ctypes.c_void_p(addr), buf,
                                    len(data), ctypes.byref(done))
        return bool(ok and done.value == len(data))

    def write_value(self, addr, value, kind='int32'):
        """写一个定长值，写完**立刻回读校验** -> (成功, 回读到的值)"""
        if not self.write(addr, struct.pack(_TYPE_FMT[kind], value)):
            return False, None
        return True, self.read_value(addr, kind)

    # ---------------------------------------------------------- 扫描
    def scan_bytes(self, needle, limit=200000, progress=None,
                   chunk_mb=32, writable_only=True, threads=8, max_region_mb=0):
        """按字节序列扫描 -> [地址]

        needle 是任意字节序列：字符串、多字节特征、打包好的数值都行。
        分块读 + 块间重叠（重叠 = 长度-1 字节），避免特征跨块边界漏掉。

        writable_only=True 只扫可写段 —— 运行时数值都在可写堆里，代码段和
        只读资源段扫了纯属浪费时间；实测只扫 <1MB 的小区域只要 0.28 秒
        （845 MB），全量 4.5 GB 要 6 秒。

        threads：并发线程数。**这个很关键** —— 游戏内存里大部分被换出到
        页面文件，跨进程读它们是在等磁盘（实测同一进程内热内存 11 GB/s，
        冷内存只有 170 MB/s）。单线程扫一遍要 50 秒，靠并发叠等待才实用。
        ctypes 调 Win32 会释放 GIL，所以线程是真并行。
        max_region_mb：只扫不超过这么大（MB）的区域；0 = 不限。
        进度回调 progress(已扫字节, 总字节)。
        """
        needle = bytes(needle)
        sz = len(needle)
        chunk = chunk_mb * 1024 * 1024
        overlap = sz - 1
        regs = self.regions(writable_only=writable_only)
        if max_region_mb:
            cap = max_region_mb * 1024 * 1024
            regs = [(b, s) for b, s in regs if s <= cap]
        total = sum(s for _b, s in regs)
        if not regs:
            return []

        lock = threading.Lock()
        state = {'done': 0}
        hits = []

        def scan_regions(my_regs):
            found = []
            buf = ctypes.create_string_buffer(chunk + overlap)
            bufaddr = ctypes.addressof(buf)
            got = ctypes.c_size_t()
            local_done = 0
            for base, size in my_regs:
                off = 0
                while off < size:
                    n = min(chunk + overlap, size - off)
                    if n < sz:
                        break
                    ok = k32.ReadProcessMemory(
                        self.handle, ctypes.c_void_p(base + off),
                        ctypes.c_void_p(bufaddr), n, ctypes.byref(got))
                    if ok and got.value >= sz:
                        # ⚠ 别写成 buf.raw[:n] —— buf.raw 每次都把整个
                        # buffer 复制成 bytes，6000 多个区域就是上百 GB 的
                        # 无用复制。string_at 只复制实际读到的长度。
                        blk = ctypes.string_at(bufaddr, got.value)
                        start = 0
                        while True:
                            i = blk.find(needle, start)
                            if i < 0:
                                break
                            # 落在重叠区的命中，上一块已经报过了
                            if not (off > 0 and i < overlap):
                                # 线程内也要限量 —— 全 0 这类海量命中会把
                                # 每个线程的列表撑到 MemoryError（踩过）
                                if len(found) >= limit:
                                    return found
                                found.append(base + off + i)
                            start = i + 1
                    local_done += n - overlap if n > overlap else n
                    off += chunk
                if progress:
                    with lock:
                        state['done'] += local_done
                        local_done = 0
                        progress(state['done'], total)
            if progress and local_done:
                with lock:
                    state['done'] += local_done
                    progress(state['done'], total)
            return found

        nthreads = max(1, min(threads, len(regs)))
        if nthreads == 1:
            return scan_regions(regs)[:limit]

        # 按总字节数均衡分配到各线程（大块优先，避免某个线程只摊到碎块）
        buckets = [[] for _ in range(nthreads)]
        load = [0] * nthreads
        for b, s in sorted(regs, key=lambda x: -x[1]):
            i = load.index(min(load))
            buckets[i].append((b, s))
            load[i] += s

        with ThreadPoolExecutor(max_workers=nthreads) as ex:
            for part in ex.map(scan_regions, buckets):
                hits.extend(part)
                if len(hits) >= limit:
                    break
        return hits[:limit]

    def scan_value(self, value, kind='int32', **kw):
        """按数值扫描 -> [地址]

        kind：int32 / uint32 / int64 / float / double
        其余参数见 scan_bytes（threads / writable_only / max_region_mb / progress）。
        """
        return self.scan_bytes(struct.pack(_TYPE_FMT[kind], value), **kw)

    def scan_str(self, text, encoding='utf-8', **kw):
        """按字符串扫描 -> [地址]（UE4 的 FName 池里存的就是这类明文属性名）"""
        return self.scan_bytes(text.encode(encoding), **kw)

    def scan_values(self, pairs, limit=200000, progress=None):
        """按多个值扫描 -> {地址: 值}，pairs = [(值, kind), ...]

        用于「同一块区域里同时存在多个已知值」的特征定位。
        """
        found = {}
        for value, kind in pairs:
            for a in self.scan_value(value, kind, limit=limit, progress=progress):
                found[a] = (value, kind)
        return found
