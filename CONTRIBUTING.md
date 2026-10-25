# Contributing

Thank you for helping make desktop-side remote work easier. Small, runnable fixes are welcome.

## Start from a reproducible problem

For a bug, include your Niri/Quickshell versions, enabled modules, expected behaviour and a short reproducer. Use `niri-sidecar doctor` rather than raw SSH process arguments. Remove addresses, usernames, window titles, clipboard contents and credentials before attaching logs or screenshots.

For a new feature, explain the desktop action it improves and how you would test it. Areas open for contribution:

- AMD/other GPU collectors with independent samples and unit tests.
- Reusing existing SSH masters and distinguishing interactive clients from helper processes.
- Accurate Dock bounds and other bottom-panel layouts.
- Other file-manager adapters, keyboard navigation and accessible icon labels.
- Localisation and packaging for more distributions.

## Development

The core collector and tests use the Python standard library. GTK/GStreamer are optional integrations. Source lives under `src/niri_sidecar`; `qml` contains the visible widgets; `native/filedock.c` is the opt-in Nautilus adapter.

```sh
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 -m compileall -q src
sh -n src/niri_sidecar/collect.sh
./bin/niri-sidecar demo --json
./bin/niri-sidecar demo
```

If Ruff is installed, run `ruff check .` and `ruff format --check src tests install.py bin/niri-sidecar`.

Add a focused regression test when fixing sampling, parser or privacy bugs. For a metric, state its denominator and scope: GPU utilisation differs from VRAM; container CPU quota differs from host logical CPUs; filesystem capacity differs from a provider's account balance. Do not use invented fixtures to claim a real integration was measured.

For QML changes, open both the compact and expanded views, verify transparent backgrounds at all menu levels, and test pointer entry/exit and exact-window focus. Use demo data for public visuals. The overview SVG is intentionally synthetic.

Keep modules independently usable. Do not add a hosted backend, analytics, mandatory account or background clipboard history. Optional dependencies should remain optional. Never commit actual runtime JSON, SSH configuration, key paths, pins, logs, screenshots of a real desktop, or compiled preload libraries.

## Pull requests

Describe the concrete problem, resulting behaviour and relevant validation. Keep unrelated formatting/refactors out of a feature fix. Contributions are made under the project's MIT licence.

Security or privacy exposures belong in private GitHub security reports, not public issues containing a credential. See [SECURITY.md](SECURITY.md).
