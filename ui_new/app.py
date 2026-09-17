# -*- coding: utf-8 -*-
"""蚁国修改器 v3 —— PySide6 + QML 重做界面（Clash 风格）

只重做"壳"：全部游戏逻辑复用 gui/core/*（memscan 定位、官方作弊开关、
蚁皇浆运行时补满、存档清除加点、备份策略），与旧版 gui/ 并存。

跑起来：python ui_new/app.py
自检：  python ui_new/app.py --selftest
打包：  python scripts/build_exe_qt.py
"""
import os
import struct
import sys
import threading
from threading import Event, Lock

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MOD_DIR not in sys.path:
    sys.path.insert(0, MOD_DIR)

from PySide6.QtCore import Property, QObject, Signal, Slot  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from gui.core import actions, cheats, gameproc, gvas, jelly, paths, saves  # noqa: E402

VERSION = '3.0.0'

# ====================================================================== QML
QML = r'''
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: win
    width: 1160; height: 720
    minimumWidth: 1000; minimumHeight: 620
    visible: true
    title: "地下蚁国 · 修改器"
    color: "transparent"
    flags: Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window

    readonly property color bg0: "#0c0f16"
    readonly property color bg1: "#12161f"
    readonly property color cardC: "#161b27"
    readonly property color cardHi: "#1b2231"
    readonly property color line: "#232b3d"
    readonly property color txt: "#e6eaf2"
    readonly property color txt2: "#9aa2b5"
    readonly property color txt3: "#5b6478"
    readonly property color a1: "#2dd4bf"
    readonly property color a2: "#38bdf8"
    readonly property color danger: "#f43f5e"
    readonly property color ok: "#34d399"

    property var g: backend.game

    Rectangle {
        id: shell
        anchors.fill: parent
        radius: 14
        color: bg0
        border.color: line
        border.width: 1
        gradient: Gradient {
            GradientStop { position: 0; color: bg1 }
            GradientStop { position: 1; color: bg0 }
        }
        Rectangle {
            x: parent.width * 0.42; y: -200
            width: 920; height: 480; radius: 240
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.rgba(a1.r, a1.g, a1.b, 0.10) }
                GradientStop { position: 1; color: Qt.rgba(a2.r, a2.g, a2.b, 0.03) } }
        }

        // ---------------- 顶栏 ----------------
        Item {
            id: topbar
            height: 58
            anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
            MouseArea {
                anchors.fill: parent
                onPressed: win.startSystemMove()
            }
            Row {
                spacing: 10
                anchors.left: parent.left; anchors.leftMargin: 22
                anchors.verticalCenter: parent.verticalCenter
                Rectangle {
                    width: 12; height: 12; radius: 6; anchors.verticalCenter: parent.verticalCenter
                    gradient: Gradient { orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: a1 }
                        GradientStop { position: 1; color: a2 } }
                }
                Text { text: "地下蚁国 · 修改器"; color: txt; font.pixelSize: 16
                       font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
            }
            Row {
                spacing: 8
                anchors.right: parent.right; anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                Rectangle { width: 8; height: 8; radius: 4
                            color: g.running ? ok : txt3
                            anchors.verticalCenter: parent.verticalCenter
                            Behavior on color { ColorAnimation { duration: 200 } } }
                Text { text: g.text; color: txt2; font.pixelSize: 13
                       anchors.verticalCenter: parent.verticalCenter }
                Item { width: 6; height: 1 }
                WinBtn { label: "—"; onClicked: win.showMinimized() }
                WinBtn { label: "✕"; danger: true; onClicked: Qt.quit() }
            }
        }

        // ---------------- 内容 ----------------
        Column {
            anchors.top: topbar.bottom
            anchors.left: parent.left; anchors.right: parent.right
            anchors.margins: 26
            spacing: 16

            // ============ 卡片 1：关卡作弊 ============
            Card {
                width: parent.width
                idx: 0
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 18
                    Column { Layout.preferredWidth: 168; spacing: 6
                        Text { text: "关卡作弊"; color: txt; font.pixelSize: 18
                               font.weight: Font.DemiBold }
                        Text { text: g.connected ? "已连接本关 · 判定级生效"
                                                 : "进入关卡后自动连接"
                               ; color: g.connected ? ok : txt3; font.pixelSize: 12
                               Behavior on color { ColorAnimation { duration: 300 } } }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2; columnSpacing: 30; rowSpacing: 16
                        CheatToggle { label: "无限资源"; fkey: "infinite" }
                        CheatToggle { label: "免费孵化"; fkey: "freehatch" }
                        CheatToggle { label: "秒建";     fkey: "instant_build" }
                        CheatToggle { label: "秒挖";     fkey: "instant_dig" }
                    }
                }
            }

            // ============ 卡片 2：蚁皇浆 ============
            Card {
                width: parent.width
                idx: 1
                RowLayout {
                    Layout.fillWidth: true; spacing: 20
                    Column { spacing: 4; Layout.fillWidth: true
                        Text { text: "蚁皇浆 · 运行时补满"; color: txt; font.pixelSize: 18
                               font.weight: Font.DemiBold }
                        Text { text: "需游戏开着 · 写入即生效并随游戏存盘"
                               ; color: txt3; font.pixelSize: 12 }
                        Text { text: backend.jelly; color: txt; font.pixelSize: 32
                               font.weight: Font.Bold; font.letterSpacing: 1 }
                    }
                    Column { Layout.alignment: Qt.AlignVCenter; spacing: 8
                        GradButton { text: "补满到 20 亿"; onClicked: backend.refill() }
                        Text { text: backend.jellyNote; color: backend.jellyOk ? ok : danger
                               font.pixelSize: 12; visible: backend.jellyNote !== ""
                               Layout.preferredWidth: 230; wrapMode: Text.WordWrap
                               Behavior on color { ColorAnimation { duration: 200 } } }
                    }
                }
            }

            // ============ 卡片 3：清除加点 ============
            Card {
                width: parent.width
                idx: 2
                RowLayout {
                    Layout.fillWidth: true; spacing: 20
                    Column { spacing: 8; Layout.fillWidth: true
                        Text { text: "清除加点"; color: txt; font.pixelSize: 18
                               font.weight: Font.DemiBold }
                        Text { text: "一键清零所选存档的全部加点 · 需完全退出游戏 · 蚁皇浆不退还"
                               ; color: txt3; font.pixelSize: 12 }
                        Row { spacing: 10
                            Text { text: "存档"; color: txt3; font.pixelSize: 13
                                   anchors.verticalCenter: parent.verticalCenter }
                            SaveCombo { width: 170 }
                        }
                    }
                    Column { Layout.alignment: Qt.AlignVCenter; spacing: 8
                        DangerButton { text: "清除全部加点"; onClicked: backend.clearAddons() }
                        Text { text: backend.clearNote; color: backend.clearOk ? ok : danger
                               font.pixelSize: 12; visible: backend.clearNote !== ""
                               Layout.preferredWidth: 240; wrapMode: Text.WordWrap
                               Behavior on color { ColorAnimation { duration: 200 } } }
                    }
                }
            }
        }
    }

    // ==================================================== 组件
    component WinBtn: Rectangle {
        id: wb
        property string label: ""
        property bool danger: false
        signal clicked()
        width: 32; height: 28; radius: 6
        color: marea.containsMouse ? (danger ? "#e5484d" : cardHi) : "transparent"
        Behavior on color { ColorAnimation { duration: 120 } }
        Text { text: wb.label
               color: marea.containsMouse && wb.danger ? "#fff" : txt2
               anchors.centerIn: parent; font.pixelSize: 12 }
        MouseArea { id: marea; anchors.fill: parent; hoverEnabled: true
                    onClicked: wb.clicked() }
    }

    component Card: Rectangle {
        id: card
        property int idx: 0
        default property alias content: body.data
        radius: 16
        color: cardC
        border.color: hma.containsMouse ? Qt.rgba(a1.r, a1.g, a1.b, 0.30) : line
        border.width: 1
        implicitHeight: body.implicitHeight + 40
        Behavior on border.color { ColorAnimation { duration: 180 } }
        ColumnLayout {
            id: body
            x: 22; y: 20
            width: card.width - 44
        }
        opacity: 0
        SequentialAnimation on opacity {
            running: true
            PauseAnimation { duration: card.idx * 90 }
            NumberAnimation { from: 0; to: 1; duration: 380
                              easing.type: Easing.OutCubic }
        }
        MouseArea { id: hma; anchors.fill: parent; hoverEnabled: true
                    acceptedButtons: Qt.NoButton }
    }

    component CheatToggle: Row {
        id: ct
        property string label: ""
        property string fkey: ""
        spacing: 12
        Text { text: label; color: txt; font.pixelSize: 14
               anchors.verticalCenter: parent.verticalCenter }
        Item {
            id: sw
            width: 46; height: 26
            anchors.verticalCenter: parent.verticalCenter
            property bool on: {
                var f = g.flags
                return f ? !!f[ct.fkey] : false
            }
            Rectangle {
                anchors.fill: parent; radius: 13
                color: sw.on ? Qt.rgba(a1.r, a1.g, a1.b, 0.22) : "#202736"
                border.color: sw.on ? a1 : line
                Behavior on color { ColorAnimation { duration: 180 } }
                Behavior on border.color { ColorAnimation { duration: 180 } }
            }
            Rectangle {
                x: sw.on ? sw.width - width - 3 : 3
                anchors.verticalCenter: parent.verticalCenter
                width: 20; height: 20; radius: 10
                gradient: Gradient { orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: a1 }
                    GradientStop { position: 1; color: a2 } }
                Behavior on x { NumberAnimation { duration: 180
                                  easing.type: Easing.OutCubic } }
            }
            MouseArea { anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.setFlag(ct.fkey, !sw.on) }
        }
    }

    component GradButton: Rectangle {
        id: gb
        property string text: ""
        signal clicked()
        width: gbl.implicitWidth + 46; height: 42; radius: 10
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0; color: a1 }
            GradientStop { position: 1; color: a2 } }
        scale: gba.pressed ? 0.96 : 1.0
        Behavior on scale { NumberAnimation { duration: 110 } }
        Rectangle { anchors.fill: parent; radius: parent.radius; color: "#fff"
                    opacity: gba.containsMouse ? 0.12 : 0
                    Behavior on opacity { NumberAnimation { duration: 140 } } }
        Text { id: gbl; text: gb.text; color: "#07131a"; font.pixelSize: 14
               font.weight: Font.DemiBold; anchors.centerIn: parent }
        MouseArea { id: gba; anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor; onClicked: gb.clicked() }
    }

    component DangerButton: Rectangle {
        id: db
        property string text: ""
        signal clicked()
        width: dbl.implicitWidth + 46; height: 42; radius: 10
        color: dba.containsMouse ? "#ff5c77" : danger
        Behavior on color { ColorAnimation { duration: 140 } }
        scale: dba.pressed ? 0.96 : 1.0
        Behavior on scale { NumberAnimation { duration: 110 } }
        Text { id: dbl; text: db.text; color: "#fff"; font.pixelSize: 14
               font.weight: Font.DemiBold; anchors.centerIn: parent }
        MouseArea { id: dba; anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor; onClicked: db.clicked() }
    }

    component SaveCombo: ComboBox {
        id: sc
        height: 36
        font.pixelSize: 13
        model: backend.saves
        textRole: "label"
        currentIndex: backend.saveIndex
        contentItem: Text {
            text: sc.count ? sc.displayText : "（没找到存档）"
            color: txt; font.pixelSize: 13
            verticalAlignment: Text.AlignVCenter
            leftPadding: 12; rightPadding: 28
        }
        background: Rectangle {
            radius: 8; color: "#1d2432"
            border.color: sc.hovered || sc.popup.visible ? a1 : line
            Behavior on border.color { ColorAnimation { duration: 140 } }
        }
        indicator: Text {
            text: sc.popup.visible ? "▴" : "▾"; color: txt3
            anchors.right: parent.right; anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
        }
        delegate: ItemDelegate {
            id: dlg
            width: sc.width
            highlighted: sc.highlightedIndex === index
            contentItem: Text {
                text: modelData ? modelData.label : ""
                color: txt; font.pixelSize: 13
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                color: dlg.highlighted ? cardHi : "transparent"; radius: 6 }
        }
        popup: Popup {
            y: sc.height + 4
            width: sc.width
            padding: 4
            background: Rectangle { color: "#171d2a"; radius: 10
                                    border.color: line; border.width: 1 }
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: sc.popup.visible ? sc.delegateModel : null
                currentIndex: sc.highlightedIndex
            }
        }
        onActivated: (i) => backend.setSave(i)
    }
}
'''


