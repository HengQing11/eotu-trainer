# -*- coding: utf-8 -*-
"""游戏进程检测

用途：装 pak 前后提示用户「重启游戏才生效」；写存档类操作前确认游戏没在跑
（存档只在游戏存盘那一刻写盘，游戏开着改会被它自己的数据覆盖）。

注意：**不做定时轮询**。旧版每 5 秒调一次 tasklist，既是性能浪费，
也是「黑框一闪而过」的来源之一。这里只在需要时查一次，结果缓存 10 秒。
"""
import os
import time

from . import winproc

EXE = 'EotU-Win64-Shipping.exe'
_CACHE_TTL = 10.0              # 秒
_cache = {'at': 0.0, 'value': None}


def _tasklist_path():
    root = os.environ.get('SystemRoot') or r'C:\Windows'
    p = os.path.join(root, 'System32', 'tasklist.exe')
    return p if os.path.isfile(p) else 'tasklist'


def game_running(force=False):
    """-> True 在跑 / False 没跑 / None 判断不了

    用**字节**匹配：中文 Windows 的 tasklist 输出是 GBK，
    一旦用 text=True 就会 UnicodeDecodeError。
    """
    now = time.time()
    if not force and _cache['value'] is not None and now - _cache['at'] < _CACHE_TTL:
        return _cache['value']

    value = None
    try:
        r = winproc.run([_tasklist_path(), '/FI', 'IMAGENAME eq %s' % EXE],
                        timeout=winproc.TIMEOUT_PROBE)
    except (OSError, winproc.subprocess.SubprocessError):
        value = None
    else:
        out = r.stdout or b''
        needle = EXE.encode()
        if needle in out:
            value = True
        elif b'No tasks' in out or b'INFO:' in out or b'\xc3\xbb\xd3\xd0' in out:
            value = False                      # "没有运行的任务…"
        else:
            value = False if b'.exe' not in out else True

    _cache['at'], _cache['value'] = now, value
    return value


def status():
    """-> (state, 文案)  state: running / idle / unknown"""
    r = game_running()
    if r is True:
        return 'running', '游戏正在运行'
    if r is False:
        return 'idle', '游戏未运行'
    return 'unknown', '状态未知'


def invalidate():
    _cache['value'] = None
