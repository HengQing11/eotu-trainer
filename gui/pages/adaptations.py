# -*- coding: utf-8 -*-
"""蚁皇浆加点 —— 改的是**存档里的加点等级**，不碰游戏数据表

和「改数据表 + 打包 pak 覆盖」是两条完全不同的路：
  这里只改存档里的加点字段（IP 微调 / 适应性 / 物种解锁），
  游戏文件一个都不动、不打包 pak。效果等于你自己在游戏里一点一点点出来。

写存档统一走 actions.commit，流程固定、不允许跳步：
  查游戏是否在跑 -> 自动备份 -> 等长改写 -> 回读校验

性能约定：进页面不起外部进程；数值表（算「生效值」用）第一次要准备资产工作区，
属于重 I/O，放到 after() 里做，先把页面渲染出来。
"""
import os
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from .. import widgets as W
from ..core import actions, creature_stats, fieldlib, gvas, jelly, pakbuild, saves
from ..theme import C, F, FAMILY, GAP


def leveldata_of(save_name):
    """存档 -> 它的关卡数据文件名（蚁皇浆余额存在那个文件里）

    用存档里自己声明的 `LinkedSaveGame`，**不猜命名规律** ——
    `X.sav -> XLevelData.sav` 这条规律对 Stage / NG+ 档是错的。
    """
    return saves.leveldata_of(save_name)


