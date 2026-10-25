# Installation and optional modules

## Dependencies

The base UI needs Niri, Quickshell, Python 3.10+, OpenSSH and wl-clipboard. Install Quickshell using its [official installation instructions](https://quickshell.org/docs/guide/install-setup/); package availability differs by distribution.

On an Ubuntu/Debian system with Niri and Quickshell already installed, optional GTK features use packages such as:

```sh
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-gstreamer-1.0 \
  gstreamer1.0-pipewire gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  libgtk4-layer-shell0 wl-clipboard
```

The GTK4 layer-shell library/typelib may require a newer distribution or a source build. `niri-sidecar doctor` reports whether the runtime library is discoverable. Use the distribution Python (`/usr/bin/python3` on Ubuntu) so its GI modules are visible; a Conda Python may not have them.

Material Icons is an optional system font for resource icons. Pin cards additionally need GTK3, the GTK3 layer-shell typelib (`gir1.2-gtklayershell-0.1` on Debian/Ubuntu), and Python GI. PDF/video card previews optionally use `pdftoppm`/`ffmpeg`; annotation optionally uses `satty`. Missing optional tools do not need to be installed for remote metrics or basic window switching.

## Run without installing

```sh
./bin/niri-sidecar doctor
/usr/bin/python3 src/niri_sidecar/cli.py run
```

To preview only fictional data:

```sh
./bin/niri-sidecar demo
```

Stop the foreground process with Ctrl+C. Do not run the same widgets from a second configuration at the same time.

## User installation

```sh
/usr/bin/python3 install.py
# Or install and enable the graphical-session user service:
/usr/bin/python3 install.py --enable
```

Add `~/.local/bin` to your PATH if needed. `--prefix` and `--config-home` support separate installation locations. Existing Sidecar configuration is preserved. Theme and module configuration are reread while running.

DMS integration is optional: its palette and enabled Dock config provide colour, transparency and approximate placement. Dock width is estimated from pinned/running applications; custom taskbar layouts may need adjustment. The current layout primarily targets a bottom Dock on one selected display.

## Live browser previews

First verify the basic selector works. Install GTK4, GStreamer/PipeWire and GTK4 layer-shell, then set `modules.previews` to `true`. The UI starts the preview daemon only for this opt-in module. The supported capture path is Niri's Mutter-compatible ScreenCast D-Bus API; another Wayland compositor is not assumed to provide it.

For a focused debugging probe on a **non-sensitive test window**:

```sh
niri-sidecar preview probe --window-id WINDOW_ID --seconds 3
```

The probe reports frame statistics and does not save the captured pixels. Leaving the actual preview closes its streams. No display-manager restart is needed.

## Experimental Nautilus folder parking

This module is a GTK4 process-local hook; it is not a Nautilus upstream plugin API. It is disabled by default.

1. Install a C compiler, `pkg-config`, GTK4 development headers and Nautilus.
2. Build during installation:

   ```sh
   /usr/bin/python3 install.py --with-folder-hook
   ```

3. Set `modules.folder_tabs` to `true` in Sidecar's config.
4. Close Nautilus normally when file operations have finished. Start the file manager through Sidecar:

   ```sh
   niri-sidecar folders open
   ```

An already running Nautilus process cannot acquire a preload library from a second invocation. Sidecar does not kill it or silently replace its D-Bus activation service. For persistent activation, explicitly configure your user Nautilus launcher/service to use the installed `native/filedock.so` as `LD_PRELOAD`. Do not set a global LD_PRELOAD.

The adapter treats floating Nautilus windows as parked/managed windows and leaves tiled ones unmanaged. Moving the pointer out hides a managed window after a short delay; hover a folder tab to restore it, or use middle-click to hide it. Popovers, drags and transient dialogs delay hiding. Validate this behaviour with your Nautilus version before relying on it.

## Uninstall

```sh
/usr/bin/python3 install.py --uninstall
```

This removes Sidecar's installed source/launcher and user service. Configuration and pins are retained. If you added the optional Niri rules or Nautilus preload to your own configuration, remove those entries as well. Runtime private data locations are listed in [Privacy](privacy.md).
