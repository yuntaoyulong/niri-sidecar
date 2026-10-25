import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

PanelWindow {
    id: panel
    required property string backend
    property color textColor: "#e7e0e8"
    property color accentColor: "#d1bcfd"
    property color outlineColor: "#66948f99"
    property bool enabled: true
    visible: enabled
    property int bottomOffset: 17
    property bool filesOnly: false
    property int leftOffset: 0
    property int rightOffset: 98
    readonly property var shownEntries: filesOnly ? entries.filter(entry => entry.kind === "files") : entries
    property color dockBackground: "#471d211a"
    property bool expanded: false
    property bool busy: false
    property string current: ""
    property string message: ""
    property string operation: ""
    property var entries: []
    readonly property string client: backend
    anchors { bottom: true; right: !filesOnly; left: filesOnly }
    margins { bottom: bottomOffset; right: filesOnly ? 0 : rightOffset; left: filesOnly ? leftOffset : 0 }
    implicitWidth: expanded ? 430 : (filesOnly ? 88 : 98)
    implicitHeight: expanded ? Math.min(560, screen.height - 100) : 30
    color: "transparent"
    exclusiveZone: -1
    WlrLayershell.namespace: panel.filesOnly ? "niri-sidecar:files" : "niri-sidecar:clipboard"
    WlrLayershell.layer: WlrLayer.Top
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    function acceptState(line) {
        try {
            const state = JSON.parse(line);
            if (!state.ok) { message = state.error; return; }
            entries = state.entries;
            current = state.current;
            if (state.message) message = state.message;
        } catch (error) { message = "Pins unavailable"; }
    }
    function act(action, ident) {
        if (busy) return;
        busy = true;
        operation = action;
        message = "";
        command.command = ["/usr/bin/python3", client, "pins", action];
        if (ident) command.command = ["/usr/bin/python3", client, "pins", action, ident];
        command.running = true;
    }
    Process {
        id: status
        command: ["/usr/bin/python3", panel.client, "pins", "status"]
        running: panel.enabled
        stdout: SplitParser { onRead: data => panel.acceptState(data) }
    }
    Process {
        id: command
        stdout: SplitParser { onRead: data => panel.acceptState(data) }
        onExited: (exitCode, exitStatus) => {
            panel.busy = false;
            if (exitCode === 0 && ["copy", "show", "edit"].includes(panel.operation)) closeAfterAction.restart();
        }
    }
    Timer {
        interval: panel.expanded ? 2000 : 15000
        repeat: true
        running: panel.enabled
        onTriggered: if (!status.running && !panel.busy) status.running = true
    }
    Timer { id: leaveDelay; interval: 300; onTriggered: panel.expanded = false }
    Timer { id: closeAfterAction; interval: 400; onTriggered: panel.expanded = false }
    Item {
        anchors.fill: parent
        HoverHandler {
            onHoveredChanged: {
                if (hovered) {
                    leaveDelay.stop(); closeAfterAction.stop();
                    panel.expanded = true;
                    if (!status.running && !panel.busy) status.running = true;
                } else leaveDelay.restart();
            }
        }
        Rectangle {
            visible: panel.expanded
            anchors { top: parent.top; left: parent.left; right: parent.right; bottom: pill.top; bottomMargin: 6 }
            color: panel.dockBackground
            radius: 10
            border { width: 1; color: panel.outlineColor }
            Text {
                id: heading
                anchors { top: parent.top; left: parent.left; margins: 12 }
                text: panel.filesOnly ? "Files" : "Clipboard pins"
                color: panel.textColor
                font { pixelSize: 15; bold: true }
            }
            Rectangle {
                anchors { top: parent.top; right: parent.right; margins: 9 }
                width: 100; height: 28; radius: 6
                color: pinHover.containsMouse ? "#28ffffff" : "#15ffffff"
                Text { anchors.centerIn: parent; text: panel.busy ? "Working…" : "+ Pin current"; color: panel.textColor; font.pixelSize: 12 }
                MouseArea { id: pinHover; anchors.fill: parent; hoverEnabled: true; enabled: !panel.busy; onClicked: panel.act(panel.filesOnly ? "pin-files" : "pin", "") }
            }
            Text {
                id: currentLabel
                anchors { top: heading.bottom; topMargin: 12; left: parent.left; right: parent.right; leftMargin: 12; rightMargin: 12 }
                text: panel.message || ("Current: " + (panel.current || "Reading…"))
                color: panel.textColor; font.pixelSize: 11
                elide: Text.ElideRight
            }
            Text {
                id: help
                anchors { top: currentLabel.bottom; topMargin: 5; left: parent.left; leftMargin: 12 }
                text: "Click to copy · Right-click to unpin"
                color: "#b6c4ae"; font.pixelSize: 10
            }
            Text {
                visible: panel.shownEntries.length === 0
                anchors { centerIn: parent }
                text: panel.filesOnly ? "Copy files in a file manager, then choose Pin current." : "Copy content, then choose Pin current."
                color: panel.textColor; font.pixelSize: 13
                horizontalAlignment: Text.AlignHCenter
                lineHeight: 1.5
            }
            ListView {
                id: list
                anchors { top: help.bottom; topMargin: 10; bottom: parent.bottom; bottomMargin: 8; left: parent.left; right: parent.right; leftMargin: 8; rightMargin: 8 }
                model: panel.shownEntries
                spacing: 5
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                delegate: Rectangle {
                    id: card
                    required property var modelData
                    width: list.width; height: 98; radius: 7
                    color: cardPointer.containsMouse ? "#24ffffff" : "#0cffffff"
                    MouseArea {
                        id: cardPointer
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: !panel.busy
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        onClicked: mouse => panel.act(mouse.button === Qt.RightButton ? "remove" : "copy", card.modelData.id)
                    }
                    Rectangle {
                        anchors { left: parent.left; leftMargin: 7; verticalCenter: parent.verticalCenter }
                        width: 68; height: 70; radius: 5
                        color: "#10ffffff"
                        Image { anchors.fill: parent; anchors.margins: 2; source: card.modelData.preview; fillMode: Image.PreserveAspectFit; sourceSize { width: 136; height: 140 }
                            asynchronous: true }
                        Text {
                            visible: !card.modelData.preview
                            anchors.centerIn: parent
                            text: ({text:"TXT",link:"LINK",files:"FILE",image:"IMG"})[card.modelData.kind] || "PIN"
                            color: panel.textColor; font.pixelSize: 12
                        }
                    }
                    Text {
                        id: title
                        anchors { left: parent.left; leftMargin: 86; right: parent.right; rightMargin: 9; top: parent.top; topMargin: 8 }
                        text: card.modelData.title; color: panel.textColor; font { pixelSize: 12; bold: true }
                        elide: Text.ElideRight
                    }
                    Text {
                        anchors { left: title.left; right: title.right; top: title.bottom; topMargin: 4 }
                        text: card.modelData.detail.replace(/\n/g, "  ")
                        color: panel.textColor; font.pixelSize: 11; elide: Text.ElideRight
                    }
                    Row {
                        anchors { left: title.left; bottom: parent.bottom; bottomMargin: 7 }
                        spacing: 7
                        Repeater {
                            model: card.modelData.preview ? ["Pin card", "Annotate"] : ["Pin card"]
                            delegate: Rectangle {
                                required property string modelData
                                width: 48; height: 24; radius: 5
                                color: actionHover.containsMouse ? "#30ffffff" : "#16ffffff"
                                Text { anchors.centerIn: parent; text: parent.modelData; color: panel.textColor; font.pixelSize: 11 }
                                MouseArea { id: actionHover; anchors.fill: parent; hoverEnabled: true; enabled: !panel.busy; onClicked: panel.act(parent.modelData === "Annotate" ? "edit" : "show", card.modelData.id) }
                            }
                        }
                    }
                }
            }
        }
        Rectangle {
            id: pill
            anchors { bottom: parent.bottom; right: parent.right }
            width: panel.filesOnly ? 88 : 98; height: 30; radius: 7
            color: panel.dockBackground
            border { width: 1; color: panel.outlineColor }
            Text { anchors.centerIn: parent; text: (panel.filesOnly ? "Files  " : "PIN  ") + panel.shownEntries.length; color: panel.textColor; font.pixelSize: 13 }
        }
    }
}
