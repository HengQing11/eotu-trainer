# -*- coding: utf-8 -*-
"""地下蚁国 · 修改器 —— 主窗口

## 布局
    顶栏（标题 + 游戏状态）
    左侧功能导航 ｜ 右侧内容区
    状态栏

## 启动时**故意什么都不做**
这一版把「启动 / 切页」路径上的外部进程调用全部拿掉了：
  - 不探测 repak（要起进程，且没窗口标志时会闪黑框）
  - 不轮询 tasklist（旧版每 5 秒一次，是卡顿和闪烁的主因）
  - 页面懒加载：第一次点导航才建，之后 refresh() 也不会重复读盘
所以点导航切页是纯 UI 操作，不存在等待。

## 加新功能
在 PAGES 里追加一个页面类即可（类上写 title / key，实现 refresh()）。
导航条会自动多一项，不用改这里其它代码。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk                                             # noqa: E402

from gui import widgets as W                                     # noqa: E402
from gui.core import actions, gameproc, pakbuild, paths, saves          # noqa: E402
from gui.pages.cheats import CheatsPage                       # noqa: E402
from gui.theme import C, F, GAP, PAD, TOP_H                             # noqa: E402

VERSION = '2.1.0'
NAV_W = 168
STATUS_H = 30

# 功能注册表：以后加功能只往这里加一行
# 「加点详情」（存档加点编辑）已按用户要求移除，代码还在
# gui/pages/adaptations.py —— 想加回来在这里补一行 import + 一个条目即可。
PAGES = [CheatsPage]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = paths.load_config()
        # 当前操作的存档名。存档选择在「清除加点」卡里（唯一用存档的功能）
        # 蚁皇浆余额在 <名字>LevelData.sav 里
        self.save_name = self.cfg.get('save_file') or 'Colony1.sav'
        _items = saves.list_saves()
        if _items and not any(s.file == self.save_name for s in _items):
            self.save_name = _items[0].file          # 配置里记的档没了 -> 顺位到第一个
            self.cfg['save_file'] = self.save_name
            paths.save_config(self.cfg)
        self.page_objs = {}          # key -> 页面实例（懒加载）
        self.nav_btns = {}           # key -> 导航按钮
        self.current = None

        self.title('地下蚁国 · 修改器')
        self.configure(fg_color=C['window'])
        self.minsize(1060, 700)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_topbar()
        self._build_nav()
        self._build_body()
        self._build_status()

        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self._center(1220, 800)

        # 先把窗口画出来，再干别的 —— 任何 I/O 都别挡在首屏前面
        self.after(30, lambda: self.select(PAGES[0].key))
        self.after(400, self._refresh_game_state)

    # -------------------------------------------------------------- 布局
    def _center(self, w, h):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry('%dx%d+%d+%d' % (w, h, max((sw - w) // 2, 0),
                                       max((sh - h) // 3, 0)))

    def _build_topbar(self):
        top = ctk.CTkFrame(self, fg_color=C['surface'], corner_radius=0, height=TOP_H)
        top.grid(row=0, column=0, columnspan=2, sticky='ew')
        top.grid_propagate(False)
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text='地下蚁国 · 修改器', font=F.get('h1'),
                     text_color=C['text']).grid(row=0, column=0, sticky='w',
                                                padx=(PAD, 0), pady=11)

        right = ctk.CTkFrame(top, fg_color='transparent')
        right.grid(row=0, column=2, sticky='e', padx=(0, PAD))
        self.dot = ctk.CTkLabel(right, text='●', font=F.get('small'), text_color=C['text3'])
        self.dot.pack(side='left', padx=(0, 4))
        self.game_lbl = ctk.CTkLabel(right, text='游戏状态检测中…', font=F.get('small'),
                                     text_color=C['text2'])
        self.game_lbl.pack(side='left')

        W.Divider(self).grid(row=0, column=0, columnspan=2, sticky='sew',
                             pady=(TOP_H - 1, 0))

    def _build_nav(self):
        nav = ctk.CTkFrame(self, fg_color=C['surface'], corner_radius=0, width=NAV_W)
        nav.grid(row=1, column=0, sticky='nsw')
        nav.grid_propagate(False)
        nav.grid_rowconfigure(len(PAGES) + 1, weight=1)

        ctk.CTkLabel(nav, text='功能', font=F.get('tiny'), text_color=C['text3'],
                     anchor='w').grid(row=0, column=0, sticky='ew', padx=(PAD, 0),
                                      pady=(14, 6))

        for i, cls in enumerate(PAGES, start=1):
            btn = ctk.CTkButton(nav, text=cls.title, anchor='w',
                                command=lambda k=cls.key: self.select(k),
                                fg_color='transparent', hover_color=C['surface3'],
                                text_color=C['text2'], font=F.get('body'),
                                corner_radius=6, height=34, width=NAV_W - 20)
            btn.grid(row=i, column=0, sticky='ew', padx=10, pady=2)
            self.nav_btns[cls.key] = btn

        ctk.CTkLabel(nav, text='改动只写进存档，\n游戏文件一个都不碰。\n每次写入前自动备份。',
                     font=F.get('tiny'), text_color=C['text3'], anchor='w',
                     justify='left', wraplength=NAV_W - 30
                     ).grid(row=len(PAGES) + 2, column=0, sticky='sw', padx=(PAD, 0),
                            pady=(0, 14))

    def _build_body(self):
        self.body = ctk.CTkFrame(self, fg_color='transparent')
        self.body.grid(row=1, column=1, sticky='nsew', padx=PAD, pady=(GAP, 0))
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

    def _build_status(self):
        bar = ctk.CTkFrame(self, fg_color=C['surface'], corner_radius=0, height=STATUS_H)
        bar.grid(row=2, column=0, columnspan=2, sticky='ew')
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        W.Divider(self).grid(row=2, column=0, columnspan=2, sticky='new')

        self.status = ctk.CTkLabel(bar, text='就绪。改动只写进存档，回游戏读一次档生效。',
                                   font=F.get('small'), text_color=C['text2'], anchor='w')
        self.status.grid(row=0, column=0, sticky='w', padx=(PAD, 0))
        ctk.CTkLabel(bar, text='v%s' % VERSION, font=F.get('small'),
                     text_color=C['text3']).grid(row=0, column=1, sticky='e',
                                                 padx=(0, PAD))

    # -------------------------------------------------------------- 导航
    def select(self, key):
        """切换功能页。第一次进来才建页面 + refresh；之后只是把它抬到前面。"""
        if key not in self.nav_btns:
            return
        if key == self.current:
            return
        cls = next(c for c in PAGES if c.key == key)
        page = self.page_objs.get(key)
        if page is None:
            page = cls(self.body, self)
            page.grid(row=0, column=0, sticky='nsew')
            self.page_objs[key] = page
            self._safe_refresh(page)        # 只在首次显示时加载
        page.tkraise()

        for k, btn in self.nav_btns.items():
            on = (k == key)
            btn.configure(fg_color=C['accent_soft'] if on else 'transparent',
                          text_color=C['accent_text'] if on else C['text2'])
        self.current = key

    def _switch_save(self, label):
        """换一个存档。下拉给的是**游戏里的名字**，这里换回文件名"""
        it = next((s for s in self.save_items if s.label == label), None)
        name = it.file if it else self.save_name
        self.save_name = name
        self.cfg['save_file'] = name
        paths.save_config(self.cfg)
        self.log('已切到存档「%s」（%s）' % (label, name))
        page = self.page_objs.get(self.current)
        if page is not None:
            self._safe_refresh(page)

    def _safe_refresh(self, page):
        try:
            page.refresh()
        except Exception as e:                                          # noqa: BLE001
            self.log('页面初始化失败：%s' % e, 'err')

    # -------------------------------------------------------------- 状态
    def log(self, msg, kind='info'):
        self.status.configure(text=msg,
                              text_color={'ok': C['ok'], 'err': C['danger'],
                                          'warn': C['warn']}.get(kind, C['text2']))

    def _refresh_game_state(self):
        state, text = gameproc.status()
        self.dot.configure(text_color={'running': C['danger'], 'idle': C['ok']}
                           .get(state, C['text3']))
        self.game_lbl.configure(text=text)

    # -------------------------------------------------------------- 关闭
    def _on_close(self):
        paths.save_config(self.cfg)
        self.destroy()


def _paks_state():
    if not pakbuild.game_paks_exists():
        return '目录不存在 —— 上方的游戏安装目录可能不对'
    files = pakbuild.installed_paks()
    mine = [f for f in files if f.lower().startswith('eotucustom')]
    return ('存在，现有 %d 个 pak%s'
            % (len(files), ('（本工具的：%s）' % '、'.join(mine)) if mine else ''))


# ==================================================================== 自检

def selftest():
    """不开界面自检：蚁国修改器.exe --selftest

    同时打印并写 exe 同级 selftest.txt（--windowed 下没有控制台，得落盘才看得到）。
    重点检查「启动路径上不该有外部进程」这条约束有没有被破坏。
    """
    import time
    from gui.core import creature_stats as CS                            # noqa: E402
    from gui.core import fieldlib, gvas, jelly                           # noqa: E402

    lines = []

    def add(k, v):
        lines.append('%-14s %s' % (k, v))

    add('版本', VERSION)
    _sv = saves.list_saves()
    add('存档 %d 个' % len(_sv), '、'.join(s.label for s in _sv) or '（没找到）')
    add('打包运行', '是' if paths.FROZEN else '否')
    add('程序目录', paths.APP_DIR)
    add('内嵌目录', paths.bundle_dir())
    add('输出目录', os.path.join(paths.APP_DIR, 'build'))

    t0 = time.time()
    add('游戏目录', pakbuild.game_dir())
    add('Paks 目录', _paks_state())

    state, text = gameproc.status()
    add('游戏进程', '%s（%s）' % (text, state))

    # ---- 蚁皇浆加点链路：当前唯一功能，必须能一路读到真实存档 ----
    cfg = paths.load_config()
    add('加点字段库', '%d 项' % len(fieldlib.all_fields()))

    save_name = cfg.get('save_file') or 'Colony1.sav'
    stem, ext = os.path.splitext(save_name)
    ld_name = '%sLevelData%s' % (stem, ext or '.sav')
    try:
        sf = gvas.SaveFile(actions.save_path(save_name))
        ads = jelly.addons(sf)
        add('加点清单', '%d 项 / 共 %d 点' % (len(ads), sum(a[1] for a in ads)))
        unk = jelly.unknown_addons(sf)
        add('未登记字段', '无' if not unk else '、'.join(unk))
    except Exception as e:                                            # noqa: BLE001
        add('加点清单', '失败：%s' % e)
    try:
        v = jelly.main_jelly(actions.save_path(ld_name))
        add('蚁皇浆余额', '（读不到 %s）' % ld_name if v is None else format(v, ','))
    except Exception as e:                                            # noqa: BLE001
        add('蚁皇浆余额', '失败：%s' % e)

    # 约束检查：外部命令只能从 winproc 里调，否则会重新出现「黑框闪烁」
    add('子进程出口', _check_subprocess_hygiene())

    text = '\n'.join(lines) + '\n'
    out = os.path.join(paths.APP_DIR, 'selftest.txt')
    try:
        with open(out, 'w', encoding='utf-8') as f:
            f.write(text)
    except OSError:
        out = '(写不进去)'
    try:
        print(text)
        print('已写入：%s' % out)
    except Exception:                                                 # noqa: BLE001
        pass
    return 0


def _check_subprocess_hygiene():
    """开发态扫一遍源码，确认外部命令只能从 winproc 出

    用 ast 只看**真正的 import 语句** —— 注释和文档字符串里提到 "import subprocess"
    不算（第一版就是拿字符串搜的，结果把自己这段注释给判越界了）。
    """
    if paths.FROZEN:
        return '打包态跳过（源码未随包分发）'
    import ast
    bad = set()
    root = os.path.join(paths.MOD_DIR, 'gui')
    for dirpath, _dirs, files in os.walk(root):
        if '__pycache__' in dirpath:
            continue
        for fn in files:
            if not fn.endswith('.py') or fn == 'winproc.py':
                continue
            fp = os.path.join(dirpath, fn)
            try:
                with open(fp, encoding='utf-8') as f:
                    tree = ast.parse(f.read())
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    hit = any(a.name.split('.')[0] == 'subprocess'
                              for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    hit = (node.module or '').split('.')[0] == 'subprocess'
                else:
                    continue
                if hit:
                    bad.add(os.path.relpath(fp, paths.MOD_DIR))
                    break
    return ('OK（只有 winproc.py 直接调 subprocess）' if not bad
            else '越界：%s' % '、'.join(sorted(bad)))


def main():
    if '--selftest' in sys.argv[1:]:
        return selftest()
    ctk.set_appearance_mode('dark')
    ctk.set_default_color_theme('blue')
    App().mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
