# -*- coding: utf-8 -*-
"""调用外部命令的**唯一出口** —— 保证永远不弹出控制台窗口

## 为什么需要这个模块

本程序是 GUI（开发态用 pythonw 启动，打包态是 --windowed），它自己没有控制台。
但每当我们调用一个命令行程序（repak.exe / tasklist.exe），Windows 默认行为是
**给子进程新建一个控制台窗口** —— 用户看到的就是「黑框一闪而过」。
调用得越频繁越像中毒（旧版每 5 秒调一次 tasklist，每次切页还调 repak）。

解决办法是 CreateProcess 时带上 `CREATE_NO_WINDOW`（0x08000000），
再叠加 `STARTF_USESHOWWINDOW + SW_HIDE` 兜底。

## 铁律

**其它任何模块都不许直接 `import subprocess`。** 一律走 `winproc.run()`。
这样以后新增功能不可能再漏掉这个标志（漏了就会复现「黑框闪烁」）。
"""
import subprocess
import sys

IS_WINDOWS = sys.platform.startswith('win')

# CreateProcess 的 dwCreationFlags：不为子进程分配控制台
CREATE_NO_WINDOW = 0x08000000

# 常用超时（秒）
TIMEOUT_PROBE = 20      # 探测类命令（--version / tasklist）
TIMEOUT_PACK = 900      # 打包 / 解包大 pak


def _startupinfo():
    """兜底方案：万一 creationflags 被忽略，也让窗口隐藏且不抢焦点"""
    if not IS_WINDOWS:
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si


def run(cmd, timeout=TIMEOUT_PROBE, **kw):
    """运行外部命令，返回 subprocess.CompletedProcess。

    - 永不弹窗（Windows 下强制隐藏）
    - 默认 capture_output=True：不继承父进程句柄，也不会把输出打到不存在的控制台
    - 默认 stdin=DEVNULL：避免子进程等输入把界面卡死
    """
    kw.setdefault('capture_output', True)
    kw.setdefault('stdin', subprocess.DEVNULL)
    if IS_WINDOWS:
        kw.setdefault('creationflags', CREATE_NO_WINDOW)
        si = _startupinfo()
        if si is not None:
            kw.setdefault('startupinfo', si)
    return subprocess.run(cmd, timeout=timeout, **kw)


def text_of(result):
    """把子进程输出解成字符串。

    不能用 text=True：repak 的输出可能是任意字节，
    中文 Windows 上按 GBK 解码会抛 UnicodeDecodeError。
    """
    if result is None:
        return ''
    raw = (result.stdout or b'') + (result.stderr or b'')
    if isinstance(raw, str):            # 万一调用方自己开了 text=True
        return raw
    return raw.decode('utf-8', 'replace')
