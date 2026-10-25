import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

PanelWindow {
    id: panel
    component TaskText: Text {
        textFormat: Text.PlainText
        font.family: panel.fontFamily
        font.pixelSize: 13
        font.hintingPreference: Font.PreferFullHinting
        renderType: Text.NativeRendering
    }
    required property string backend
    property bool enabled: true
    property color textColor: "#e7e0e8"
    property color accentColor: "#d1bcfd"
    property color outlineColor: "#66948f99"
    property string fontFamily: "sans-serif"
    visible: enabled
    property int bottomOffset: 17
    property int rightOffset: 202
    property string appId: "com.mitchellh.ghostty"
    property string panelTitle: "Terminal tasks"
    property string pillLabel: "Tasks"
    property bool showThumbnails: false
    onExpandedChanged: {
        if (showThumbnails) {
            Quickshell.execDetached(["/usr/bin/python3", panel.backend, "preview", expanded ? "show" : "hide", appId,
                "--screen", screen.name, "--layout", "sidebar", "--right-margin", String(rightOffset)]);
        }
    }
    property color dockBackground: "#471d211a"
    property bool expanded: false
    property bool busy: false
    property string error: ""
    property var tasks: []
    readonly property string client: backend
    anchors { bottom: true; right: true }
    margins { bottom: bottomOffset; right: rightOffset }
    implicitWidth: expanded && !showThumbnails ? 430 : 100
    implicitHeight: expanded && !showThumbnails ? Math.min(500, screen.height - 100) : 30
    color: "transparent"
    exclusiveZone: -1
    WlrLayershell.namespace: "niri-sidecar:tasks:" + panel.appId
    WlrLayershell.layer: WlrLayer.Top
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    function update(line) {
        try {
            const state = JSON.parse(line);
            if (state.ok) { tasks = state.tasks; error = ""; }
            else error = state.error;
        } catch (failure) { error = "Window list unavailable"; }
    }
    Process {
        id: status
        command: ["/usr/bin/python3", panel.client, "windows", "tasks", panel.appId]
        running: panel.enabled
        stdout: SplitParser { onRead: data => panel.update(data) }
    }
    Process {
        id: selection
        stdout: SplitParser { onRead: data => panel.update(data) }
        onExited: (exitCode, exitStatus) => { panel.busy = false; if (exitCode === 0) panel.expanded = false; }
    }
    Timer { interval: panel.expanded ? 2000 : 15000; repeat: true; running: panel.enabled; onTriggered: if (!status.running && !panel.busy) status.running = true }
    Timer { id: leaveDelay; interval: 300; onTriggered: panel.expanded = false }
    Item {
        anchors.fill: parent
        HoverHandler {
            onHoveredChanged: {
                if (hovered) { leaveDelay.stop(); panel.expanded = true; if (!status.running && !panel.busy) status.running = true; }
                else leaveDelay.restart();
            }
        }
        Rectangle {
            visible: panel.expanded && !panel.showThumbnails
            anchors { top: parent.top; left: parent.left; right: parent.right; bottom: pill.top; bottomMargin: 6 }
            radius: 10
            color: panel.dockBackground
            border { width: 1; color: panel.outlineColor }
            TaskText {
        textFormat: Text.PlainText
                id: heading
                anchors { top: parent.top; left: parent.left; margins: 12 }
                text: panel.panelTitle
                color: panel.textColor
                font { pixelSize: 14; bold: true }
            }
            TaskText {
        textFormat: Text.PlainText
                id: subtitle
                anchors { top: heading.bottom; topMargin: 7; left: heading.left; right: parent.right; rightMargin: 12 }
                text: panel.error || "Hover to inspect · Click to focus"
                color: panel.textColor
                font.pixelSize: 12
                elide: Text.ElideRight
            }
            ListView {
                id: list
                anchors { top: subtitle.bottom; topMargin: 10; bottom: parent.bottom; bottomMargin: 8; left: parent.left; right: parent.right; leftMargin: 8; rightMargin: 8 }
                model: panel.tasks
                spacing: 4
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                delegate: Rectangle {
                    id: task
                    required property var modelData
                    width: list.width
                    height: 64
                    radius: 6
                    color: pointer.containsMouse ? "#28ffffff" : (modelData.focused ? "#1cffffff" : "transparent")
                    TaskText {
        textFormat: Text.PlainText
                        id: title
                        anchors { top: parent.top; topMargin: 9; left: parent.left; leftMargin: 9; right: parent.right; rightMargin: 9 }
                        text: task.modelData.title
                        color: panel.textColor
                        font.pixelSize: 14
                        elide: Text.ElideRight
                    }
                    TaskText {
        textFormat: Text.PlainText
                        anchors { top: title.bottom; topMargin: 6; left: title.left }
                        text: (task.modelData.running ? "● running" : "○ idle") + "  ·  workspace " + task.modelData.workspace
                        color: task.modelData.running ? panel.accentColor : panel.textColor
                        font.pixelSize: 12
                    }
                    MouseArea {
                        id: pointer
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: !panel.busy
                        onClicked: {
                            panel.busy = true;
                            selection.command = ["/usr/bin/python3", panel.client, "windows", "focus", String(task.modelData.id), panel.appId];
                            selection.running = true;
                        }
                    }
                }
            }
        }
        Rectangle {
            id: pill
            anchors { bottom: parent.bottom; right: parent.right }
            width: 100; height: 30; radius: 7
            color: panel.dockBackground
            border { width: 1; color: panel.outlineColor }
            TaskText {
        textFormat: Text.PlainText anchors.centerIn: parent; text: panel.pillLabel + "  " + panel.tasks.length; color: panel.textColor }
        }
    }
}
