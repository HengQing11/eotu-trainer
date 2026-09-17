# -*- coding: utf-8 -*-
"""黑色主题 —— 所有颜色、字号、间距的唯一出处

设计原则：深色底 + 层次靠明度差 + 0.5px 细边框 + 克制的留白。
不堆装饰，靠层次和留白把信息分清。
"""
import customtkinter as ctk

# ------------------------------------------------------------------ 颜色
C = {
    'window': '#17191D',        # 窗口底色
    'surface': '#1E2228',       # 卡片
    'surface2': '#242932',      # 次级区块（指标卡、输入框底）
    'surface3': '#2A303A',      # 悬停
    'border': '#2E3440',        # 细边框
    'border2': '#3A4150',       # 强调边框 / 输入框

    'text': '#E6E9EF',          # 主文字
    'text2': '#9AA3B2',         # 次要文字
    'text3': '#6B7280',         # 提示文字

    'accent': '#2FBF8F',        # 主色（青绿）
    'accent_h': '#27A67C',      # 主色悬停
    'accent_soft': '#123B2E',   # 主色浅底
    'accent_text': '#7FE0C0',

    'danger': '#E24B4A',
    'danger_h': '#C43B3B',
    'danger_soft': '#3A1B1E',

    'warn': '#E0A23C',
    'warn_soft': '#3A2E17',

    'ok': '#2FBF8F',
    'ok_soft': '#123B2E',

    'info': '#4A8DDC',
    'info_soft': '#16283D',

    'track_off': '#3A4150',     # 开关关闭时的轨道
}

# ------------------------------------------------------------------ 字体
FAMILY = 'Microsoft YaHei UI'


def _font(size, weight='normal'):
    return ctk.CTkFont(family=FAMILY, size=size, weight=weight)


class F:
    """字体集合（延迟创建，必须在 CTk 根窗口之后用）"""
    _cache = {}

    @classmethod
    def get(cls, key):
        if key in cls._cache:
            return cls._cache[key]
        spec = {
            'h1': (20, 'bold'),      # 窗口标题
            'h2': (15, 'bold'),      # 页面标题
            'h3': (13, 'bold'),      # 卡片标题
            'body': (13, 'normal'),
            'body_b': (13, 'bold'),
            'small': (12, 'normal'),
            'tiny': (11, 'normal'),
            'num': (22, 'bold'),     # 指标数字
            'mono': (12, 'normal'),
        }.get(key, (13, 'normal'))
        cls._cache[key] = _font(*spec)
        return cls._cache[key]


def clear_fonts():
    F._cache.clear()


# ------------------------------------------------------------------ 尺寸
PAD = 18            # 页面外边距
GAP = 10            # 元素间距
CARD_PAD = 16       # 卡片内边距
RADIUS = 10
ROW_H = 34
BTN_H = 32
TOP_H = 52
TAB_H = 40

RISK_COLOR = {
    'low': ('ok', '安全'),
    'medium': ('warn', '注意'),
    'high': ('danger', '高危'),
}
