<div align="center">

# Niri Sidecar

**Remote resources, window switching, and files within reach.**

A modular Quickshell companion for the Niri desktop, with optional DankMaterialShell theme integration.

[简体中文](README.zh-CN.md) · [Quick start](#quick-start) · [Privacy](docs/privacy.md) · [Contributing](CONTRIBUTING.md)

[![CI](https://github.com/yuntaoyulong/niri-sidecar/actions/workflows/ci.yml/badge.svg)](https://github.com/yuntaoyulong/niri-sidecar/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-a78bfa.svg)](LICENSE)

![Niri Sidecar: compact remote hardware meters, window selectors, and file pins. Illustrated with synthetic data.](docs/assets/overview.svg)

*Illustration with synthetic data. No real desktop capture, server address, task title, or file record is included.*

</div>

Niri Sidecar grew out of a desktop used to supervise remote GPU work and several terminal sessions. It keeps resource readings and the next window or file close to the Dock, instead of adding another dashboard to keep open.

## What it does

| Module | Behaviour |
| --- | --- |
| **SSH resource strip** | Discovers this user's interactive SSH clients. Shows each GPU's model, compute utilisation and VRAM; CPU usage, RAM, and filesystem capacity. Model/capacity sits above a compact percentage block. Hover for details. |
| **Window / task selectors** | Hover to list Edge or terminal windows across workspaces; click to focus the exact window. App IDs are configurable. Terminal titles with a Braille spinner are marked running. |
| **Live window previews** | Optional PipeWire thumbnails for a selected application. Frames stay in RAM; leaving the preview closes streams. Disabled by default. |
| **File pins** | Explicitly pin copied file references and restore them to the clipboard later. `niri-sidecar copy path...` copies files without opening a file manager. |
| **Folder parking** | Optional Nautilus GTK4 hook: floating folders can hide when the pointer leaves and return from a Dock-side tab. Disabled by default; requires a separate build and Nautilus restart. |

CPU utilisation is normalised to the available CPU quota when cgroup accounting is visible. RAM uses a finite container limit when it is below host RAM, subtracting inactive file cache from the cgroup charge. Otherwise readings describe the host. Disk readings come from `df`, not the cloud provider's billing API.

**Current scope:** Linux + Niri + Quickshell. NVIDIA metrics use `nvidia-smi`; CPU/RAM/disk monitoring still works without it. This is an initial community release, not a universal desktop extension or a cloud-account monitor.

## Quick start

Install these tools using your distribution: **Python 3.10+**, **Niri**, **Quickshell**, **OpenSSH**, and **wl-clipboard**. Optional features need Python GI and GTK; see [installation details](docs/installation.md).

```sh
git clone https://github.com/yuntaoyulong/niri-sidecar.git
cd niri-sidecar
/usr/bin/python3 install.py
~/.local/bin/niri-sidecar doctor
~/.local/bin/niri-sidecar run
```

The installer copies source into `~/.local/share/niri-sidecar`, writes a launcher and a user service, and creates configuration only if it does not already exist. It does **not** change the compositor, replace a system package, restart Nautilus, or start the service unless requested.

For autostart, after checking the foreground run:

```sh
/usr/bin/python3 install.py --enable
```

Open an SSH session normally. Sidecar uses a non-interactive OpenSSH metrics connection, reuses its own short-lived multiplexed connection, and samples every three seconds by default. Key/agent authentication or a configured reusable connection is needed; Sidecar never prompts for or stores passwords. Strict host-key checking is enabled. Your existing interactive connection need not already be multiplexed.

## Configure only the modules you want

Edit `~/.config/niri-sidecar/config.json`. Changes are read while the application runs.

```json
{
  "modules": {
    "remote": true,
    "tasks": true,
    "edge": true,
    "file_pins": true,
    "folder_tabs": false,
    "clipboard_pins": false,
    "previews": false
  },
  "privacy": { "redact_hosts": true },
  "remote": { "interval": 3, "disk_paths": ["/", "~/data"] },
  "tasks": { "app_id": "com.mitchellh.ghostty", "label": "Tasks" },
  "edge": { "app_id": "microsoft-edge", "label": "Edge" }
}
```

`redact_hosts` shows `Remote 1`, `Remote 2`, etc. rather than usernames, addresses and remote hostnames. It does not hide file names or window titles from the local UI. Set `display` to a connector name if you want a particular screen. DMS colour, alpha and Dock sizing are used when its configuration is available; otherwise the supplied theme works independently.

Optional blur rules are in [examples/niri.kdl](examples/niri.kdl). Add the layer rule to your existing configuration; the file shortcut is optional. Every popup uses the same transparent background as its parent. Text and icons are not faded by lowering whole-window opacity.

## Files and previews

```sh
niri-sidecar copy ./report.pdf ./figure.png
# Then choose Pin current in the left-side Files entry.
```

Pins keep local references; the original file must remain available. This command writes the clipboard, not a copy of the file into the repository. Clipboard text/image history is **not** collected in the background. Enabling `clipboard_pins` allows explicit non-file pins; pin cards and Satty annotation are optional integrations.

For thumbnails and floating-folder parking, follow the separate, reversible steps in [installation details](docs/installation.md). The basic window selector does not require a screen-capture service.

## Inspect or develop

```sh
./bin/niri-sidecar doctor
./bin/niri-sidecar remote
./bin/niri-sidecar windows tasks com.mitchellh.ghostty
./bin/niri-sidecar demo --json
./bin/niri-sidecar demo
/usr/bin/python3 -m unittest discover -s tests -v
```

Demo mode supplies only the included synthetic fixture and does not inspect your SSH processes, clipboard or real window list. `remote` prints live metrics to stdout; save or share that output only after reviewing it. The full data flow and local state locations are documented in [Privacy](docs/privacy.md).

## Help shape the project

Useful contributions include AMD GPU collectors, better SSH connection reuse, accurate Dock bounds, other file-manager adapters, localisation, and accessibility testing. Please include a reproducer or an independent reference for metric changes. Start with [CONTRIBUTING.md](CONTRIBUTING.md), open a [feature proposal](https://github.com/yuntaoyulong/niri-sidecar/issues/new/choose), or join [Discussions](https://github.com/yuntaoyulong/niri-sidecar/discussions).

Tested during development with Niri 26.04, Quickshell 0.3.2 and GTK 4.24 on Ubuntu 26.10. The GTK4 Nautilus hook is experimental; terminal-window running status is a title heuristic, not an integration with Codex internals. Remote collectors currently target Linux `/proc` and cgroup v1/v2 layouts.

Built with [Niri](https://github.com/niri-wm/niri), [Quickshell](https://quickshell.org/), OpenSSH and optional GTK/PipeWire integration. [DankMaterialShell](https://github.com/AvengeMedia/DankMaterialShell) supplies the optional desktop theme. These projects are dependencies/inspirations, not endorsements.

[MIT license](LICENSE).
