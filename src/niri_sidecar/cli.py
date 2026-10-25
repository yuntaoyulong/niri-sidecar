#!/usr/bin/python3
"""One local entry point for the independently usable sidecar modules."""

import ctypes.util
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from niri_sidecar.common import PACKAGE, config, theme

ROOT = PACKAGE.parents[1]


def demo_scene():
    return json.loads((PACKAGE / "demo.json").read_text())


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def doctor():
    checks = {}
    for name in ("niri", "qs", "ssh", "wl-copy", "wl-paste", "nautilus"):
        checks[name] = bool(shutil.which(name))
    checks["python_gi_optional"] = importlib.util.find_spec("gi") is not None
    checks["gtk4_layer_shell_optional"] = bool(ctypes.util.find_library("gtk4-layer-shell"))
    checks["folder_hook_optional"] = (ROOT / "native/filedock.so").exists()
    return {
        "ok": all(checks[name] for name in ("niri", "qs", "ssh")),
        "checks": checks,
        "config_modules": config()["modules"],
        "telemetry": False,
    }


def main():
    args = sys.argv[1:]
    if args and args[0] == "--version":
        from niri_sidecar import __version__

        print(__version__)
        return
    if not args or args[0] in ("-h", "--help"):
        print(
            "Niri Sidecar\nCommands: run, doctor, remote [--watch], windows tasks|focus, pins, folders, preview, pin, copy, theme [--watch], demo [--json]\nConfiguration: $XDG_CONFIG_HOME/niri-sidecar/config.json\nNo telemetry. Remote metrics use your OpenSSH configuration."
        )
        return
    command, args = args[0], args[1:]
    demo = os.environ.get("NIRI_SIDECAR_DEMO") == "1"
    if command == "demo":
        if "--json" in args:
            emit(demo_scene())
            return
        os.environ["NIRI_SIDECAR_DEMO"] = "1"
        command, demo = "run", True
    if command == "run":
        os.execvp("qs", ["qs", "-p", str(ROOT / "qml/shell.qml")])
    if command == "doctor":
        emit(doctor())
        return
    if demo:
        scene = demo_scene()
        while True:
            if command in ("remote", "theme"):
                emit(scene["remote"] if command == "remote" else scene["theme"])
            elif command == "windows":
                emit({"ok": True, "tasks": scene["tasks"]})
            elif command == "pins":
                emit({"ok": True, "entries": scene["pins"], "current": "Synthetic demo files", "message": ""})
            elif command == "folders":
                emit({**scene["theme"], "windows": scene["folders"]})
            else:
                emit({"ok": True, "demo": True})
            if "--watch" not in args and "watch" not in args:
                return
            time.sleep(3)
    if command == "theme":
        while True:
            emit(theme())
            if "--watch" not in args:
                return
            time.sleep(1)
    if command == "remote":
        from niri_sidecar.remote import main as remote_main

        remote_main(args)
        return
    if command == "windows":
        from niri_sidecar.windows import tasks, focus

        if not args:
            raise ValueError("Expected tasks APP_ID or focus WINDOW_ID APP_ID")
        emit(focus(args[1], args[2]) if args[0] == "focus" else tasks(args[1]))
        return
    if command == "copy":
        if not args:
            raise ValueError("Pass one or more local file paths")
        paths = []
        for value in args:
            if value.startswith("file:"):
                uri = urlsplit(value)
                if uri.netloc not in ("", "localhost"):
                    raise ValueError("Only local file URLs can be copied")
                value = unquote(uri.path)
            paths.append(Path(value).expanduser().resolve(strict=True))
        payload = "".join(p.as_uri() + "\r\n" for p in paths).encode()
        subprocess.run(["wl-copy", "--type", "text/uri-list"], input=payload, check=True, timeout=3)
        return
    if command == "preview" and os.environ.get("_NIRI_SIDECAR_PREVIEW") != "1":
        library = ctypes.util.find_library("gtk4-layer-shell")
        if not library:
            raise ValueError("Live preview requires libgtk4-layer-shell")
        env = dict(os.environ, _NIRI_SIDECAR_PREVIEW="1", LD_PRELOAD=library)
        os.execve(sys.executable, [sys.executable, str(__file__), "preview", *args], env)
    if command == "pin-image":
        data = sys.stdin.buffer.read(64 * 1024 * 1024 + 1)
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 64 * 1024 * 1024:
            raise ValueError("Expected a PNG up to 64 MiB")
        subprocess.run(["wl-copy", "--type", "image/png"], input=data, check=True)
        subprocess.run([sys.executable, str(__file__), "pin", "--image-stdin"], input=data, check=True)
        return
    modules = {"pins": "pins.py", "folders": "folders.py", "preview": "preview.py", "pin": "desktop_pin.py"}
    if command not in modules:
        raise ValueError("Unknown command; use --help")
    sys.argv = [str(PACKAGE / modules[command]), *args]
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        emit({"ok": False, "error": str(error)})
        sys.exit(1)