# ====================================================================== 后端
class Backend(QObject):
    gameChanged = Signal()
    jellyChanged = Signal()
    jellyNoteChanged = Signal()
    clearNoteChanged = Signal()
    savesChanged = Signal()

    def __init__(self):
        super().__init__()
        self.lock = Lock()
        self.proc = None
        self.base = None
        self.grid = None
        self.colony = None
        self._stop = Event()
        self._game = dict(running=False, text='检测中…', connected=False,
                          res=0, cap=0, flags={})
        self._jelly = '—'
        self._jnote, self._jok = '', True
        self._cnote, self._cok = '', True
        self._saves = []
        cfg = paths.load_config()
        self._cur = cfg.get('save_file') or 'Colony1.sav'
        self._max_bak = cfg.get('max_backups', 5)
        # 期望状态表：用户的点击先落这里，循环按它重申（修"点击被旧状态覆盖"竞态）
        self.wants = {}

    # ---------------- Q_PROPERTY（类属性）----------------
    def _get_game(self):
        return self._game

    def _get_jelly(self):
        return self._jelly

    def _get_jnote(self):
        return self._jnote

    def _get_jok(self):
        return self._jok

    def _get_cnote(self):
        return self._cnote

    def _get_cok(self):
        return self._cok

    def _get_saves(self):
        return self._saves

    def _get_saveindex(self):
        return next((i for i, s in enumerate(self._saves)
                     if s['file'] == self._cur), 0)

    game = Property('QVariant', _get_game, notify=gameChanged)
    jelly = Property(str, _get_jelly, notify=jellyChanged)
    jellyNote = Property(str, _get_jnote, notify=jellyNoteChanged)
    jellyOk = Property(bool, _get_jok, notify=jellyNoteChanged)
    clearNote = Property(str, _get_cnote, notify=clearNoteChanged)
    clearOk = Property(bool, _get_cok, notify=clearNoteChanged)
    saves = Property('QVariantList', _get_saves, notify=savesChanged)
    saveIndex = Property(int, _get_saveindex, notify=savesChanged)

    # ---------------- 内部 ----------------
    def _set_game(self, **kw):
        self._game.update(kw)
        self.gameChanged.emit()

    def _load_saves(self):
        self._saves = [dict(label=s.label, file=s.file)
                       for s in saves.list_saves()]
        if self._saves and not any(s['file'] == self._cur for s in self._saves):
            self._cur = self._saves[0]['file']
            cfg = paths.load_config()
            cfg['save_file'] = self._cur
            paths.save_config(cfg)
        self.savesChanged.emit()

    # ---------------- 给 QML 的槽 ----------------
    @Slot(str, bool)
    def setFlag(self, key, val):
        with self.lock:
            if not self._connect():
                return
            try:
                self.wants[key] = bool(val)
                cheats.apply_flags(self.proc, self.grid, self.wants)
                # 立即回读并推送，UI 不用等下一秒
                st = cheats.read_status(self.proc, self.grid)
                self._set_game(connected=True, res=st['res'],
                               cap=st['cap'], flags=st['flags'])
            except Exception:                                    # noqa: BLE001
                self._close()

    @Slot()
    def refill(self):
        def work():
            with self.lock:
                try:
                    if not self._connect():
                        self._jnote, self._jok = \
                            '✗ 游戏没开或不在关卡里', False
                        self.jellyNoteChanged.emit()
                        return
                    colony = cheats.find_play_colony(self.proc, self.base)
                    if colony is None:
                        self._jnote, self._jok = \
                            '✗ 没找到你的殖民地（不猜不乱写）', False
                        self.jellyNoteChanged.emit()
                        return
                    cur = cheats.read_jelly(self.proc, colony)
                    ok, after = cheats.refill_jelly(self.proc, colony,
                                                    self.base)
                    self.colony = colony if ok else None
                    if ok:
                        self._jnote = '✓ %s → 20 亿 · 回读一致' \
                            % '{:,}'.format(cur or 0)
                        self._jok = True
                        self._jelly = '{:,}'.format(cheats.JELLY_CAP)
                        self.jellyChanged.emit()
                    else:
                        self._jnote = '✗ 写入后回读不符（%s）' \
                            % '{:,}'.format(after or 0)
                        self._jok = False
                    self.jellyNoteChanged.emit()
                except Exception as e:                           # noqa: BLE001
                    self._jnote, self._jok = '✗ %s' % str(e)[:40], False
                    self.jellyNoteChanged.emit()
        threading.Thread(target=work, daemon=True).start()

    @Slot(int)
    def setSave(self, idx):
        if not (0 <= idx < len(self._saves)):
            return
        self._cur = self._saves[idx]['file']
        cfg = paths.load_config()
        cfg['save_file'] = self._cur
        paths.save_config(cfg)
        self._cnote, self._cok = '', True
        self.clearNoteChanged.emit()
        self.savesChanged.emit()

    @Slot()
    def clearAddons(self):
        def work():
            try:
                if gameproc.game_running() is True:
                    self._cnote, self._cok = \
                        '✗ 游戏正在运行 —— 请先完全退出游戏再清除', False
                    self.clearNoteChanged.emit()
                    return
                sf = gvas.SaveFile(actions.save_path(self._cur))
                ads = jelly.addons(sf)
                if not ads:
                    self._cnote, self._cok = '这个存档当前没有任何加点', True
                    self.clearNoteChanged.emit()
                    return
                n_items, total = len(ads), sum(a[1] for a in ads)
                for f, _pts, _cost in ads:
                    sf.set_int(f.name, 0)

                def verify(vp):
                    left = jelly.addons(gvas.SaveFile(vp))
                    return (not left,
                            '全部 %d 项已归零（原共 %d 点）' % (n_items, total)
                            if not left else '剩余未清 %d 项' % len(left))

                r = actions.commit(sf, 'clearAddons', verify=verify)
                self._cnote = ('✓ ' if r.ok else '✗ ') + \
                    r.msg.replace('\n', ' ')
                self._cok = r.ok
            except Exception as e:                               # noqa: BLE001
                self._cnote, self._cok = '✗ %s' % str(e)[:60], False
            self.clearNoteChanged.emit()
        threading.Thread(target=work, daemon=True).start()

    # ---------------- 连接管理 ----------------
    def _grid_ok(self):
        """身份核对：grid 处的 vtable 还是不是 UGTileGrid？

        换关/重开后游戏会新建网格对象，旧地址可能被释放或复用 ——
        不核对就会"界面显示开着、写入落在死地址"（= 显示 ON 但毫无效果）。
        """
        if self.proc is None or self.grid is None:
            return False
        h = self.proc.read(self.grid, 8)
        if not h or len(h) < 8:
            return False
        try:
            return struct.unpack('<Q', h)[0] - self.base == cheats.GRID_RVA
        except (TypeError, ValueError):
            return False

    def _connect(self):
        if self.proc is not None and self.grid is not None:
            if self._grid_ok():          # 每次进循环都验一遍身份
                return True
            self.grid = None             # 身份失效 → 重新定位
        proc, base = cheats.connect()
        if proc is None:
            self._close()
            return False
        if self.proc is None or self.base != base:
            self.proc, self.base = proc, base
        self.grid = cheats.find_grid(proc, base)
        if self.grid is None:
            self._close()
            return False
        self.colony = None               # 网格都换了，浆的锚点也要重找
        return True

    def _close(self):
        try:
            if self.proc is not None:
                self.proc.close()
        except Exception:                                        # noqa: BLE001
            pass
        self.proc = None
        self.base = None
        self.grid = None
        self.colony = None

    def _loop(self):
        tick = 0
        while not self._stop.is_set():
            with self.lock:
                try:
                    # 每 0.3s 按"期望状态表"重申一遍 —— 游戏实测每 ~0.4s 会把
                    # InfinateResources 写回 1，所以 OFF 也必须持续按住
                    connected = self._connect()
                    if connected:
                        cheats.apply_flags(self.proc, self.grid, self.wants)
                        tick += 1
                        if tick % 4 == 1:
                            # 稍重的读取（资源/浆/殖民地）降频到 ~1.2s 一次
                            st = cheats.read_status(self.proc, self.grid)
                            if self.colony is None:
                                self.colony = cheats.find_play_colony(
                                    self.proc, self.base)
                            jv = (cheats.read_jelly(self.proc, self.colony)
                                  if self.colony is not None else None)
                            if jv is not None:
                                self._jelly = '{:,}'.format(int(jv))
                                self.jellyChanged.emit()
                            state, text = gameproc.status()
                            self._set_game(running=(state == 'running'),
                                           text=text, connected=True,
                                           res=st['res'], cap=st['cap'],
                                           flags=st['flags'])
                    else:
                        self._set_game(running=gameproc.game_running() is True,
                                       text='进入关卡后自动连接',
                                       connected=False, flags={})
                except Exception:                                # noqa: BLE001
                    self._close()
                    self._set_game(connected=False, flags={})
            self._stop.wait(0.3)

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        """退出前收尾：把 4 个作弊开关全部关掉（用户要求：关工具=全关）"""
        self._stop.set()
        with self.lock:
            try:
                # 句柄没了就现连一次；连不上（游戏没开/在菜单）就只能放弃
                if self.proc is None:
                    proc, base = cheats.connect()
                    if proc is None:
                        return
                    self.proc, self.base = proc, base
                    self.grid = cheats.find_grid(proc, base)
                if self.grid is not None and self._grid_ok():
                    cheats.apply_flags(self.proc, self.grid,
                                       {k: False
                                        for k, _o, _c, _e in cheats.FLAG_DEFS})
                    st = cheats.read_status(self.proc, self.grid)
                    print('退出清理：flags =',
                          ''.join('1' if st['flags'][k] else '0'
                                  for k, _o, _c, _e in cheats.FLAG_DEFS),
                          flush=True)
            except Exception:                                    # noqa: BLE001
                pass
            self._close()


