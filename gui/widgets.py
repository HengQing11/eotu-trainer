# -*- coding: utf-8 -*-
"""复用组件 —— 界面上所有元素的统一出处

页面代码只负责摆放和接线，外观全在这里决定。改风格只改这一个文件。
（组件库只保留当前真正在用的，避免死代码。加新组件前先看看下面有没有能复用的。）
"""
import customtkinter as ctk

from .theme import C, F, CARD_PAD, RADIUS, BTN_H


# ------------------------------------------------------------------ 基础容器

class Card(ctk.CTkFrame):
    """白卡片。内容放进 self.body"""

    def __init__(self, master, title=None, desc=None, pad=CARD_PAD, **kw):
        kw.setdefault('fg_color', C['surface'])
        kw.setdefault('corner_radius', RADIUS)
        kw.setdefault('border_width', 1)
        kw.setdefault('border_color', C['border'])
        super().__init__(master, **kw)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # width/height=1：空的 CTkFrame 默认要 200×200，会把卡片顶得很高
        wrap = ctk.CTkFrame(self, fg_color='transparent', width=1, height=1)
        wrap.grid(row=0, column=0, sticky='nsew', padx=pad, pady=pad)
        wrap.grid_columnconfigure(0, weight=1)

        r = 0
        if title:
            ctk.CTkLabel(wrap, text=title, font=F.get('h3'), text_color=C['text'],
                         anchor='w').grid(row=r, column=0, sticky='ew')
            r += 1
        if desc:
            ctk.CTkLabel(wrap, text=desc, font=F.get('small'), text_color=C['text3'],
                         anchor='w', justify='left', wraplength=860
                         ).grid(row=r, column=0, sticky='ew', pady=(3, 0))
            r += 1

        # 正文行要跟着卡片一起纵向拉伸，否则 sticky='nsew' 不生效
        wrap.grid_rowconfigure(r, weight=1)
        self.body = ctk.CTkFrame(wrap, fg_color='transparent', width=1, height=1)
        self.body.grid(row=r, column=0, sticky='nsew', pady=(10 if r else 0, 0))
        self.body.grid_columnconfigure(0, weight=1)


class Divider(ctk.CTkFrame):
    def __init__(self, master, **kw):
        kw.setdefault('height', 1)
        kw.setdefault('fg_color', C['border'])
        super().__init__(master, **kw)


def scroll_frame(master, **kw):
    """统一样式的滚动容器（CTk 默认滚动条是深灰的，浅色主题下很跳）"""
    kw.setdefault('fg_color', 'transparent')
    kw.setdefault('scrollbar_fg_color', 'transparent')
    kw.setdefault('scrollbar_button_color', C['border2'])
    kw.setdefault('scrollbar_button_hover_color', C['text3'])
    return ctk.CTkScrollableFrame(master, **kw)


# ------------------------------------------------------------------ 按钮

def make_button(master, text, command, kind='ghost', width=None, height=BTN_H, **kw):
    """kind: primary / ghost / danger"""
    style = {
        'primary': dict(fg_color=C['accent'], hover_color=C['accent_h'],
                        text_color='#FFFFFF', border_width=0),
        'ghost': dict(fg_color=C['surface'], hover_color=C['surface3'],
                      text_color=C['text'], border_width=1, border_color=C['border2']),
        'danger': dict(fg_color=C['danger'], hover_color=C['danger_h'],
                       text_color='#FFFFFF', border_width=0),
    }.get(kind, {})
    style.update(kw)
    b = ctk.CTkButton(master, text=text, command=command, corner_radius=7,
                      height=height, font=F.get('body'), **style)
    if width:
        b.configure(width=width)
    return b


def make_menu(master, variable, values, width=110, command=None, height=BTN_H - 2):
    """统一样式的下拉框"""
    return ctk.CTkOptionMenu(
        master, variable=variable, values=values, width=width, height=height,
        font=F.get('small'), fg_color=C['surface2'], button_color=C['surface2'],
        button_hover_color=C['surface3'], text_color=C['text'],
        dropdown_fg_color=C['surface'], dropdown_text_color=C['text'],
        dropdown_hover_color=C['surface3'], corner_radius=7, command=command)


# ------------------------------------------------------------------ 对话框

