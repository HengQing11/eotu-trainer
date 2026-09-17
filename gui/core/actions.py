# -*- coding: utf-8 -*-
"""安全落盘 —— 所有写存档的操作都走这里

流程固定，不允许跳步：
  1) 游戏在跑 -> 直接拒绝（存档只在存盘那一刻落盘，开着游戏改会被覆盖）
  2) 落盘前自动备份
  3) 写盘
  4) 重新读回来校验，确认改动确实生效
"""
import os

from . import backup as BK
from . import gvas
from . import paths
from . import gameproc
from . import saves as SV


class Result(object):
    def __init__(self, ok, msg, **kw):
        self.ok = ok
        self.msg = msg
        self.__dict__.update(kw)

    def __repr__(self):
        return '<Result %s %s>' % ('OK' if self.ok else 'FAIL', self.msg)


def commit(sf, verify=None, note='', force=False):
    """把 SaveFile 的改动落盘

    sf      : gvas.SaveFile
    verify  : callable(path) -> (bool, str)，落盘后校验；返回 False 就报失败
    force   : 跳过游戏运行检测（沙箱测试用，UI 里不给这个选项）
    """
    path = sf.path
    if not sf.dirty:
        return Result(False, '没有任何改动需要保存。')

    running = gameproc.game_running()
    if running is True and not force:
        return Result(False,
                      '游戏正在运行，已停止写入。\n'
                      '存档只在「游戏存盘那一刻」写盘，开着游戏改会被它自己的数据覆盖。\n'
                      '请先完全退出游戏，回到桌面后重试。',
                      code='running')
    if running is None:
        return Result(False, '没能确认游戏是否在运行，为安全起见已停止。', code='unknown')

    bak = BK.backup_file(path, note)
    if not bak:
        return Result(False, '备份失败，已停止写入（不敢在没有备份的情况下改存档）。',
                      code='backup')

    dst, nbytes, same = sf.save()
    if not same:
        return Result(False, '写入后文件长度变了，这是异常情况！请还原备份：\n%s' % bak,
                      code='size', backup=bak)

    msg = '已写入 %d 处改动，文件长度不变（%d 字节）。' % (nbytes, os.path.getsize(path))
    detail = ''
    if verify:
        try:
            ok, detail = verify(path)
        except Exception as e:                       # noqa: BLE001
            ok, detail = False, '校验过程出错：%s' % e
        if not ok:
            return Result(False, '写入后的校验没通过：%s\n请还原备份：%s' % (detail, bak),
                          code='verify', backup=bak)

    return Result(True, msg + (('\n' + detail) if detail else ''),
                  backup=bak, changed=nbytes, path=path)


def restore(bak_path):
    """把备份还原回存档目录"""
    try:
        dst = BK.restore(bak_path)
    except OSError as e:
        return Result(False, '还原失败：%s' % e)
    return Result(True, '已还原：%s -> %s' % (os.path.basename(bak_path), dst), path=dst)


def saves_dir_ok():
    d = paths.saves_dir()
    return os.path.isdir(d), d


def list_saves():
    """存档目录里可操作的存档 -> [文件名]

    过滤规则统一放在 core/saves.py，这里只取文件名，别再写第二套。
    """
    return [s.file for s in SV.list_saves()]


def save_path(name):
    return os.path.join(paths.saves_dir(), name)
