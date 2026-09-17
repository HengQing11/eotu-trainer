# -*- coding: utf-8 -*-
"""路径解析 —— 开发态和打包成 exe 后都能正确找到资源

两种运行状态：
  开发态：直接跑 gui/main.py，资源就在 mod/ 下面
  打包态：跑 蚁国修改器.exe，资源在 exe 同级 data/ 或 PyInstaller 解包目录

可写数据（字段库）优先放在 exe 同级的 data/，用户能自己扩充；
只读资源（数值表、repak）找不到时回落到内嵌副本。
"""
import json
import os
import sys

FROZEN = getattr(sys, 'frozen', False)

HERE = os.path.dirname(os.path.abspath(__file__))       # gui/core
GUI_DIR = os.path.dirname(HERE)                          # gui
MOD_DIR = os.path.dirname(GUI_DIR)                       # mod


def app_dir():
    """程序所在目录：打包后 = exe 同级；开发态 = mod/"""
    if FROZEN:
        return os.path.dirname(os.path.abspath(sys.executable))
    return MOD_DIR


def bundle_dir():
    """PyInstaller 运行时解包目录（打包态才有意义）"""
    return getattr(sys, '_MEIPASS', app_dir())


APP_DIR = app_dir()
DATA_DIR = os.path.join(APP_DIR, 'data')
BACKUP_DIR = os.path.join(APP_DIR, 'backup', 'saves')
CONFIG_PATH = os.path.join(APP_DIR, 'config.json')

# 游戏存档目录（LOCALAPPDATA 可被环境变量覆盖，方便沙箱测试）
def saves_dir():
    override = os.environ.get('EOTU_SAVES_DIR')
    if override:
        return override
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'EotU', 'Saved', 'SaveGames')


# 默认游戏安装目录（可在设置里改，写进 config.json）
DEFAULT_GAME_DIR = r'D:\app\steam\steamapps\common\Empires of the Undergrowth'

DEFAULT_CONFIG = {
    'game_dir': DEFAULT_GAME_DIR,
    'save_file': 'Colony1.sav',
    'max_backups': 5,
    'jelly_cap': 2_000_000_000,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            cfg.update(json.load(f) or {})
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def find_data(name, writable=False):
    """按优先级找一个数据文件

    writable=True 时只认可写目录（需要能改的文件，比如字段库）
    """
    cands = []
    if writable:
        cands.append(os.path.join(DATA_DIR, name))
        cands.append(os.path.join(APP_DIR, name))
        cands.append(os.path.join(MOD_DIR, name))
    else:
        cands.append(os.path.join(DATA_DIR, name))
        cands.append(os.path.join(APP_DIR, name))
        cands.append(os.path.join(bundle_dir(), name))
        cands.append(os.path.join(MOD_DIR, name))
    for p in cands:
        if os.path.isfile(p):
            return p
    return None


def ensure_data_dir():
    """确保可写数据目录存在；返回该目录"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        pass
    return DATA_DIR