def _center(dlg, parent, w, h):
    dlg.update_idletasks()
    try:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x, y = px + (pw - w) // 2, py + (ph - h) // 3
    except Exception:                                          # noqa: BLE001
        x = y = 200
    dlg.geometry('%dx%d+%d+%d' % (w, h, max(x, 0), max(y, 0)))


def _modal(dlg, parent):
    dlg.transient(parent.winfo_toplevel())
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.lift()
    dlg.focus_force()


def _dialog_shell(parent, title, w, h):
    dlg = ctk.CTkToplevel(parent)
    dlg.title(title)
    dlg.configure(fg_color=C['window'])
    _modal(dlg, parent)
    _center(dlg, parent, w, h)
    box = ctk.CTkFrame(dlg, fg_color=C['surface'], corner_radius=RADIUS,
                       border_width=1, border_color=C['border'])
    box.pack(fill='both', expand=True, padx=14, pady=14)
    box.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(box, text=title, font=F.get('h3'), text_color=C['text'],
                 anchor='w').grid(row=0, column=0, sticky='ew', padx=18, pady=(16, 6))
    return dlg, box


def _bind_keys(dlg, on_ok):
    try:
        dlg.bind('<Return>', lambda _e: on_ok())
        dlg.bind('<Escape>', lambda _e: dlg.destroy())
    except Exception:                                          # noqa: BLE001
        pass


def confirm(parent, title, message, danger=False, ok_text='确定',
            cancel_text='取消', detail=''):
    """确认对话框 -> bool"""
    dlg, box = _dialog_shell(parent, title, 460, 250 if detail else 208)
    ctk.CTkLabel(box, text=message, font=F.get('body'),
                 text_color=C['danger'] if danger else C['text2'],
                 anchor='w', justify='left', wraplength=400
                 ).grid(row=1, column=0, sticky='ew', padx=18)
    if detail:
        ctk.CTkLabel(box, text=detail, font=F.get('small'), text_color=C['text3'],
                     anchor='w', justify='left', wraplength=400
                     ).grid(row=2, column=0, sticky='ew', padx=18, pady=(8, 0))

    state = {'ok': False}

    def _ok():
        state['ok'] = True
        dlg.destroy()

    bar = ctk.CTkFrame(box, fg_color='transparent')
    bar.grid(row=9, column=0, sticky='e', padx=18, pady=16)
    make_button(bar, cancel_text, dlg.destroy, kind='ghost', width=84).pack(side='left')
    make_button(bar, ok_text, _ok, kind='danger' if danger else 'primary',
                width=84).pack(side='left', padx=(8, 0))
    _bind_keys(dlg, _ok)
    parent.wait_window(dlg)
    return state['ok']


def ask_number(parent, title, message='', init='', lo=None, hi=None, unit=''):
    """数值输入对话框 -> int/float，取消返回 None

    回车确定、Esc 取消、打开即全选，方便连改多个格子。
    """
    dlg, box = _dialog_shell(parent, title, 400, 220)
    if message:
        ctk.CTkLabel(box, text=message, font=F.get('small'), text_color=C['text3'],
                     anchor='w', justify='left', wraplength=340
                     ).grid(row=1, column=0, sticky='ew', padx=18)

    var = ctk.StringVar(value=str(init))
    ent = ctk.CTkEntry(box, textvariable=var, height=36, font=F.get('body'),
                       fg_color=C['surface2'], border_color=C['border2'], corner_radius=7)
    ent.grid(row=2, column=0, sticky='ew', padx=18, pady=(12, 0))

    hint = ctk.CTkLabel(box, text='', font=F.get('tiny'), text_color=C['danger'], anchor='w')
    hint.grid(row=3, column=0, sticky='ew', padx=18, pady=(3, 0))
    bits = []
    if lo is not None:
        bits.append('最小 %s' % lo)
    if hi is not None:
        bits.append('最大 %s' % hi)
    if unit:
        bits.append('单位 %s' % unit)
    if bits:
        hint.configure(text=' · '.join(bits), text_color=C['text3'])

    state = {'v': None}

    def _ok():
        raw = var.get().strip().replace(',', '').replace('，', '')
        if not raw:
            hint.configure(text='请输入一个数字', text_color=C['danger'])
            return
        try:
            val = float(raw) if ('.' in raw or 'e' in raw.lower()) else int(raw)
        except ValueError:
            hint.configure(text='这不是一个有效数字', text_color=C['danger'])
            return
        if lo is not None and val < lo:
            hint.configure(text='不能小于 %s' % lo, text_color=C['danger'])
            return
        if hi is not None and val > hi:
            hint.configure(text='不能大于 %s' % hi, text_color=C['danger'])
            return
        state['v'] = val
        dlg.destroy()

    bar = ctk.CTkFrame(box, fg_color='transparent')
    bar.grid(row=9, column=0, sticky='e', padx=18, pady=16)
    make_button(bar, '取消', dlg.destroy, kind='ghost', width=84).pack(side='left')
    make_button(bar, '确定', _ok, kind='primary', width=84).pack(side='left', padx=(8, 0))
    _bind_keys(dlg, _ok)
    ent.focus_set()
    ent.select_range(0, 'end')
    parent.wait_window(dlg)
    return state['v']


