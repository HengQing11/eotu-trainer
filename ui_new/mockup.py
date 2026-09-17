# -*- coding: utf-8 -*-
"""新界面效果图（纯视觉，假数据，不连游戏）—— Clash 风格

看效果用：python ui_new/mockup.py
确认后才把真逻辑（core/）接进来。
"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickStyle

QML = r'''
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

ApplicationWindow {
    id: win
    width: 1180; height: 760
    visible: true
    title: "地下蚁国 · 修改器"
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.Window

    // ------------------------------------------------ 配色（Clash 风格）
    readonly property color bg0:      "#0c0f16"
    readonly property color bg1:      "#11151f"
    readonly property color card:     "#161b27"
    readonly property color cardHi:   "#1b2231"
    readonly property color line:     "#232b3d"
    readonly property color txt:      "#e6eaf2"
    readonly property color txt2:     "#8b93a7"
    readonly property color txt3:     "#565f75"
    readonly property color a1:       "#2dd4bf"   // 青绿
    readonly property color a2:       "#38bdf8"   // 天蓝
    readonly property color danger:   "#f43f5e"
    readonly property color ok:       "#34d399"

    // 拖动窗口
    function moveWin(mouse) {
        win.x += mouse.x - win._px; win.y += mouse.y - win._py
    }

    Rectangle {
        id: shell
        anchors.fill: parent
        radius: 14
        color: bg0
        border.color: line
        border.width: 1

        // 背景渐变 + 右上角氛围光
        gradient: Gradient {
            GradientStop { position: 0; color: bg1 }
            GradientStop { position: 1; color: bg0 }
        }
        Rectangle {
            x: parent.width * 0.45; y: -180
            width: 900; height: 460; radius: 230
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.rgba(a1.r, a1.g, a1.b, 0.10) }
                GradientStop { position: 1; color: Qt.rgba(a2.r, a2.g, a2.b, 0.04) } }
        }

        // ------------------------------------------------ 顶栏
        Item {
            id: topbar
            height: 56
            anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right

            MouseArea {  // 拖动
                anchors.fill: parent
                onPressed: (m) => { win._px = m.x; win._py = m.y }
                onPositionChanged: (m) => { if (win._px >= 0) win.moveWin(m) }
                onReleased: win._px = -1
                onDoubleClicked: win.showMinimized()
            }
            property real _px: -1

            Row {
                spacing: 10
                anchors.left: parent.left; anchors.leftMargin: 22
                anchors.verticalCenter: parent.verticalCenter
                Rectangle {   // logo 圆点
                    width: 12; height: 12; radius: 6; anchors.verticalCenter: parent.verticalCenter
                    gradient: Gradient { orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: a1 } GradientStop { position: 1; color: a2 } }
                }
                Text { text: "地下蚁国 · 修改器"; color: txt; font.pixelSize: 16; font.weight: Font.DemiBold
                       anchors.verticalCenter: parent.verticalCenter }
            }

            Row {
                spacing: 8
                anchors.right: parent.right; anchors.rightMargin: 22
                anchors.verticalCenter: parent.verticalCenter
                Rectangle { width: 8; height: 8; radius: 4; color: ok; anchors.verticalCenter: parent.verticalCenter }
                Text { text: "游戏运行中"; color: txt2; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                Rectangle { width: 1; height: 16; color: line; anchors.verticalCenter: parent.verticalCenter; anchors.leftMargin: 6 }
                Row {  // 最小化 / 关闭
                    spacing: 4; anchors.verticalCenter: parent.verticalCenter
                    Rectangle {
                        width: 30; height: 26; radius: 6; color: mra.containsMouse ? cardHi : "transparent"
                        Text { text: "—"; color: txt2; anchors.centerIn: parent; font.pixelSize: 12 }
                        MouseArea { id: mra; anchors.fill: parent; onClicked: win.showMinimized() }
                    }
                    Rectangle {
                        width: 30; height: 26; radius: 6; color: mrc.containsMouse ? "#e5484d" : "transparent"
                        Text { text: "✕"; color: mrc.containsMouse ? "#fff" : txt2; anchors.centerIn: parent; font.pixelSize: 12 }
                        MouseArea { id: mrc; anchors.fill: parent; onClicked: Qt.quit() }
                    }
                }
            }
        }

        // ------------------------------------------------ 内容
        Column {
            anchors.top: topbar.bottom
            anchors.left: parent.left; anchors.right: parent.right
            anchors.margins: 26
            anchors.topMargin: 4
            spacing: 18

            // ================= 卡片 1：关卡作弊 =================
            Card {
                width: parent.width
                RowLayout {
                    width: parent.width
                    spacing: 0
                    Column { Layout.alignment: Qt.AlignTop; Layout.preferredWidth: 170; spacing: 6
                        Text { text: "关卡作弊"; color: txt; font.pixelSize: 18; font.weight: Font.DemiBold }
                        Text { text: "官方调试开关\n判定级生效"; color: txt3; font.pixelSize: 12; lineHeight: 1.3 }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2; columnSpacing: 26; rowSpacing: 14
                        CheatToggle { label: "无限资源"; on0: true }
                        CheatToggle { label: "免费孵化" }
                        CheatToggle { label: "秒建" }
                        CheatToggle { label: "秒挖" }
                    }
                }
            }

            // ================= 卡片 2：蚁皇浆 =================
            Card {
                width: parent.width
                RowLayout {
                    width: parent.width; spacing: 20
                    Column { spacing: 6; Layout.fillWidth: true
                        Text { text: "蚁皇浆 · 运行时补满"; color: txt; font.pixelSize: 18; font.weight: Font.DemiBold }
                        Text { text: "需游戏开着 · 写入即生效并随游戏存盘"; color: txt3; font.pixelSize: 12 }
                        Text { text: "2,000,000,000"; color: txt; font.pixelSize: 34; font.weight: Font.Bold
                               font.letterSpacing: 1 }
                    }
                    GradButton {
                        Layout.alignment: Qt.AlignVCenter
                        text: "补满到 20 亿"
                    }
                }
            }

            // ================= 卡片 3：清除加点 =================
            Card {
                width: parent.width
                RowLayout {
                    width: parent.width; spacing: 20
                    Column { spacing: 6; Layout.fillWidth: true
                        Text { text: "清除加点"; color: txt; font.pixelSize: 18; font.weight: Font.DemiBold }
                        Text { text: "一键清零 · 需完全退出游戏 · 蚁皇浆不退还 · 自动备份（保留 5 份）"
                               ; color: txt3; font.pixelSize: 12 }
                        Row { spacing: 8
                            Text { text: "存档"; color: txt3; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                            Combo { model: ["pp", "ggg", "aa", "ww"] }
                        }
                    }
                    DangerButton {
                        Layout.alignment: Qt.AlignVCenter
                        text: "清除全部加点"
                    }
                }
            }
        }
    }

    // ==================================================== 组件
    component Card: Rectangle {
        radius: 16
        color: ma.containsMouse ? cardHi : card
        border.color: ma.containsMouse ? Qt.rgba(a1.r, a1.g, a1.b, 0.35) : line
        border.width: 1
        Behavior on color { ColorAnimation { duration: 150 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }
        // 入场动画
        opacity: 0; transform: Translate { y: 18 }
        SequentialAnimation on opacity {
            running: true; ParallelAnimation {
                NumberAnimation { duration: 420; easing.type: Easing.OutCubic; to: 1 }
            }
        }
        NumberAnimation on y { }   // 占位
        MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
    }

    component CheatToggle: Row {
        property string label: ""
        property bool on0: false
        spacing: 12
        Text { text: label; color: txt; font.pixelSize: 14; anchors.verticalCenter: parent.verticalCenter }
        Item {
            width: 46; height: 26; anchors.verticalCenter: parent.verticalCenter
            property bool on: on0
            Rectangle {
                anchors.fill: parent; radius: 13
                color: parent.on ? Qt.rgba(a1.r, a1.g, a1.b, 0.25) : "#222938"
                border.color: parent.on ? a1 : line
                Behavior on color { ColorAnimation { duration: 180 } }
                Behavior on border.color { ColorAnimation { duration: 180 } }
            }
            Rectangle {
                x: parent.on ? parent.width - width - 3 : 3
                anchors.verticalCenter: parent.verticalCenter
                width: 20; height: 20; radius: 10
                gradient: Gradient { orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: a1 } GradientStop { position: 1; color: a2 } }
                Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: parent.on = !parent.on }
        }
    }

    component GradButton: Rectangle {
        property string text: ""
        width: btnLbl.implicitWidth + 44; height: 42; radius: 10
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0; color: a1 } GradientStop { position: 1; color: a2 } }
        scale: gba.pressed ? 0.96 : 1.0
        Behavior on scale { NumberAnimation { duration: 120 } }
        Rectangle { anchors.fill: parent; radius: parent.radius; color: "#fff"
                    opacity: gba.containsMouse ? 0.12 : 0
                    Behavior on opacity { NumberAnimation { duration: 150 } } }
        Text { id: btnLbl; text: parent.text; color: "#08131a"; font.pixelSize: 14; font.weight: Font.DemiBold
               anchors.centerIn: parent }
        MouseArea { id: gba; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor }
    }

    component DangerButton: Rectangle {
        property string text: ""
        width: dbLbl.implicitWidth + 44; height: 42; radius: 10
        color: dba.containsMouse ? "#ff5c77" : danger
        Behavior on color { ColorAnimation { duration: 150 } }
        scale: dba.pressed ? 0.96 : 1.0
        Behavior on scale { NumberAnimation { duration: 120 } }
        Text { id: dbLbl; text: parent.text; color: "#fff"; font.pixelSize: 14; font.weight: Font.DemiBold
               anchors.centerIn: parent }
        MouseArea { id: dba; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor }
    }

    component Combo: Rectangle {
        property var model: []
        width: 150; height: 34; radius: 8
        color: "#1d2432"; border.color: coMa.containsMouse ? a1 : line
        Behavior on border.color { ColorAnimation { duration: 150 } }
        Row {
            anchors.left: parent.left; anchors.leftMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Text { text: "pp"; color: txt; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
        }
        Text { text: "▾"; color: txt3; anchors.right: parent.right; anchors.rightMargin: 10
               anchors.verticalCenter: parent.verticalCenter }
        MouseArea { id: coMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor }
    }
}
'''


def main():
    QGuiApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, False)
    QQuickStyle.setStyle('Basic')
    app = QGuiApplication(sys.argv)
    eng = QQmlApplicationEngine()
    eng.loadData(QML.encode('utf-8'), QUrlMockup())
    if not eng.rootObjects():
        return 1
    return app.exec()


def QUrlMockup():
    from PySide6.QtCore import QUrl
    return QUrl('mockup.qml')


if __name__ == '__main__':
    sys.exit(main())
