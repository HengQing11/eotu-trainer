# -*- coding: utf-8 -*-
"""repak 封装 + 资产工作区管理（走 winproc，绝不弹控制台）

打包成 mod pak 的流程：
  1) 把解包好的资产树复制到**可写工作区**（原始副本不动，随时可还原）
  2) 在工作区里改文件（数值 uexp）
  3) repak pack 打成 .pak
  4) 把 pak 放进游戏 Paks 目录（只新增文件，不动任何原有文件）

用的 repak 是 trumank/repak 0.2.3，只做打包解包，不加壳、不注入。
"""
import os
import shutil

from . import paths, winproc

REPAK_NAME = 'repak.exe'
ASSETS_DIR = 'assets'
PAK_VERSION = 'V8B'          # 本作 pak 的版本
MOUNT = '../../../'

_repak_cache = {}


class PakError(Exception):
    """打包 / 解包 / 安装失败"""


# ---------------------------------------------------------------- repak

def repak_path():
    """找 repak.exe：可写 data/ > exe 同级 > 内嵌 > 源码目录"""
    return (paths.find_data(REPAK_NAME, writable=True)
            or paths.find_data(REPAK_NAME))


def repak_ok(force=False):
    """repak 是否可用 -> (ok, 说明)

    结果缓存：探测要起一个进程，没必要反复做（旧版每切一次页就探一次，
    既是卡顿来源，也是「黑框一闪」的来源）。
    """
    if not force and 'ok' in _repak_cache:
        return _repak_cache['ok'], _repak_cache['msg']

    exe = repak_path()
    if not exe:
        result, msg = False, '找不到 repak.exe'
    else:
        try:
            r = winproc.run([exe, '--version'], timeout=winproc.TIMEOUT_PROBE)
            out = winproc.text_of(r).strip()
            result = (r.returncode == 0)
            msg = out or ('repak 可用' if result else 'repak 返回码 %d' % r.returncode)
        except (OSError, winproc.subprocess.SubprocessError) as e:
            result, msg = False, 'repak 无法运行：%s' % e

    _repak_cache['ok'], _repak_cache['msg'] = result, msg
    return result, msg


def _require_repak():
    exe = repak_path()
    if not exe:
        raise PakError('找不到 repak.exe（应该在 data/ 或 exe 同级）')
    return exe


# ---------------------------------------------------------------- 工作区

def workspace():
    """可写的资产工作目录"""
    return os.path.join(paths.ensure_data_dir(), 'workspace')


def source_assets():
    """原始解包资产（只读来源），找不到返回 None"""
    marker = os.path.join('EotU', 'Content', 'Assets', 'Data', 'CreatureStats.uexp')
    for cand in (os.path.join(paths.DATA_DIR, ASSETS_DIR),
                 os.path.join(paths.bundle_dir(), ASSETS_DIR),
                 os.path.join(paths.MOD_DIR, 'extracted')):
        if os.path.isdir(cand) and os.path.isfile(os.path.join(cand, marker)):
            return cand
    return None


def workspace_ready():
    marker = os.path.join(workspace(), 'EotU', 'Content', 'Assets',
                          'Data', 'CreatureStats.uexp')
    return os.path.isfile(marker)


def reset_workspace():
    """从原始资产重建工作区（等于丢弃所有未打包的改动）"""
    src = source_assets()
    if not src:
        raise PakError('找不到解包好的原始资产（assets / extracted 目录）')
    dst = workspace()
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    return dst


def ensure_workspace():
    """工作区不存在就建一份；已存在则原样返回"""
    if not workspace_ready():
        return reset_workspace()
    return workspace()


def asset(rel):
    """工作区里的某个资产路径（如 EotU/Content/Assets/Data/CreatureStats.uexp）"""
    return os.path.join(workspace(), *rel.split('/'))


def uasset_pair(rel_base):
    """-> (uasset 路径, uexp 路径)"""
    return asset(rel_base + '.uasset'), asset(rel_base + '.uexp')


# ---------------------------------------------------------------- repak 子命令

def pack(out_pak, src_dir=None, mount=MOUNT):
    """把工作区打成 .pak

    注意 repak 0.2.3 的签名是 `pack [OPTIONS] <INPUT> [OUTPUT]`，
    输出是**位置参数**，写成 `-o out.pak` 会报 unexpected argument。
    """
    exe = _require_repak()
    src = src_dir or workspace()
    if os.path.isfile(out_pak):
        os.remove(out_pak)
    if os.path.dirname(out_pak):
        os.makedirs(os.path.dirname(out_pak), exist_ok=True)

    r = winproc.run([exe, 'pack', src, out_pak, '--version', PAK_VERSION,
                     '-m', mount], timeout=winproc.TIMEOUT_PACK)
    if r.returncode != 0:
        raise PakError('repak 打包失败（退出码 %d）：%s'
                       % (r.returncode, winproc.text_of(r)[:400]))
    return out_pak


def list_files(pak):
    """列出 pak 里的条目"""
    exe = _require_repak()
    r = winproc.run([exe, 'list', pak], timeout=winproc.TIMEOUT_PROBE)
    return [ln for ln in winproc.text_of(r).splitlines() if ln.strip()]


# ---------------------------------------------------------------- 游戏目录

def game_dir():
    return paths.load_config().get('game_dir') or paths.DEFAULT_GAME_DIR


def game_paks_dir():
    return os.path.join(game_dir(), 'EotU', 'Content', 'Paks')


def game_paks_exists():
    return os.path.isdir(game_paks_dir())


def installed_paks():
    """游戏 Paks 目录里现有的 pak 文件名（只读目录，不起进程）"""
    d = game_paks_dir()
    if not os.path.isdir(d):
        return []
    try:
        return sorted(f for f in os.listdir(d) if f.lower().endswith('.pak'))
    except OSError:
        return []


def install(pak_path):
    """把 pak 复制进游戏目录（只新增，不覆盖也不删除任何原有文件）"""
    dst_dir = game_paks_dir()
    if not os.path.isdir(dst_dir):
        raise PakError('游戏 Paks 目录不存在：%s\n请先在「设置」里确认游戏安装路径。'
                       % dst_dir)
    dst = os.path.join(dst_dir, os.path.basename(pak_path))
    shutil.copy2(pak_path, dst)
    return dst


def uninstall(pak_name):
    """卸载 = 删掉我们装进去的那一个 pak 文件"""
    p = os.path.join(game_paks_dir(), pak_name)
    if os.path.isfile(p):
        os.remove(p)
        return True
    return False