# ====================================================================== 入口
def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName('地下蚁国 · 修改器')
    backend = Backend()
    eng = QQmlApplicationEngine()
    eng.rootContext().setContextProperty('backend', backend)
    eng.loadData(QML.encode('utf-8'))
    if not eng.rootObjects():
        print('QML 加载失败', file=sys.stderr)
        return 1
    backend._load_saves()
    backend.start()
    ret = app.exec()
    backend.stop()
    return ret


def selftest():
    lines = []

    def add(k, v):
        lines.append('%-14s %s' % (k, v))

    add('版本', VERSION)
    add('打包运行', '是' if getattr(sys, 'frozen', False) else '否')
    sv = saves.list_saves()
    add('存档 %d 个' % len(sv), '、'.join(s.label for s in sv) or '（没找到）')
    add('游戏进程', gameproc.status()[1])
    add('备份上限', '%d 份' % self_cfg_max())
    try:
        cfg = paths.load_config()
        sf = gvas.SaveFile(actions.save_path(cfg.get('save_file')
                                             or 'Colony1.sav'))
        ads = jelly.addons(sf)
        add('加点清单', '%d 项 / 共 %d 点' % (len(ads), sum(a[1] for a in ads)))
    except Exception as e:                                       # noqa: BLE001
        add('加点清单', '失败：%s' % e)
    # 打包态 MOD_DIR 指向临时解压目录，selftest.txt 要写到 exe 同级
    app_dir = (os.path.dirname(sys.executable)
               if getattr(sys, 'frozen', False) else MOD_DIR)
    out = os.path.join(app_dir, 'selftest.txt')
    try:
        with open(out, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    except OSError:
        out = '(写不进去)'
    try:
        print('\n'.join(lines))
        print('已写入：%s' % out)
    except Exception:                                            # noqa: BLE001
        pass
    return 0


def self_cfg_max():
    return paths.load_config().get('max_backups', 5)


if __name__ == '__main__':
    if '--selftest' in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
