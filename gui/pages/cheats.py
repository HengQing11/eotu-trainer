# -*- coding: utf-8 -*-
"""关卡作弊 + 蚁皇浆运行时 + 清除加点

1. 官方调试开关（无限资源 / 免费孵化 / 秒建 / 秒挖）：判定级生效
2. 蚁皇浆运行时补满：锚点定位（与浆值无关，新档也能用），写入 20 亿后回读校验
3. 清除加点：存档层操作，一键把当前档的全部加点清零（需完全退出游戏）
后台线程每 1 秒回读状态同步 UI + 重申已开的开关（防游戏清位）。
"""
import os
import threading
import time

import customtkinter as ctk

from .. import widgets as W
from ..core import actions, cheats, gameproc, gvas, jelly, saves
from ..theme import C, F, GAP


class CheatsPage(ctk.CTkFrame):
    title = '关卡作弊'
    key = 'cheats'

    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        self.proc = None
        self.base = None
        self.grid_addr = None
        self.jcolony = None
        self._syncing = False
        self._lock = threading.Lock()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        body = ctk.CTkFrame(self, fg_color='transparent')
        body.grid(row=0, column=0, sticky='nsew', padx=GAP, pady=GAP)
        body.grid_columnconfigure(0, weight=1)

        # ---------------------------------------------------------- 开关卡片
        card = W.Card(body)
        card.grid(row=0, column=0, sticky='ew')
        card.grid_columnconfigure(0, weight=1)

        self.rows = {}
        for i, (key, _off, cn, _en) in enumerate(cheats.FLAG_DEFS):
            row = W.ToggleRow(card, cn, note='', value=False,
                              command=(lambda v, k=key: self._on_toggle(k, v)))
            row.grid(row=i, column=0, sticky='ew', padx=16,
                     pady=(14 if i == 0 else 2, 2))

        # ---------------------------------------------------------- 蚁皇浆卡片
        jcard = W.Card(body)
        jcard.grid(row=1, column=0, sticky='ew', pady=(GAP, 0))
        jcard.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(jcard, text='蚁皇浆 · 运行时补满',
                     font=F.get('h3'), text_color=C['text']).grid(
            row=0, column=0, sticky='w', padx=16, pady=(14, 0))
        ctk.CTkLabel(jcard, text='需游戏开着 · 定位约 1 秒 · 写入即生效并随游戏存盘',
                     font=F.get('tiny'), text_color=C['text3']).grid(
            row=1, column=0, sticky='w', padx=16)

        self.j_val = ctk.CTkLabel(jcard, text='—', font=F.get('num'),
                                  text_color=C['text'])
        self.j_val.grid(row=2, column=0, sticky='w', padx=16, pady=(6, 0))

        btns = ctk.CTkFrame(jcard, fg_color='transparent')
        btns.grid(row=3, column=0, sticky='ew', padx=16, pady=(8, 12))
        self.j_btn = W.make_button(btns, '补满到 20 亿', self._refill, kind='primary')
        self.j_btn.pack(side='left')
        self.j_note = ctk.CTkLabel(btns, text='', font=F.get('small'),
                                   text_color=C['text2'])
        self.j_note.pack(side='left', padx=(GAP, 0))

        # ---------------------------------------------------------- 清除加点卡片
        ccard = W.Card(body)
        ccard.grid(row=2, column=0, sticky='ew', pady=(GAP, 0))
        ccard.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(ccard, text='清除加点',
                     font=F.get('h3'), text_color=C['text']).grid(
            row=0, column=0, sticky='w', padx=16, pady=(14, 0))
        ctk.CTkLabel(ccard, text='把所选存档的全部加点一键清零 · 需完全退出游戏 · '
                                 '清除后蚁皇浆不退还 · 每次写入前自动备份',
                     font=F.get('tiny'), text_color=C['text3']).grid(
            row=1, column=0, sticky='w', padx=16)

        # 存档选择就在这张卡里 —— 只有这个功能用存档
        # 下拉里**只显示游戏里的名字**（存档的 ColonyName 字段），文件名只在内部用
        crow = ctk.CTkFrame(ccard, fg_color='transparent')
        crow.grid(row=2, column=0, sticky='w', padx=16, pady=(10, 0))
        ctk.CTkLabel(crow, text='存档', font=F.get('small'),
                     text_color=C['text3']).pack(side='left', padx=(0, 8))
        self.save_items = saves.list_saves()
        _cur = next((s for s in self.save_items if s.file == self.app.save_name),
                    None)
        self.save_var = ctk.StringVar(
            value=_cur.label if _cur else self.app.save_name)
        W.make_menu(crow, self.save_var,
                    [s.label for s in self.save_items] or ['（没找到存档）'],
                    width=200, command=self._on_save_switch)

        cbtns = ctk.CTkFrame(ccard, fg_color='transparent')
        cbtns.grid(row=3, column=0, sticky='ew', padx=16, pady=(8, 12))
        self.c_btn = W.make_button(cbtns, '清除全部加点', self._clear_addons,
                                   kind='danger')
        self.c_btn.pack(side='left')
        self.c_note = ctk.CTkLabel(cbtns, text='', font=F.get('small'),
                                   text_color=C['text2'])
        self.c_note.pack(side='left', padx=(GAP, 0))

        # ---------------------------------------------------------- 后台刷新
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.bind('<Destroy>', self._on_destroy)

    # -------------------------------------------------- 与游戏内存的同步
    def _connect(self):
        if self.proc is not None:
            return True
        proc, base = cheats.connect()
        if proc is None:
            return False
        self.proc, self.base = proc, base
        self.grid_addr = cheats.find_grid(proc, base)
        if self.grid_addr is None:
            self._close_proc()
            return False
        return True

    def _on_destroy(self, _e):
        self._stop.set()
        self._close_proc()

    def _close_proc(self):
        try:
            if self.proc is not None:
                self.proc.close()
        except Exception:                                        # noqa: BLE001
            pass
        self.proc = None
        self.grid_addr = None
        self.jcolony = None

    def _loop(self):
        """后台：每 1 秒回读状态刷 UI + 重申已开的开关（防游戏清位）"""
        while not self._stop.is_set():
            time.sleep(1.0)
            if self._stop.is_set():
                return
            with self._lock:
                if not self._connect():
                    self._safe_ui(None, None)
                    continue
                try:
                    wants = {k: self.rows[k].var.get() for k in self.rows}
                    if any(wants.values()):
                        cheats.apply_flags(self.proc, self.grid_addr, wants)
                    st = cheats.read_status(self.proc, self.grid_addr)
                    # 蚁皇浆：归属失效就重新锚定
                    if self.jcolony is None:
                        self.jcolony = cheats.find_play_colony(self.proc, self.base)
                    jv = (cheats.read_jelly(self.proc, self.jcolony)
                          if self.jcolony is not None else None)
                    self._safe_ui(st, jv)
                except Exception:                                # noqa: BLE001
                    self._close_proc()
                    self._safe_ui(None, None)

    def _safe_ui(self, st, jv):
        """线程里不能直接碰控件 —— 转给主线程"""
        try:
            self.after(0, lambda: self._apply_ui(st, jv))
        except Exception:                                        # noqa: BLE001
            pass

    def _apply_ui(self, st, jv):
        self._syncing = True
        try:
            if st is None:
                for row in self.rows.values():
                    row.var.set(False)
            else:
                for key, row in self.rows.items():
                    row.var.set(bool(st['flags'].get(key)))
            if jv is not None:
                self.j_val.configure(text='{:,}'.format(int(jv)))
        finally:
            self._syncing = False

    def _on_toggle(self, key, value):
        if self._syncing:
            return
        with self._lock:
            if not self._connect():
                return
            wants = {k: self.rows[k].var.get() for k in self.rows}
            wants[key] = value
            try:
                cheats.apply_flags(self.proc, self.grid_addr, wants)
            except Exception:                                    # noqa: BLE001
                self._close_proc()

    def _refill(self):
        def work():
            with self._lock:
                try:
                    if not self._connect():
                        self.after(0, lambda: self.j_note.configure(
                            text='✗ 游戏没开或不在关卡里', text_color=C['danger']))
                        return
                    colony = cheats.find_play_colony(self.proc, self.base)
                    if colony is None:
                        self.after(0, lambda: self.j_note.configure(
                            text='✗ 没找到你的殖民地（不猜不乱写）',
                            text_color=C['danger']))
                        return
                    cur = cheats.read_jelly(self.proc, colony)
                    ok, after = cheats.refill_jelly(self.proc, colony, self.base)
                    self.jcolony = colony if ok else None
                    txt = ('✓ 定位成功 · %s → 20 亿 · 回读一致'
                           % '{:,}'.format(cur or 0)) if ok else \
                          ('✗ 写入后回读不符（%s）' % '{:,}'.format(after or 0))
                    col = C['ok'] if ok else C['danger']
                    self.after(0, lambda: self.j_note.configure(text=txt,
                                                                text_color=col))
                    if ok:
                        self.after(0, lambda: self.j_val.configure(
                            text='{:,}'.format(cheats.JELLY_CAP)))
                except Exception as e:                           # noqa: BLE001
                    msg = str(e)[:40]
                    self.after(0, lambda: self.j_note.configure(
                        text='✗ %s' % msg, text_color=C['danger']))
        threading.Thread(target=work, daemon=True).start()

    # -------------------------------------------------------------- 清除加点
    def _on_save_switch(self, label):
        """卡内下拉切换存档 -> 交给主框架统一处理（记配置、写状态栏）"""
        self.app._switch_save(label)
        self.c_note.configure(text='')

    def _clear_addons(self):
        """存档层：把当前档的全部加点一键清零（actions.commit 自带
        「游戏在跑就拒绝 + 自动备份 + 回读校验」，这里只做友好前置提示）"""
        if gameproc.game_running() is True:
            self.c_note.configure(text='✗ 游戏正在运行 —— 请先完全退出游戏再清除',
                                  text_color=C['danger'])
            return
        try:
            sf = gvas.SaveFile(actions.save_path(self.app.save_name))
            ads = jelly.addons(sf)
        except Exception as e:                                   # noqa: BLE001
            self.c_note.configure(text='✗ 读存档失败：%s' % str(e)[:50],
                                  text_color=C['danger'])
            return
        if not ads:
            self.c_note.configure(text='这个存档当前没有任何加点，无需清除',
                                  text_color=C['text2'])
            return
        n_items, total = len(ads), sum(a[1] for a in ads)

        if not W.confirm(self, '清除全部加点？',
                         '这个档有 %d 项加点（共 %d 点），将全部清零。'
                         % (n_items, total),
                         ok_text='全部清零', danger=True,
                         detail='加点的蚁皇浆不会退回。\n'
                                '写入前会自动备份，出问题可以还原。'):
            return

        def work():
            try:
                for f, _pts, _cost in ads:
                    sf.set_int(f.name, 0)

                def verify(vp):
                    left = jelly.addons(gvas.SaveFile(vp))
                    return (not left,
                            '全部 %d 项已归零（原共 %d 点）' % (n_items, total)
                            if not left else '剩余未清 %d 项' % len(left))

                r = actions.commit(sf, 'clearAddons', verify=verify)
                self.after(0, lambda: self.c_note.configure(
                    text=('✓ ' if r.ok else '✗ ') + r.msg.replace('\n', ' '),
                    text_color=C['ok'] if r.ok else C['danger']))
            except Exception as e:                               # noqa: BLE001
                msg = str(e)[:60]
                self.after(0, lambda: self.c_note.configure(
                    text='✗ %s' % msg, text_color=C['danger']))

        threading.Thread(target=work, daemon=True).start()

    # -------------------------------------------------------------- 页面刷新
    def refresh(self):
        pass