class AdaptationsPage(ctk.CTkFrame):
    title = '加点详情'
    key = 'jelly'

    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        self.sf = None
        self.ads = []
        self.jelly_val = None
        self.sw_expanded = False
        self._table_ready = False
        self.tree = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.scroll = W.scroll_frame(self)
        self.scroll.grid(row=0, column=0, sticky='nsew')
        self.scroll.grid_columnconfigure(0, weight=1)
        self._build()

    # -------------------------------------------------------------- 骨架
    def _build(self):
        s = self.scroll
        r = 0

        # 指标卡
        kpi = ctk.CTkFrame(s, fg_color='transparent')
        kpi.grid(row=r, column=0, sticky='ew', pady=(0, GAP))
        for i in range(3):
            kpi.grid_columnconfigure(i, weight=1, uniform='k')
        self.k_jelly = W.StatCard(kpi, '蚁皇浆余额', '—')
        self.k_jelly.grid(row=0, column=0, sticky='ew', padx=(0, GAP))
        self.k_spent = W.StatCard(kpi, '加点已投入', '—')
        self.k_spent.grid(row=0, column=1, sticky='ew', padx=(0, GAP))
        self.k_items = W.StatCard(kpi, '加点项目', '—')
        self.k_items.grid(row=0, column=2, sticky='ew')
        r += 1

        # 蚁皇浆
        card = W.Card(
            s, '蚁皇浆',
            '余额存在这个档的关卡数据文件里。补满后回游戏读一次档就能看到。'
            '按等比涨价，20 亿大约够单一项买到 140 点。')
        card.grid(row=r, column=0, sticky='ew', pady=(0, GAP))
        b = ctk.CTkFrame(card.body, fg_color='transparent')
        b.grid(row=0, column=0, sticky='w')
        W.make_button(b, '补满到 20 亿', self._refill, kind='primary').pack(side='left')
        W.make_button(b, '设定为…', self._set_jelly).pack(side='left', padx=(GAP, 0))
        W.make_button(b, '重新读档', self.refresh).pack(side='left', padx=(GAP, 0))
        self.jelly_note = ctk.CTkLabel(card.body, text='', font=F.get('small'),
                                       text_color=C['text3'], anchor='w',
                                       justify='left', wraplength=860)
        self.jelly_note.grid(row=1, column=0, sticky='ew', pady=(9, 0))
        r += 1

        # 未登记字段告警（默认隐藏）
        self.warn_card = W.Card(s, '字段库还没收录这些加点字段')
        self.warn_card.grid(row=r, column=0, sticky='ew', pady=(0, GAP))
        self.warn_card.grid_remove()
        self.warn_body = ctk.CTkLabel(self.warn_card.body, text='', font=F.get('small'),
                                      text_color=C['danger'], anchor='w',
                                      justify='left', wraplength=860)
        self.warn_body.grid(row=0, column=0, sticky='ew')
        r += 1

        # 加点清单
        self.addon_card = W.Card(
            s, '加点清单',
            '「设定」可以直接把某一项改到任意点数，不用在游戏里一下一下点；'
            '「清零」把这一项退回 0，游戏会从第 1 点的价格重新算。'
            '改完回游戏读档生效。')
        self.addon_card.grid(row=r, column=0, sticky='ew', pady=(0, GAP))
        self.addon_box = ctk.CTkFrame(self.addon_card.body, fg_color='transparent')
        self.addon_box.grid(row=0, column=0, sticky='ew')
        self.addon_box.grid_columnconfigure(0, weight=1)
        r += 1

        # 适应性 / 物种解锁
        self.sw_card = W.Card(
            s, '适应性 与 物种解锁',
            '适应性每个单位 4 选 2，可以随时切换。改动直接写进存档。')
        self.sw_card.grid(row=r, column=0, sticky='ew', pady=(0, GAP))

        head = ctk.CTkFrame(self.sw_card.body, fg_color='transparent')
        head.grid(row=0, column=0, sticky='ew')
        head.grid_columnconfigure(0, weight=1)
        self.sw_notice = ctk.CTkLabel(head, text='', font=F.get('small'),
                                      text_color=C['text3'], anchor='w',
                                      justify='left', wraplength=740)
        self.sw_notice.grid(row=0, column=0, sticky='ew')
        self.sw_btn = W.make_button(head, '展开', self._toggle_switches, width=76)
        self.sw_btn.grid(row=0, column=1, sticky='e', padx=(10, 0))

        self.sw_box = ctk.CTkFrame(self.sw_card.body, fg_color='transparent')
        self.sw_box.grid(row=1, column=0, sticky='ew', pady=(8, 0))
        self.sw_box.grid_columnconfigure(0, weight=1)
        self.sw_box.grid_remove()

    # -------------------------------------------------------------- 路径
    def save_path(self):
        return actions.save_path(self.app.save_name)

    def leveldata_path(self):
        return actions.save_path(leveldata_of(self.app.save_name))

    # -------------------------------------------------------------- 数据
    def refresh(self):
        p = self.save_path()
        if not os.path.isfile(p):
            self.app.log('找不到存档 %s' % self.app.save_name, 'err')
            self.sf, self.ads = None, []
            self.k_jelly.set('—', '存档不存在')
            self.k_spent.set('—')
            self.k_items.set('—')
            self._build_addons()
            return

        self.sf = gvas.SaveFile(p)
        self.ads = jelly.addons(self.sf)
        spent = sum(a[2] for a in self.ads)

        lp = self.leveldata_path()
        self.jelly_val = jelly.main_jelly(lp) if os.path.isfile(lp) else None

        self.k_jelly.set('—' if self.jelly_val is None else format(self.jelly_val, ','),
                         '' if self.jelly_val is not None
                         else '找不到 %s' % leveldata_of(self.app.save_name))
        self.k_spent.set(format(spent, ','), '约合蚁皇浆')
        self.k_items.set('%d 项' % len(self.ads),
                         '共 %d 点' % sum(a[1] for a in self.ads))

        if self.jelly_val is not None:
            self.jelly_note.configure(
                text='当前余额按等比涨价大约还能买 %d 点（单一项）。'
                     '第 1 点 1 浆，之后每点 ×1.15。' % jelly.budget_points(self.jelly_val))
        else:
            self.jelly_note.configure(text='读不到蚁皇浆余额 —— 补满功能会不可用。')

        self._build_addons()
        self._build_switches()
        self._check_unknown()

    def _build_addons(self):
        for w in self.addon_box.winfo_children():
            w.destroy()
        self.tree = None
        if not self.ads:
            ctk.CTkLabel(self.addon_box,
                         text=('这个存档还没有任何蚁皇浆加点。' if self.sf
                               else '读不到存档。'),
                         font=F.get('small'), text_color=C['text3'], anchor='w'
                         ).grid(row=0, column=0, sticky='ew', pady=4)
            return

        # 用原生 ttk.Treeview，而不是每行拼一堆 CTk 控件：
        # customtkinter 的控件内部是好几层 canvas，实测 12 行要 465 ms；
        # Treeview 建一次就够，之后加多少行都一样快。
        self._style_tree()
        self.tree = ttk.Treeview(
            self.addon_box, columns=('unit', 'item', 'pts', 'cost', 'eff'),
            show='headings', style='EotU.Treeview', selectmode='browse',
            height=min(max(len(self.ads), 4), 14))
        self.tree.grid(row=0, column=0, sticky='ew')

        for cid, text, width, anchor, stretch in (
                ('unit', '单位', 132, 'w', False),
                ('item', '项目', 132, 'w', False),
                ('pts', '点数', 66, 'e', False),
                ('cost', '已投入', 120, 'e', False),
                ('eff', '生效值', 320, 'w', True)):
            self.tree.heading(cid, text=text, anchor=anchor)
            self.tree.column(cid, width=width, anchor=anchor,
                             stretch=stretch, minwidth=56)

        for f, pts, cost in self.ads:
            e = jelly.effective(f, pts)
            eff = jelly.eff_text(e['rows'])
            if not eff:
                eff = (jelly.delta_text(f, e['variants']) + '（技能表，见总表）'
                       if e['variants'] else '—')
            self.tree.insert('', 'end', iid=f.name,
                             values=(f.unit_zh, f.item, pts, format(cost, ','),
                                     '  ' + eff))

        self.tree.bind('<Double-1>', self._on_row_activate)
        self.tree.bind('<Return>', lambda _e: self._edit_selected())

        bar = ctk.CTkFrame(self.addon_box, fg_color='transparent')
        bar.grid(row=1, column=0, sticky='ew', pady=(8, 0))
        bar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(bar, text='选中一行后按右边的按钮，或者直接双击那一行。',
                     font=F.get('small'), text_color=C['text3'], anchor='w'
                     ).grid(row=0, column=0, sticky='w')
        W.make_button(bar, '设定点数…', self._edit_selected, width=98
                      ).grid(row=0, column=1, sticky='e')
        W.make_button(bar, '清零这一项', self._clear_selected, width=104
                      ).grid(row=0, column=2, sticky='e', padx=(8, 0))

        # 工作区没就绪时「生效值」只剩加分量 —— 备好表再补算一次
        if not self._table_ready:
            self.after(60, self._prepare_table)

    def _style_tree(self):
        st = ttk.Style()
        try:
            st.theme_use('clam')
        except tk.TclError:
            pass
        st.configure('EotU.Treeview', background=C['surface'],
                     fieldbackground=C['surface'], foreground=C['text'],
                     rowheight=26, borderwidth=0, relief='flat', font=(FAMILY, 10))
        st.configure('EotU.Treeview.Heading', background=C['surface2'],
                     foreground=C['text2'], relief='flat', borderwidth=0,
                     font=(FAMILY, 10, 'bold'))
        st.map('EotU.Treeview', background=[('selected', C['accent_soft'])],
               foreground=[('selected', C['accent_text'])])
        st.map('EotU.Treeview.Heading', background=[('active', C['surface3'])])

    # ---- 表格交互
    def _field_by_name(self, name):
        return next((f for f, _p, _c in self.ads if f.name == name), None)

    def _selected_field(self):
        if self.tree is None:
            return None
        sel = self.tree.selection()
        return self._field_by_name(sel[0]) if sel else None

    def _on_row_activate(self, event):
        if self.tree is None:
            return
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self._edit_selected()

    def _edit_selected(self):
        f = self._selected_field()
        if f is None:
            self.app.log('先在上面选一行，或者直接双击要改的那一行。', 'warn')
            return
        pts = next((p for n, p, _c in self.ads if n.name == f.name), 0)
        self._set_points(f, pts)

    def _clear_selected(self):
        f = self._selected_field()
        if f is None:
            self.app.log('先在上面选一行，或者直接双击要改的那一行。', 'warn')
            return
        self._clear_one(f)

    def _prepare_table(self):
        """备好资产工作区，好让「生效值」显示绝对值而不是只有加分量

        这是重 I/O（几秒），所以放在 after 里做，先把页面渲染出来。
        """
        try:
            pakbuild.ensure_workspace()
            creature_stats.load()
        except Exception:                                               # noqa: BLE001
            return
        self._table_ready = True
        if self.ads:
            self._build_addons()

    def _check_unknown(self):
        if not self.sf:
            return
        unk = jelly.unknown_addons(self.sf)
        if unk:
            self.warn_body.configure(
                text='\n'.join('%s —— %s' % (u, fieldlib.unknown_hint(u)) for u in unk))
            self.warn_card.grid()
        else:
            self.warn_card.grid_remove()

    # -------------------------------------------------------------- 开关
    def _toggle_switches(self):
        self.sw_expanded = not self.sw_expanded
        self.sw_btn.configure(text='收起' if self.sw_expanded else '展开')
        if self.sw_expanded:
            self.sw_box.grid()
        else:
            self.sw_box.grid_remove()

    def _build_switches(self):
        if not self.sf:
            return
        ad = jelly.adapts(self.sf)
        un = jelly.unlocks(self.sf)

        if self.sw_expanded:
            for w in self.sw_box.winfo_children():
                w.destroy()
            r = 0
            for label, items in (('适应性（每个单位 4 选 2）', ad), ('物种解锁', un)):
                if not items:
                    continue
                ctk.CTkLabel(self.sw_box, text='%s —— %d 项' % (label, len(items)),
                             font=F.get('body_b'), text_color=C['text'], anchor='w'
                             ).grid(row=r, column=0, sticky='ew', pady=(10 if r else 0, 2))
                r += 1
                for f, cur in items:
                    W.ToggleRow(self.sw_box, '%s · %s' % (f.unit_zh, f.item),
                                f.note or '', value=cur, command=self._on_switch(f)
                                ).grid(row=r, column=0, sticky='ew')
                    r += 1

        self.sw_notice.configure(text='存档里出现了 %d 个适应性开关、%d 个物种解锁开关。'
                                      % (len(ad), len(un)))

    def _on_switch(self, field):
        def cb(val):
            self._write_bool(field, val)
        return cb

    # -------------------------------------------------------------- 写入
    def _commit(self, sf, note, verify=None):
        r = actions.commit(sf, note=note, verify=verify)
        self.app.log(r.msg.replace('\n', ' '), 'ok' if r.ok else 'err')
        if r.ok:
            self.refresh()
        return r.ok

    def _write_bool(self, field, val):
        sf = gvas.SaveFile(self.save_path())
        if not sf.set_bool(field.name, bool(val)):
            self.app.log('存档里没有字段 %s，跳过。' % field.name, 'err')
            return
        self._commit(sf, 'toggle', verify=lambda p: (
            gvas.read(open(p, 'rb').read(), field.name, 'BoolProperty') == bool(val),
            '%s = %s' % (field.name, val)))

    def _write_int(self, field_name, val, label):
        sf = gvas.SaveFile(self.save_path())
        if not sf.set_int(field_name, int(val)):
            self.app.log('存档里没有字段 %s，跳过。' % field_name, 'err')
            return
        self._commit(sf, 'addon', verify=lambda p: (
            gvas.read(open(p, 'rb').read(), field_name, 'IntProperty') == int(val),
            '%s = %s' % (label, val)))

    def _set_points(self, field, cur):
        v = W.ask_number(self, '设定 %s · %s' % (field.unit_zh, field.item),
                         '直接写入存档的点数，改完回游戏读档生效。'
                         '注意：游戏里再次加点时仍按原价继续。',
                         init=cur, lo=0, hi=2_000_000)
        if v is None:
            return
        self._write_int(field.name, int(v), '%s %s' % (field.unit_zh, field.item))

    def _clear_one(self, field):
        pts = self.sf.get_int(field.name, default=0) if self.sf else 0
        if not W.confirm(self, '清零这一项？',
                         '%s · %s（当前 %d 点）将被清零。'
                         % (field.unit_zh, field.item, pts),
                         detail='加点的蚁皇浆不会退回。想加回来重新加即可，\n'
                                '价格从第 1 点重新算。'):
            return
        self._write_int(field.name, 0, '%s %s' % (field.unit_zh, field.item))

    # -------------------------------------------------------------- 蚁皇浆
    def _refill(self):
        lp = self.leveldata_path()
        if not os.path.isfile(lp):
            self.app.log('找不到 %s' % leveldata_of(self.app.save_name), 'err')
            return
        cap = int(self.app.cfg.get('jelly_cap', 2_000_000_000))
        slots = jelly.jelly_slots(lp)
        detail = '\n'.join('槽位 %d：%s' % (i + 1, format(s[1], ','))
                           for i, s in enumerate(slots))
        if not W.confirm(self, '补满蚁皇浆？',
                         '把 %s 里全部 %d 个槽位都设为 %s。'
                         % (leveldata_of(self.app.save_name), len(slots), format(cap, ',')),
                         detail=detail + '\n\n留了 1.4 亿余量，避免游戏发奖励时整数溢出。'):
            return
        sf, changed = jelly.set_jelly(lp, cap)
        if not changed:
            self.app.log('没找到蚁皇浆字段，未改动。', 'err')
            return
        r = actions.commit(sf, 'refillJelly', verify=lambda p: (
            all(s[1] == cap for s in jelly.jelly_slots(p)),
            '全部槽位已确认 = %s' % format(cap, ',')))
        self.app.log(r.msg.replace('\n', ' '), 'ok' if r.ok else 'err')
        if r.ok:
            self.refresh()

    def _set_jelly(self):
        lp = self.leveldata_path()
        if not os.path.isfile(lp):
            self.app.log('找不到 %s' % leveldata_of(self.app.save_name), 'err')
            return
        cur = jelly.main_jelly(lp) or 0
        v = W.ask_number(self, '设定蚁皇浆数量',
                         '会同时写进这个存档里的所有槽位（玩家巢 + 空巢）。',
                         init=cur, lo=0, hi=2_000_000_000)
        if v is None:
            return
        sf, changed = jelly.set_jelly(lp, int(v))
        if not changed:
            self.app.log('没找到蚁皇浆字段，未改动。', 'err')
            return
        r = actions.commit(sf, 'setJelly', verify=lambda p: (
            all(s[1] == int(v) for s in jelly.jelly_slots(p)),
            '全部槽位已确认 = %s' % format(int(v), ',')))
        self.app.log(r.msg.replace('\n', ' '), 'ok' if r.ok else 'err')
        if r.ok:
            self.refresh()
