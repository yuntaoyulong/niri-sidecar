#!/usr/bin/env python3
"""Install source and user services without changing a compositor or system package."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

SOURCE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    parser.add_argument(
        "--config-home", type=Path, default=Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    )
    parser.add_argument("--with-folder-hook", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--enable", action="store_true", help="Enable and start the user service")
    args = parser.parse_args()
    prefix = args.prefix.expanduser().resolve()
    destination = prefix / "share/niri-sidecar"
    launcher = prefix / "bin/niri-sidecar"
    service = args.config_home / "systemd/user/niri-sidecar.service"
    if args.uninstall:
        if service.exists():
            subprocess.run(["systemctl", "--user", "disable", "--now", "niri-sidecar.service"], check=False)
            service.unlink()
        shutil.rmtree(destination, ignore_errors=True)
        if launcher.exists() and "niri_sidecar.cli" in launcher.read_text():
            launcher.unlink()
        print("Removed Sidecar program and service; private user configuration and pins were retained.")
        return
    destination.mkdir(parents=True, exist_ok=True)
    for directory in ("src", "qml", "native"):
        shutil.copytree(
            SOURCE / directory,
            destination / directory,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.so"),
        )
    if args.with_folder_hook:
        flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "gtk4"], text=True).split()
        subprocess.run(
            [
                "cc",
                "-shared",
                "-fPIC",
                "-O2",
                "-o",
                str(destination / "native/filedock.so"),
                str(destination / "native/filedock.c"),
                *flags,
            ],
            check=True,
        )
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(
        f'#!{sys.executable}\nimport sys,runpy\nsys.path.insert(0,{str(destination / "src")!r})\nrunpy.run_module("niri_sidecar.cli",run_name="__main__")\n'
    )
    launcher.chmod(0o755)
    cfg = args.config_home / "niri-sidecar/config.json"
    cfg.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not cfg.exists():
        cfg.write_text((SOURCE / "examples/config.json").read_text())
        cfg.chmod(0o600)
    service.parent.mkdir(parents=True, exist_ok=True)
    service.write_text(
        "[Unit]\nDescription=Niri Sidecar desktop tools\nAfter=graphical-session.target\nPartOf=graphical-session.target\n\n[Service]\n"
        + f'ExecStart="{launcher}" run\nRestart=on-failure\nRestartSec=2\nUMask=0077\n\n[Install]\nWantedBy=graphical-session.target\n'
    )
    print(f"Installed: {launcher}\nConfiguration: {cfg}")
    if args.enable:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "niri-sidecar.service"], check=True)
    else:
        print("Run niri-sidecar doctor, then niri-sidecar run; use --enable for user-service autostart.")


if __name__ == "__main__":
    main()
