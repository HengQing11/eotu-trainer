# -*- coding: utf-8 -*-
"""打包成单文件 exe（蚁皇浆修改器）

必须在**系统 Python**（含 tkinter 的那个）里跑：
    C:/Users/beimo/AppData/Local/Programs/Python/Python313/python.exe scripts/build_exe.py

当前唯一功能 = 「蚁皇浆加点」（改存档），因此内嵌清单精简为：
    升级项字段库.csv   加点字段的唯一权威源（fieldlib 读取，运行时自动
                       释放一份到 exe 同级 data/ 供用户扩充）
不再内嵌 repak.exe / extracted 资产 —— pak 相关功能已移出导航。

注意：manifest 里不加管理员权限请求，也不改任何系统设置。
"""
import os
import sys
import subprocess

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = '蚁国修改器'
SEP = ';'                                    # Windows 的 --add-data 分隔符


def need(path, what):
    if not os.path.exists(path):
        print('缺少%s：%s' % (what, path))
        return False
    return True


def main():
    checks = [
        (os.path.join(MOD, '升级项字段库.csv'), '加点字段库'),
        (os.path.join(MOD, 'gui', 'main.py'), '主程序'),
    ]
    for p, w in checks:
        if not need(p, w):
            return 1

    # 直接打包覆盖旧 exe（PyInstaller --noconfirm 会覆盖同名输出），
    # 不做预删除 —— 沙箱对删除有额度限制，能不删就不删。

    # 源路径必须绝对路径：带了 --specpath 之后，相对路径会按 spec 目录去解析
    datas = [(os.path.join(MOD, '升级项字段库.csv'), '.')]

    args = [sys.executable, '-m', 'PyInstaller',
            '--noconfirm', '--clean',
            '--onefile', '--windowed',
            '--name', NAME,
            '--distpath', os.path.join(MOD, 'dist'),
            '--workpath', os.path.join(MOD, 'build_pyi'),
            '--specpath', os.path.join(MOD, 'build_pyi'),
            '--collect-all', 'customtkinter',
            '--exclude-module', 'numpy',
            '--exclude-module', 'matplotlib',
            '--exclude-module', 'PIL.ImageQt',
            '--exclude-module', 'tests',
            ]
    for src, dst in datas:
        args += ['--add-data', '%s%s%s' % (src, SEP, dst)]
    args.append(os.path.join(MOD, 'gui', 'main.py'))

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