# ------------------------------------------------------------------ 指标卡 / 表头 / 开关行

class StatCard(ctk.CTkFrame):
    """小指标卡：标题 + 大号数字 + 注解，三行结构固定，并排时高度自然对齐"""

    def __init__(self, master, title, value='—', sub='', wrap=240, **kw):
        kw.setdefault('fg_color', C['surface'])
        kw.setdefault('corner_radius', RADIUS)
        kw.setdefault('border_width', 1)
        kw.setdefault('border_color', C['border'])
        super().__init__(master, **kw)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text=title, font=F.get('small'), text_color=C['text2'],
                     anchor='w').grid(row=0, column=0, sticky='ew',
                                      padx=CARD_PAD, pady=(13, 0))
        self._value = ctk.CTkLabel(self, text=value, font=F.get('num'),
                                   text_color=C['text'], anchor='w')
        self._value.grid(row=1, column=0, sticky='ew', padx=CARD_PAD, pady=(1, 0))
        self._sub = ctk.CTkLabel(self, text=sub, font=F.get('tiny'),
                                 text_color=C['text3'], anchor='w', justify='left',
                                 wraplength=wrap)
        self._sub.grid(row=2, column=0, sticky='ew', padx=CARD_PAD, pady=(3, 13))

    def set(self, value, sub=''):
        self._value.configure(text=str(value))
        # 空串会让这一行塌掉，三张卡就不一般高了 —— 用空格占位
        self._sub.configure(text=sub if sub else ' ')


class TableHeader(ctk.CTkFrame):
    """表头行。weights 要和下面数据行的 grid 权重用同一套，否则列会错位"""

    def __init__(self, master, columns, weights=None, **kw):
        kw.setdefault('fg_color', 'transparent')
        super().__init__(master, **kw)
        w = list(weights) if weights else [1] * len(columns)
        while len(w) < len(columns):
            w.append(1)
        for i, col in enumerate(columns):
            self.grid_columnconfigure(i, weight=w[i], minsize=0)
            ctk.CTkLabel(self, text=col, font=F.get('tiny'), text_color=C['text3'],
                         anchor='w').grid(row=0, column=i, sticky='ew', padx=(0, 8))


class ToggleRow(ctk.CTkFrame):
    """一行开关：左边名称（+ 可选说明），右边拨动开关

    command 收到的是切换「之后」的布尔值。
    """

    def __init__(self, master, label, note='', value=False, command=None,
                 wrap=680, **kw):
        kw.setdefault('fg_color', 'transparent')
        super().__init__(master, **kw)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text=label, font=F.get('body'), text_color=C['text'],
                     anchor='w').grid(row=0, column=0, sticky='ew', pady=(7, 0))
        if note:
            ctk.CTkLabel(self, text=note, font=F.get('tiny'), text_color=C['text3'],
                         anchor='w', justify='left', wraplength=wrap
                         ).grid(row=1, column=0, sticky='ew', pady=(1, 5))
        else:
            ctk.CTkFrame(self, fg_color='transparent', height=7,
                         width=1).grid(row=1, column=0)

        self.var = ctk.BooleanVar(value=bool(value))
        self.sw = ctk.CTkSwitch(
            self, text='', variable=self.var, width=46,
            switch_width=40, switch_height=21,
            progress_color=C['accent'], fg_color=C['track_off'],
            button_color='#FFFFFF', button_hover_color='#FFFFFF',
            command=(lambda: command(self.var.get())) if command else None)
        self.sw.grid(row=0, column=1, rowspan=2, sticky='e', padx=(12, 0))
