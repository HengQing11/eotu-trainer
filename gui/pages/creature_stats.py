# -*- coding: utf-8 -*-
"""唯一的页面：生物数值编辑

职责很窄 —— 把 `CreatureStats` 数据表里的浮点数值改掉，然后打包成一个 mod pak。

性能约定（旧版在这里踩过坑，改版后刻意守住）：
  1. **进页面不做任何外部进程调用** —— repak / tasklist 都不在启动路径上
  2. 数据解析一次就缓存，切表才重新解析；改一个格子**不重新解析整张表**
  3. 表格按「当前显示的行集合」增量判断，集合没变就不重建
  4. 搜索输入做 200ms 防抖，避免每敲一个字符重建 281 行
  5. 改过的行用 tag 标色，不需要额外的列
"""
import os
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from .. import widgets as W
from ..core import creature_stats as CS
from ..core import gameproc, pakbuild, paths
from ..theme import C, F, FAMILY, GAP

PAK_NAME = 'EotUCustom_P.pak'
ROW_LIMIT = 400             # 单屏最多渲染多少行（防手滑输入空搜索后卡顿）
SEARCH_DEBOUNCE_MS = 200


class CreatureStatsPage(ctk.CTkFrame):
    title = '生物数值'
    key = 'stats'

    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        self.freeplay = False
        self.rows = {}
        self.filtered = []
        self.shown = []             # 表格里当前渲染的行名（用于判断要不要重建）
        self.edits = []             # 未打包的改动 [(行名, 属性, 旧, 新)]
        self.dirty_rows = set()
        self._search_job = None
        self._built = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build()

    # ================================================================ 构建
    def _build(self):
        card = W.Card(self)
        card.grid(row=0, column=0, sticky='nsew')
        self.grid_rowconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)
        body = card.body
        body.grid_rowconfigure(3, weight=1)          # 第 3 行是表格，吃掉剩余高度

        self._build_toolbar(body)
        self._build_batchbar(body)
        table_wrap = self._build_table(body)
        table_wrap.grid(row=3, column=0, sticky='nsew', pady=(10, 0))
        self._build_footer(body)

    def _build_toolbar(self, body):
        bar = ctk.CTkFrame(body, fg_color='transparent')
        bar.grid(row=0, column=0, sticky='ew')

        self.src_var = ctk.StringVar(value=CS.table_label(False))
        ctk.CTkSegmentedButton(
            bar, values=[CS.table_label(False), CS.table_label(True)],
            variable=self.src_var, command=self._on_switch_table,
            font=F.get('small'), fg_color=C['surface2'], selected_color=C['accent'],
            selected_hover_color=C['accent_h'], unselected_color=C['surface2'],
            unselected_hover_color=C['surface3'], text_color=C['text'],
            corner_radius=7, height=30).pack(side='left')

        self.search = ctk.CTkEntry(
            bar, placeholder_text='搜索生物内部名，如 BlackAnt / Queen / Beast',
            width=268, height=30, font=F.get('small'), fg_color=C['surface2'],
            border_color=C['border2'], corner_radius=7)
        self.search.pack(side='left', padx=(GAP, 0))
        self.search.bind('<KeyRelease>', self._on_search_key)

        ctk.CTkLabel(bar, text='显示列', font=F.get('small'),
                     text_color=C['text2']).pack(side='left', padx=(GAP, 0))
        self.preset_var = ctk.StringVar(value=CS.PRESETS[0][0])
        W.make_menu(bar, self.preset_var, [p[0] for p in CS.PRESETS], width=96,
                    command=lambda _v: self._on_switch_preset()).pack(side='left',
                                                                     padx=(6, 0))

        self.only_dirty = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(bar, text='只看改过的', variable=self.only_dirty,
                        command=self._on_only_dirty, font=F.get('small'),
                        text_color=C['text2'], fg_color=C['accent'],
                        hover_color=C['accent_h'], border_color=C['border2'],
                        checkbox_width=17, checkbox_height=17, corner_radius=4,
                        border_width=1.5).pack(side='left', padx=(GAP, 0))

        W.make_button(bar, '重新检测环境', self._probe, width=112
                      ).pack(side='right')
        W.make_button(bar, '把资产恢复原样', self._reset_workspace, width=126
                      ).pack(side='right', padx=(0, 8))

        self.info = ctk.CTkLabel(body, text='', font=F.get('small'),
                                 text_color=C['text3'], anchor='w', justify='left',
                                 wraplength=900)
        self.info.grid(row=1, column=0, sticky='ew', pady=(9, 0))

    def _build_batchbar(self, body):
        W.Divider(body).grid(row=2, column=0, sticky='ew', pady=(11, 0))
        bb = ctk.CTkFrame(body, fg_color='transparent')
        bb.grid(row=2, column=0, sticky='sw', pady=(12, 0))

        ctk.CTkLabel(bb, text='批量改', font=F.get('body_b'),
                     text_color=C['text']).pack(side='left')
        ctk.CTkLabel(bb, text='列', font=F.get('small'),
                     text_color=C['text2']).pack(side='left', padx=(14, 0))
        self.bulk_col = ctk.StringVar(value=CS.COL_ZH['Health'])
        self.bulk_menu = W.make_menu(bb, self.bulk_col,
                                     [c[1] for c in CS.COLUMNS], width=104)
        self.bulk_menu.pack(side='left', padx=(6, 12))

        ctk.CTkLabel(bb, text='范围', font=F.get('small'),
                     text_color=C['text2']).pack(side='left')
        self.bulk_scope = ctk.StringVar(value='当前筛选')
        W.make_menu(bb, self.bulk_scope, ['选中的行', '当前筛选', '全部生物'],
                    width=102).pack(side='left', padx=(6, 12))

        W.make_button(bb, '× 倍率', self._bulk_scale, width=78).pack(side='left')
        W.make_button(bb, '= 定值', self._bulk_set, width=78).pack(side='left',
                                                                   padx=(6, 0))

        self.dirty_lbl = ctk.CTkLabel(bb, text='', font=F.get('small'),
                                      text_color=C['text3'])
        self.dirty_lbl.pack(side='left', padx=(16, 0))
        W.make_button(bb, '撤销全部改动', self._undo_all, width=110
                      ).pack(side='left', padx=(10, 0))

    def _columns(self):
        for name, cols in CS.PRESETS:
            if name == self.preset_var.get():
                return cols
        return CS.PRESETS[0][1]

    def _build_table(self, body):
        wrap = ctk.CTkFrame(body, fg_color=C['surface'], width=1, height=1)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)

        self._style_tree()
        self.tree = ttk.Treeview(wrap, columns=(), show='headings',
                                 style='EotU.Treeview', height=10,
                                 selectmode='extended')
        self.tree.grid(row=0, column=0, sticky='nsew')

        vs = ttk.Scrollbar(wrap, orient='vertical', command=self.tree.yview,
                           style='EotU.Vertical.TScrollbar')
        vs.grid(row=0, column=1, sticky='ns')
        hs = ttk.Scrollbar(wrap, orient='horizontal', command=self.tree.xview,
                           style='EotU.Horizontal.TScrollbar')
        hs.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)

        self.tree.bind('<Double-1>', self._on_double_click)
        self.tree.bind('<Return>', self._on_enter)
        self.tree.tag_configure('dirty', background=C['warn_soft'],
                                foreground=C['warn'])
        self._apply_columns()
        return wrap

    def _build_footer(self, body):
        foot = ctk.CTkFrame(body, fg_color='transparent')
        foot.grid(row=4, column=0, sticky='ew', pady=(10, 0))
        foot.grid_columnconfigure(0, weight=1)

        self.count_lbl = ctk.CTkLabel(foot, text='', font=F.get('small'),
                                      text_color=C['text3'], anchor='w')
        self.count_lbl.grid(row=0, column=0, sticky='w')

        btns = ctk.CTkFrame(foot, fg_color='transparent')
        btns.grid(row=0, column=1, sticky='e')
        W.make_button(btns, '生成 pak', self._build_pak, kind='primary',
                      width=102).pack(side='left')
        W.make_button(btns, '装进游戏', self._install, width=102).pack(side='left',
                                                                      padx=(GAP, 0))
        W.make_button(btns, '从游戏卸载', self._uninstall, kind='danger',
                      width=112).pack(side='left', padx=(GAP, 0))

        self.note = ctk.CTkLabel(body, text='', font=F.get('small'),
                                 text_color=C['text3'], anchor='w', justify='left',
                                 wraplength=900)
        self.note.grid(row=5, column=0, sticky='ew', pady=(8, 0))

    def _style_tree(self):
        st = ttk.Style()
        try:
            st.theme_use('clam')
        except tk.TclError:
            pass
        st.configure('EotU.Treeview', background=C['surface'], fieldbackground=C['surface'],
                     foreground=C['text'], rowheight=25, borderwidth=0, relief='flat',
                     font=(FAMILY, 9))
        st.configure('EotU.Treeview.Heading', background=C['surface2'],
                     foreground=C['text2'], relief='flat', borderwidth=0,
                     font=(FAMILY, 9, 'bold'))
        st.map('EotU.Treeview', background=[('selected', C['accent_soft'])],
               foreground=[('selected', C['accent_text'])])
        st.map('EotU.Treeview.Heading', background=[('active', C['surface3'])])
        for name, orient in (('EotU.Vertical.TScrollbar', 'vertical'),
                             ('EotU.Horizontal.TScrollbar', 'horizontal')):
            st.configure(name, background=C['border2'], troughcolor=C['surface'],
                         bordercolor=C['surface'], arrowcolor=C['text3'],
                         borderwidth=0, arrowsize=12, relief='flat', gripcount=0)
            st.map(name, background=[('active', C['text3']), ('pressed', C['text2'])])

    def _apply_columns(self):
        """按预设重建列（只动列定义，不销毁控件）"""
        cols = ['row'] + self._columns()
        self.tree.configure(columns=cols, displaycolumns=cols)
        self.tree.heading('row', text='行名（内部名）', anchor='w')
        self.tree.column('row', width=212, minwidth=160, anchor='w', stretch=True)
        for c in self._columns():
            self.tree.heading(c, text=CS.COL_ZH[c], anchor='e')
            self.tree.column(c, width=88, minwidth=70, anchor='e', stretch=False)
        self.shown = []                 # 列变了，行值要重填

    # ================================================================ 数据
    def refresh(self):
        """主窗口切到本页时调用 —— 只在第一次真正加载数据"""
        if not self._built:
            self.reload()

    def reload(self):
        try:
            pakbuild.ensure_workspace()
        except (pakbuild.PakError, OSError) as e:
            self.info.configure(text='准备资产工作区失败：%s' % e, text_color=C['danger'])
            return
        try:
            self.rows, _table = CS.load(self.freeplay)
        except (CS.StatsError, pakbuild.PakError) as e:
            self.info.configure(text='载入数值表失败：%s' % e, text_color=C['danger'])
            return
        self._built = True
        self._update_info(loaded=True)
        self._apply_filter(force=True)

    def _update_info(self, loaded=False, repak=None):
        ov = CS.overview(self.freeplay) if loaded else None
        bits = []
        if ov:
            bits.append('%s · %d 行 · %d 种生物 · %d 个可改格子'
                        % (CS.table_label(self.freeplay), ov['rows'],
                           ov['species'], ov['cells']))
        state, text = gameproc.status()
        bits.append(text)
        if repak is None:
            if pakbuild.workspace_ready() and pakbuild.repak_path():
                bits.append('环境就绪')
            else:
                bits.append('环境未就绪（点右侧「重新检测环境」）')
        else:
            bits.append('repak ' + ('就绪' if repak[0] else '不可用：' + str(repak[1])))
        self.info.configure(text=' · '.join(bits), text_color=C['text3'])

    # ================================================================ 表格
    def _on_switch_table(self, value):
        free = (value == CS.table_label(True))
        if free == self.freeplay:
            return
        self.freeplay = free
        self.edits = []
        self.dirty_rows = set()
        CS.invalidate()
        self._built = False
        self.reload()
        self.app.log('已切换到「%s」。' % value)

    def _on_switch_preset(self):
        self._apply_columns()
        self._apply_filter(force=True)

    def _on_only_dirty(self):
        self._apply_filter(force=True)

    def _on_search_key(self, _ev=None):
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:                                  # noqa: BLE001
                pass
        self._search_job = self.after(SEARCH_DEBOUNCE_MS, self._apply_filter)

    def _visible_names(self):
        kw = self.search.get().strip().lower()
        if self.only_dirty.get():
            base = sorted(self.dirty_rows)
        else:
            base = sorted(self.rows)
        return [n for n in base if kw in n.lower()] if kw else list(base)

    def _apply_filter(self, force=False):
        self._search_job = None
        names = self._visible_names()
        if not force and names == self.shown:
            return
        self.filtered = names
        limit = names[:ROW_LIMIT]

        tree = self.tree
        tree.delete(*tree.get_children())
        cols = self._columns()
        for n in limit:
            r = self.rows[n]
            tree.insert('', 'end', iid=n,
                        values=[n] + [CS.fmt(r.get(c)) for c in cols],
                        tags=('dirty',) if n in self.dirty_rows else ())
        self.shown = list(limit)
        self._update_count(len(names))

    def _update_count(self, total=None):
        if total is None:
            total = len(self.filtered)
        extra = ''
        if total > ROW_LIMIT:
            extra = '（只渲染前 %d 行，用搜索缩小范围）' % ROW_LIMIT
        self.count_lbl.configure(
            text='显示 %d / %d 行 %s　·　双击单元格改值，回车也能改'
                 % (len(self.shown), len(self.rows), extra))
        n = len(self.edits)
        self.dirty_lbl.configure(
            text=('已改动 %d 处（%d 行），未打包' % (n, len(self.dirty_rows)))
            if n else '',
            text_color=C['warn'] if n else C['text3'])

    # ================================================================ 编辑
    def _cell_at(self, ev):
        iid = self.tree.identify_row(ev.y)
        col = self.tree.identify_column(ev.x)
        if not iid or not col:
            return None, None
        idx = int(col.replace('#', '')) - 1
        if idx < 1:                       # 第 1 列是行名，不可改
            return iid, None
        cols = self._columns()
        if idx - 1 >= len(cols):
            return iid, None
        return iid, cols[idx - 1]

    def _on_double_click(self, ev):
        iid, attr = self._cell_at(ev)
        if iid and attr:
            self._edit_cell(iid, attr)

    def _on_enter(self, _ev=None):
        sel = self.tree.selection()
        if not sel:
            return
        cols = self._columns()
        self._edit_cell(sel[0], cols[0])

    def _edit_cell(self, row, attr):
        cur = self.rows.get(row, {}).get(attr)
        if cur is None:
            return
        new = W.ask_number(self, '修改 %s · %s' % (row, CS.COL_ZH[attr]),
                           CS.COL_DESC[attr], init=CS.fmt(cur), lo=0, hi=1e9)
        if new is None or abs(float(new) - cur) < 1e-9:
            return
        applied = CS.apply_edits({(row, attr): new}, self.freeplay)
        if not applied:
            return
        self._note_edits(applied)
        self.app.log('%s 的 %s：%s → %s（已写入工作区，尚未打包）'
                     % (row, CS.COL_ZH[attr], CS.fmt(cur), CS.fmt(new)))

    def _note_edits(self, applied):
        """记录改动 + 就地更新界面（不重建表格）"""
        self.edits.extend(applied)
        cols = self._columns()
        for rn, _attr, _old, _new in applied:
            self.dirty_rows.add(rn)
            if rn in self.shown:
                self.tree.item(rn, values=[rn] + [CS.fmt(self.rows[rn].get(c))
                                                  for c in cols],
                               tags=('dirty',))
        self._update_count()

    # ================================================================ 批量
    def _scope_rows(self):
        scope = self.bulk_scope.get()
        if scope == '选中的行':
            sel = list(self.tree.selection())
            if sel:
                return sel
            return list(self.filtered)          # 没选就退回当前筛选
        if scope == '当前筛选':
            return list(self.filtered)
        return sorted(self.rows)

    def _bulk(self, kind):
        attr = CS.COL_KEY.get(self.bulk_col.get())
        if not attr:
            return
        zh = CS.COL_ZH[attr]
        if kind == 'scale':
            val = W.ask_number(self, '按倍率改「%s」' % zh,
                               '范围内的每一行都乘以这个系数。1.5 = 增强 50%%，'
                               '0.5 = 减半。', init='2', lo=0, hi=1000)
        else:
            val = W.ask_number(self, '把「%s」设为固定值' % zh,
                               '范围内的每一行都写成这个值。', init='100',
                               lo=0, hi=1e9)
        if val is None:
            return

        targets = self._scope_rows()
        edits = (CS.scale(targets, attr, float(val), self.freeplay) if kind == 'scale'
                 else CS.set_all(targets, attr, float(val), self.freeplay))
        if not edits:
            self.app.log('范围内没有可改的行。', 'err')
            return

        what = ('×%g' % val) if kind == 'scale' else ('= %g' % val)
        if not W.confirm(self, '确认批量修改？',
                         '「%s」共 %d 行，%s。' % (zh, len(edits), what),
                         detail='改动只写进工作区，点「生成 pak」并装进游戏后才生效。\n'
                                '改错了可以点「撤销全部改动」。',
                         ok_text='执行'):
            return

        applied = CS.apply_edits(edits, self.freeplay)
        self._note_edits(applied)
        self.app.log('批量修改完成：%s %s，共 %d 处。' % (zh, what, len(applied)), 'ok')
        if self.only_dirty.get():
            self._apply_filter(force=True)

    def _bulk_scale(self):
        self._bulk('scale')

    def _bulk_set(self):
        self._bulk('set')

    def _undo_all(self):
        if not self.edits:
            self.app.log('没有未打包的改动。')
            return
        if not W.confirm(self, '撤销全部改动？',
                         '把未打包的 %d 处改动全部还原（%d 行）。'
                         % (len(self.edits), len(self.dirty_rows)),
                         ok_text='撤销'):
            return
        back = CS.undo(self.edits, self.freeplay)
        self.edits = []
        self.dirty_rows = set()
        self._apply_filter(force=True)
        self.app.log('已撤销 %d 处改动。' % len(back), 'ok')

    # ================================================================ 打包
    def _build_pak(self):
        out = os.path.join(paths.APP_DIR, 'build', PAK_NAME)
        self.app.log('正在打包…')
        self.update_idletasks()
        try:
            pakbuild.pack(out)
        except (pakbuild.PakError, OSError) as e:
            self.app.log('打包失败：%s' % e, 'err')
            self.note.configure(text='打包失败：%s' % e, text_color=C['danger'])
            return
        size = os.path.getsize(out) / 1048576.0
        self.note.configure(
            text='已生成：%s（%.2f MB）。装进游戏后重启游戏生效。' % (out, size),
            text_color=C['ok'])
        self.app.log('打包完成：%s（%.2f MB）' % (out, size), 'ok')

    def _pak_path(self):
        return os.path.join(paths.APP_DIR, 'build', PAK_NAME)

    def _install(self):
        out = self._pak_path()
        if not os.path.isfile(out):
            self.app.log('还没有 pak，请先点「生成 pak」。', 'err')
            return
        d = pakbuild.game_paks_dir()
        if not W.confirm(self, '装进游戏目录？',
                         '将把 %s 复制到：\n%s' % (PAK_NAME, d),
                         detail='只是往游戏目录里「新增」一个文件，不会改动或删除任何原有文件。\n'
                                '想撤销就点「从游戏卸载」。\n'
                                '这一步会写入游戏安装目录，请确认你接受。',
                         ok_text='确认复制'):
            return
        try:
            dst = pakbuild.install(out)
        except (pakbuild.PakError, OSError) as e:
            self.app.log('安装失败：%s' % e, 'err')
            return
        gameproc.invalidate()
        self._update_info(loaded=True, repak=pakbuild.repak_ok())
        self.note.configure(text='已装到游戏：%s　重启游戏后生效。' % dst,
                            text_color=C['ok'])
        self.app.log('已装到游戏：%s' % dst, 'ok')

    def _uninstall(self):
        if not W.confirm(self, '从游戏卸载？',
                         '删除游戏 Paks 目录里的 %s。' % PAK_NAME,
                         detail='只会删这一个文件，游戏原有文件不受影响。',
                         ok_text='卸载'):
            return
        if pakbuild.uninstall(PAK_NAME):
            self.app.log('已从游戏卸载 %s。' % PAK_NAME, 'ok')
        else:
            self.app.log('游戏目录里没有 %s，可能本来就没装。' % PAK_NAME, 'err')

    def _reset_workspace(self):
        if not W.confirm(self, '把资产恢复原样？',
                         '工作区里所有未打包的改动都会作废，从原始资产重新解一份出来。',
                         danger=True, ok_text='恢复'):
            return
        try:
            pakbuild.reset_workspace()
        except (pakbuild.PakError, OSError) as e:
            self.app.log('恢复失败：%s' % e, 'err')
            return
        CS.invalidate()
        self.edits = []
        self.dirty_rows = set()
        self._built = False
        self.reload()
        self.app.log('工作区已恢复原样。', 'ok')

    def _probe(self):
        """只在用户主动点击时探测外部环境（repak 要起进程，别放启动路径上）"""
        ok, msg = pakbuild.repak_ok(force=True)
        gameproc.invalidate()
        self._update_info(loaded=self._built, repak=(ok, msg))
        self.app.log('环境检测：repak %s；%s' % (msg, gameproc.status()[1]),
                     'ok' if ok else 'err')
