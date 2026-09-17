# -*- coding: utf-8 -*-
"""改动前自动备份 + 备份还原

规则：
  * 每次写存档前先复制一份到 backup/saves/
  * 备份文件名带时间戳和原文件名，来源可追溯
  * 同类文件只保留最近 N 份，自动清理最旧的
"""
import os
import re
import shutil
from datetime import datetime

from . import paths

STAMP = '%Y%m%d-%H%M%S'


def backup_dir():
    d = paths.BACKUP_DIR
    os.makedirs(d, exist_ok=True)
    return d


def backup_file(path, note=''):
    """备份一个文件 -> 备份文件的完整路径（失败返回 None）"""
    if not os.path.isfile(path):
        return None
    d = backup_dir()
    base = os.path.basename(path)
    stamp = datetime.now().strftime(STAMP)
    name = '%s.bak-%s' % (base, stamp)
    if note:
        safe = re.sub(r'[^0-9A-Za-z_.-]', '', note)[:20]
        if safe:
            name = '%s.%s.bak-%s' % (base, safe, stamp)
    dst = os.path.join(d, name)
    i = 1
    while os.path.exists(dst):
        dst = os.path.join(d, '%s.%d' % (name, i))
        i += 1
    try:
        shutil.copy2(path, dst)
    except OSError:
        return None
    prune(os.path.basename(path))
    return dst


def prune(base_name, keep=None):
    """只保留某个存档最近 keep 份备份"""
    if keep is None:
        keep = int(paths.load_config().get('max_backups', 5))
    d = backup_dir()
    prefix = base_name + '.'
    try:
        entries = [f for f in os.listdir(d) if f.startswith(prefix) and '.bak-' in f]
    except OSError:
        return
    entries.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
    for f in entries[keep:]:
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass


def _split(name):
    """backup 文件名 -> (原文件名, 时间)"""
    m = re.match(r'^(.*?)\.bak-(\d{8}-\d{6})(?:\.\d+)?$', name)
    if not m:
        return name, None
    return m.group(1), m.group(2)


def list_backups():
    """-> [{name, origin, path, size, mtime, time}]，按时间倒序"""
    d = backup_dir()
    out = []
    try:
        files = os.listdir(d)
    except OSError:
        return out
    for f in files:
        p = os.path.join(d, f)
        if not os.path.isfile(p):
            continue
        origin, ts = _split(f)
        try:
            mt = os.path.getmtime(p)
            size = os.path.getsize(p)
        except OSError:
            continue
        out.append({
            'name': f,
            'origin': origin,
            'path': p,
            'size': size,
            'mtime': mt,
            'time': ts or datetime.fromtimestamp(mt).strftime(STAMP),
        })
    out.sort(key=lambda x: x['mtime'], reverse=True)
    return out


def restore(bak_path, target_dir=None):
    """把备份还原回存档目录 -> 还原后的完整路径"""
    origin, _ = _split(os.path.basename(bak_path))
    dst_dir = target_dir or paths.saves_dir()
    dst = os.path.join(dst_dir, origin)
    if os.path.exists(dst):
        backup_file(dst, 'beforeRevert')
    shutil.copy2(bak_path, dst)
    return dst


def delete(bak_path):
    try:
        os.remove(bak_path)
        return True
    except OSError:
        return False


def total_size():
    return sum(b['size'] for b in list_backups())
