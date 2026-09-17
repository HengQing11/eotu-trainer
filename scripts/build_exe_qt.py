# -*- coding: utf-8 -*-
"""打包 PySide6/QML 版修改器（v3）成单文件 exe

必须在系统 Python（装了 PySide6 的那个）里跑：
    C:/Users/beimo/AppData/Local/Programs/Python/Python313/python.exe scripts/build_exe_qt.py

注意：QML 从 Python 字符串加载，PyInstaller 静态分析看不到 QML 的 import，
所以 QtQuick/QtQuickControls2/QmlModels 必须显式 hiddenimports，
让 PySide6 钩子把对应的 qml 资源目录收进来。
"""
import os
import subprocess
import sys

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = '蚁国修改器'


def main():
    # 工作目录带时间戳：每次全新，绝不清空旧目录（沙箱会拦批量删除）
    import time
    work = os.path.join(MOD, 'build_pyi_qt', time.strftime('%Y%m%d_%H%M%S'))
    os.makedirs(work, exist_ok=True)
    args = [sys.executable, '-m', 'PyInstaller',
            '--noconfirm',
            '--onefile', '--windowed',
            '--name', NAME,
            '--distpath', os.path.join(MOD, 'dist'),
            '--workpath', work,
            '--specpath', work,
            '--hidden-import', 'PySide6.QtQuick',
            '--hidden-import', 'PySide6.QtQuickControls2',
            '--hidden-import', 'PySide6.QtNetwork',
            '--exclude-module', 'numpy',
            '--exclude-module', 'matplotlib',
            '--exclude-module', 'PySide6.QtWebEngineCore',
            '--exclude-module', 'PySide6.QtWebEngineWidgets',
            '--exclude-module', 'PySide6.QtWebChannel',
            '--exclude-module', 'PySide6.Qt3D',
            '--exclude-module', 'tests',
            os.path.join(MOD, 'ui_new', 'app.py')]

    print('打包命令：')
    print('  ' + ' '.join('"%s"' % a if ' ' in a else a for a in args))
    print()
    r = subprocess.run(args, cwd=MOD)
    if r.returncode != 0:
        print('\n打包失败，退出码 %d' % r.returncode)
        return r.returncode
    exe = os.path.join(MOD, 'dist', NAME + '.exe')
    if not os.path.isfile(exe):
        print('\n打包命令返回成功，但没找到 exe：%s' % exe)
        return 1
    print('\n完成：%s（%.1f MB）' % (exe, os.path.getsize(exe) / 1048576.0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
