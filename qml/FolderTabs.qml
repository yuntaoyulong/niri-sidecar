import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
Item {
    id: root
    required property string backend
    required property var state
    property bool enabled: false
    property var folders: []
    Process {
        command: ["/usr/bin/python3", root.backend, "folders", "watch"]
        running: root.enabled
        stdout: SplitParser {
            onRead: data => { try { root.folders = JSON.parse(data).windows || []; } catch (error) { console.warn("Folder state unavailable"); } }
        }
    }
    Variants {
        model: Quickshell.screens
        delegate: PanelWindow {
            id: panel
            required property var modelData
            screen: modelData
            visible: root.enabled && root.folders.length > 0
            color: "transparent"
            anchors { bottom: true; left: true }
            margins {
                bottom: root.state.bottom || 15
                left: 100
            }
            implicitWidth: Math.min(panel.screen.width * 0.3, tabs.implicitWidth)
            implicitHeight: 30
            exclusiveZone: -1
            WlrLayershell.namespace: "niri-sidecar:folders"
            WlrLayershell.layer: WlrLayer.Top
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
            Flickable {
                anchors.fill: parent
                contentWidth: tabs.implicitWidth
                clip: true
                Row {
                    id: tabs
                    spacing: 3
                    Repeater {
                        model: root.folders
                        delegate: Rectangle {
                            id: tab
                            required property var modelData
                            width: Math.min(144, Math.max(68, label.implicitWidth+20))
                            height: 30
                            radius: 7
                            color: pointer.containsMouse ? Qt.lighter(root.state.background || "transparent", 1.15) : root.state.background || "transparent"
                            border.color: modelData.shown ? root.state.primary || "white" : root.state.outline || "transparent"
                            border.width: 1
                            Text {
        textFormat: Text.PlainText;

                                id: label
                                anchors { left: parent.left; leftMargin: 8; right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                                text: "▱  " + tab.modelData.title
                                color: root.state.text || "white"
                                elide: Text.ElideRight
                                font.pixelSize: 13
                            }
                            MouseArea {
                                id: pointer
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                                onEntered: { leaveDelay.stop(); hoverDelay.restart(); }
                                onExited: { hoverDelay.stop(); leaveDelay.restart(); }
                                onClicked: mouse => {
                                    if (mouse.button === Qt.LeftButton) Quickshell.execDetached(["/usr/bin/python3",root.backend,"folders","show",String(tab.modelData.id)]);
                                    else Quickshell.execDetached(["/usr/bin/python3",root.backend,"folders","hide",String(tab.modelData.id)]);
                                }
                            }
                            Timer {
                                id: leaveDelay
                                interval: 650
                                onTriggered: Quickshell.execDetached(["/usr/bin/python3",root.backend,"folders","hide",String(tab.modelData.id)])
                            }
                            Timer {
                                id: hoverDelay
                                interval: 180
                                onTriggered: Quickshell.execDetached(["/usr/bin/python3",root.backend,"folders","show",String(tab.modelData.id)])
                            }
                        }
                    }
                }
            }
        }
    }
}
