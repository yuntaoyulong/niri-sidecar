# Niri Sidecar 0.1.0

First public release of a modular Quickshell companion for Niri.

- SSH resource strip with GPU compute/VRAM, quota-aware CPU/RAM and filesystem capacity.
- App-specific terminal/task and browser window selectors, with optional in-memory PipeWire previews.
- Explicit file pins, file-to-clipboard CLI, and an optional GTK4 Nautilus folder-parking adapter.
- DMS theme synchronisation or a standalone transparent theme.
- Anonymous remote labels by default, no telemetry, disabled-by-default non-file clipboard pins/previews/native hook, and synthetic demo data.
- English/Chinese documentation, source-only user installation, privacy regression tests and CI.

Validation includes live read-only metrics from NVIDIA-equipped SSH hosts, a synthetic-data Quickshell launch, parser/privacy/install regression tests and a compiled GTK4 hook. The preload adapter is experimental; other compositors, AMD GPU sampling and every distribution/Nautilus combination are not claimed as supported.

Read the [README](https://github.com/yuntaoyulong/niri-sidecar#readme) and [privacy notes](https://github.com/yuntaoyulong/niri-sidecar/blob/main/docs/privacy.md) before enabling optional modules. Contributions focused on compatibility, precise metrics and accessibility are welcome.
