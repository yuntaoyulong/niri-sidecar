import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

Item {
    id: root
    property var state: ({hosts: []})
    required property string backend
    property bool enabled: true
    property string hoveredHostKey: ""
    readonly property color accent: state.primary || "white"
    readonly property color foreground: state.text || "white"
    Process {
        command: ["/usr/bin/python3", root.backend, "remote", "--watch"]
        running: root.enabled
        stdout: SplitParser {
            onRead: data => {
                try { root.state = JSON.parse(data); }
                catch (error) { console.warn("Remote monitor state:", error); }
            }
        }
    }
    function gib(value) { return (value / 1073741824).toFixed(1).replace(/\.0$/, ""); }
    function percent(value) { return value === null || value === undefined ? "--" : Math.round(value); }
    function metrics(host) {
        let result = [];
        for (const gpu of host.gpus || []) {
            result.push({title: gpu.name.replace(/^NVIDIA (GeForce )?/, ""),
                detail: "GPU " + gpu.index + " · VRAM " + (gpu.used / 1024).toFixed(1) + "/" + (gpu.total / 1024).toFixed(0) + " GiB",
                bars: [{label: "GPU", value: gpu.utilization}, {label: "VRAM", value: gpu.used / gpu.total * 100}]});
        }
        if (host.cpu) {
            let cpu = host.cpu;
            result.push({title: cpu.model.replace(/\(R\)|\(TM\)/g, "").replace(/^(Intel|AMD) /, "").replace(/ CPU @.*| \d+-Core Processor$/, ""),
                detail: cpu.cores + " cores · " + cpu.scope, bars: [{label: "CPU", value: cpu.percent}]});
        }
        if (host.memory) {
            let mem = host.memory;
            result.push({title: "RAM · " + gib(mem.total) + " GiB", detail: "Used " + gib(mem.used) + " GiB · " + mem.scope,
                bars: [{label: "RAM", value: mem.percent}]});
        }
        for (const disk of host.disks || []) {
            let name = disk.mount === "/" ? "System disk /" : disk.mount.split("/").pop();
            result.push({title: name + " · " + gib(disk.total) + " GiB", detail: "Used " + gib(disk.used) + " · Free " + gib(disk.available) + " GiB",
                bars: [{label: "Disk", value: disk.percent}]});
        }
        return result;
    }
    component Meter: Column {
        id: meter
        required property var metric
        spacing: 5
        Text {
        textFormat: Text.PlainText;

            width: parent.width
            text: meter.metric.title
            color: root.foreground
            font { family: root.state.font || "sans-serif"; pixelSize: 12; bold: true }
            elide: Text.ElideRight
        }
        Text {
        textFormat: Text.PlainText;

            width: parent.width
            text: meter.metric.detail
            color: root.foreground
            font { family: root.state.font || "sans-serif"; pixelSize: 11 }
            elide: Text.ElideRight
        }
        Row {
            width: parent.width
            spacing: 5
            Repeater {
                model: meter.metric.bars
                delegate: Rectangle {
                    required property var modelData
                    width: (meter.width - (meter.metric.bars.length - 1) * 5) / meter.metric.bars.length
                    height: 18
                    radius: 4
                    color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, .07)
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(1, (parent.modelData.value || 0) / 100))
                        height: parent.height
                        radius: parent.radius
                        color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, .32)
                        Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                    }
                    Text {
        textFormat: Text.PlainText;

                        anchors.centerIn: parent
                        text: parent.modelData.label + " " + root.percent(parent.modelData.value) + "%"
                        color: root.foreground
                        font { family: root.state.font || "sans-serif"; pixelSize: 11; bold: true }
                    }
                }
            }
        }
    }
    function selectedHost() {
        return (state.hosts || []).find(host => host.key === hoveredHostKey) || (state.hosts || [])[0] || {};
    }
    function compactMetrics(host) {
        let cells = [];
        for (const gpu of host.gpus || []) {
            let name = gpu.name.replace(/^NVIDIA (GeForce )?/, "").replace(/ 80GB.*| PCIe.*|RTX /g, "");
            cells.push({title: name, icon: "\ue30d", value: gpu.utilization});
            cells.push({title: (gpu.total / 1024).toFixed(0) + "G", icon: "\ue8f0", value: gpu.used / gpu.total * 100});
        }
        if (host.cpu) {
            let model = host.cpu.model.match(/\b\d{4}[A-Z]?\b/);
            cells.push({title: model ? model[0] : "CPU", icon: "\ue322", value: host.cpu.percent});
        }
        if (host.memory) cells.push({title: root.gib(host.memory.total) + "G", icon: "\ue1bc", value: host.memory.percent});
        for (const disk of host.disks || []) cells.push({title: root.gib(disk.total) + "G", icon: "\ue1db", value: disk.percent});
        return cells;
    }
    Variants {
        model: Quickshell.screens
        delegate: PanelWindow {
            id: panel
            required property var modelData
            property bool expanded: false
            screen: modelData
            visible: root.enabled && (root.state.hosts || []).length > 0 && (!root.state.output || root.state.output === modelData.name)
            color: "transparent"
            anchors { bottom: true; left: true }
            margins {
                bottom: Math.max(0, Math.round((root.state.dockBottom ?? 2) + ((root.state.dockHeight || 56) - 60) / 2))
                left: Math.round(screen.width / 2 + (root.state.dockWidth || 300) / 2 + 10)
            }
            implicitWidth: Math.min(strip.implicitWidth + 16, screen.width - margins.left - 12)
            implicitHeight: content.implicitHeight + 16
            exclusiveZone: -1
            WlrLayershell.namespace: "niri-sidecar:remote"
            WlrLayershell.layer: WlrLayer.Top
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
            Timer { id: closeDelay; interval: 250; onTriggered: panel.expanded = false }
            Rectangle {
                anchors.fill: parent
                color: root.state.background || "transparent"
                radius: 10
                border.width: 1
                border.color: root.state.outline || "transparent"
                HoverHandler {
                    onHoveredChanged: {
                        if (hovered) { closeDelay.stop(); panel.expanded = true; }
                        else closeDelay.restart();
                    }
                }
                Column {
                    id: content
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 8 }
                    spacing: 10
                    Column {
                        width: parent.width
                        spacing: 12
                        visible: panel.expanded
                        Text {
        textFormat: Text.PlainText;

                            width: parent.width
                            text: root.selectedHost().host || "SSH remote resources"
                            color: root.accent
                            font { family: root.state.font || "sans-serif"; pixelSize: 12; bold: true }
                            elide: Text.ElideMiddle
                        }
                        Text {
        textFormat: Text.PlainText;

                            width: parent.width
                            visible: !!root.selectedHost().error
                            text: root.selectedHost().error || ""
                            color: root.foreground
                            wrapMode: Text.Wrap
                            font.pixelSize: 12
                        }
                        Grid {
                            width: parent.width
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Repeater {
                                model: root.metrics(root.selectedHost())
                                delegate: Meter {
                                    required property var modelData
                                    metric: modelData
                                    width: (content.width - 12) / 2
                                }
                            }
                        }
                        Text {
        textFormat: Text.PlainText;

                            text: "GPU / VRAM / CPU / RAM / Disk"
                            color: root.foreground
                            font.pixelSize: 10
                        }
                    }
                    Flickable {
                        id: stripScroll
                        width: parent.width
                        height: 44
                        contentWidth: strip.implicitWidth
                        contentHeight: height
                        interactive: contentWidth > width
                        onContentWidthChanged: contentX = Math.min(contentX, Math.max(0, contentWidth - width))
                        onWidthChanged: contentX = 0
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        flickableDirection: Flickable.HorizontalFlick
                        Row {
                            id: strip
                            height: parent.height
                            spacing: 10
                            Repeater {
                                model: root.state.hosts || []
                                delegate: Row {
                                    id: hostRow
                                    required property var modelData
                                    required property int index
                                    readonly property var cells: root.compactMetrics(modelData)
                                    height: 44
                                    spacing: 3
                                    HoverHandler { onHoveredChanged: if (hovered) root.hoveredHostKey = hostRow.modelData.key }
                                    Rectangle {
                                        visible: hostRow.index > 0
                                        width: 1
                                        height: 38
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: root.state.outline || "transparent"
                                    }
                                    Repeater {
                                        model: hostRow.cells
                                        delegate: Column {
                                            required property var modelData
                                            width: 48
                                            spacing: 3
                                            Text {
        textFormat: Text.PlainText;

                                                width: parent.width
                                                text: modelData.title
                                                color: root.accent
                                                horizontalAlignment: Text.AlignHCenter
                                                elide: Text.ElideRight
                                                font { family: root.state.font || "sans-serif"; pixelSize: 11; bold: true }
                                            }
                                            Rectangle {
                                                width: parent.width
                                                height: 26
                                                radius: 4
                                                color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, .07)
                                                Rectangle {
                                                    anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
                                                    height: parent.height * Math.max(0, Math.min(1, (modelData.value || 0) / 100))
                                                    radius: 4
                                                    color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, .32)
                                                    Behavior on height { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                                                }
                                                Row {
                                                    anchors.centerIn: parent
                                                    spacing: 2
                                                    Text {
        textFormat: Text.PlainText;

                                                        text: modelData.icon
                                                        color: root.foreground
                                                        font { family: "Material Icons"; pixelSize: 13 }
                                                    }
                                                    Text {
        textFormat: Text.PlainText;

                                                        text: root.percent(modelData.value) + "%"
                                                        color: root.foreground
                                                        font { family: root.state.font || "sans-serif"; pixelSize: 10 }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            acceptedButtons: Qt.NoButton
                            enabled: stripScroll.contentWidth > stripScroll.width
                            onWheel: wheel => {
                                let delta = wheel.angleDelta.y || wheel.angleDelta.x;
                                stripScroll.contentX = Math.max(0, Math.min(stripScroll.contentWidth - stripScroll.width, stripScroll.contentX - delta));
                                wheel.accepted = true;
                            }
                        }
                    }
                }
            }
        }
    }
}
