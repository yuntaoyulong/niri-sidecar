# Architecture

```text
Interactive ssh processes ──> remote.py ──OpenSSH──> collect.sh (read only)
                                 │
Niri JSON IPC ──> windows.py      │ GPU / CPU / RAM / filesystems
                                 ▼
                       Quickshell widgets
                                 ▲
Explicit file pins ──> pins.py ──┘
Nautilus GTK4 hook ──local D-Bus──> folders.py (optional)
Niri ScreenCast ──PipeWire──> preview.py (optional, RAM-only frames)
```

`cli.py` is the shared entry point; `common.py` reads configuration, resolves the display and supplies theme tokens. QML launches only enabled modules. DMS integration reads its existing palette and Dock configuration but is not an import-time requirement.

The remote collector sends a small POSIX shell program through SSH stdin. It samples CPU counters across a short interval and returns sectioned text. Parsing and cgroup normalisation happen locally. Remote scripts do not install packages or create metrics files. The module uses a short-lived multiplexed SSH connection per detected destination to avoid a fresh authentication for every sample.

The collector currently recognises common cgroup v1/v2 mount layouts. A finite memory limit below physical host RAM changes the memory denominator; inactive file cache is removed from cgroup usage. Visible CPU accounting is divided by quota-derived CPU capacity. Without usable cgroup accounting it uses the aggregate `/proc/stat` delta. GPU utilisation comes from NVIDIA's query, independently of memory occupancy.

Window selectors use app IDs and Niri window IDs, not title matching for focusing. A leading Braille spinner is only an optional running indicator. Basic selectors never access the Codex data directory. The file module keeps explicit user-selected pins separate from these window operations.

The Nautilus adapter is intentionally isolated: no global library preload, no system file replacement and no requirement for the other modules. It remains version-sensitive because GTK/Nautilus do not define this as a stable extension point.

The standalone app can coexist with DMS, but do not enable a duplicate copy of the same widgets in another Quickshell config. Dock dimensions are estimated; improving the geometry integration is a useful contributor task.
