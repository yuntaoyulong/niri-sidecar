import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    id: root
    readonly property string backend: decodeURIComponent(String(Qt.resolvedUrl("../src/niri_sidecar/cli.py")).replace(/^file:\/\//, ""))
    property var state: ({modules: {}})
    function activeScreen(name) { return !state.output || state.output === name; }
    Process {
        command: ["/usr/bin/python3", root.backend, "theme", "--watch"]
        running: true
        stdout: SplitParser {
            onRead: data => { try { root.state = JSON.parse(data); } catch (error) { console.warn("Sidecar theme unavailable"); } }
        }
    }
    Process {
        command: ["/usr/bin/python3", root.backend, "preview", "daemon"]
        running: !!root.state.modules?.previews
    }
    RemoteGpu {
        backend: root.backend
        enabled: !!root.state.modules?.remote
    }
    FolderTabs {
        backend: root.backend
        state: root.state
        enabled: !!root.state.modules?.folder_tabs
    }
    Variants {
        model: Quickshell.screens
        delegate: TaskSwitcher {
            required property var modelData
            screen: modelData
            backend: root.backend
            enabled: !!root.state.modules?.edge && root.activeScreen(modelData.name)
            bottomOffset: root.state.bottom || 15
            rightOffset: 112
            appId: root.state.edge?.app_id || "microsoft-edge"
            panelTitle: "Browser windows"
            pillLabel: root.state.edge?.label || "Edge"
            showThumbnails: !!root.state.modules?.previews
            dockBackground: root.state.background || "transparent"
            textColor: root.state.text || "white"
            accentColor: root.state.primary || "white"
            outlineColor: root.state.outline || "transparent"
            fontFamily: root.state.font || "sans-serif"
        }
    }
    Variants {
        model: Quickshell.screens
        delegate: TaskSwitcher {
            required property var modelData
            screen: modelData
            backend: root.backend
            enabled: !!root.state.modules?.tasks && root.activeScreen(modelData.name)
            bottomOffset: root.state.bottom || 15
            rightOffset: 10
            appId: root.state.tasks?.app_id || "com.mitchellh.ghostty"
            panelTitle: "Terminal tasks"
            pillLabel: root.state.tasks?.label || "Tasks"
            dockBackground: root.state.background || "transparent"
            textColor: root.state.text || "white"
            accentColor: root.state.primary || "white"
            outlineColor: root.state.outline || "transparent"
            fontFamily: root.state.font || "sans-serif"
        }
    }
    Variants {
        model: Quickshell.screens
        delegate: ClipboardPins {
            required property var modelData
            screen: modelData
            backend: root.backend
            enabled: !!root.state.modules?.file_pins && root.activeScreen(modelData.name)
            textColor: root.state.text || "white"
            accentColor: root.state.primary || "white"
            outlineColor: root.state.outline || "transparent"
            filesOnly: true
            leftOffset: 8
            bottomOffset: root.state.bottom || 15
            dockBackground: root.state.background || "transparent"
        }
    }
}
