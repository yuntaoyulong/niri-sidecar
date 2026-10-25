"""Configuration and theme shared by the optional sidecar modules."""

import json
import os
from pathlib import Path
import subprocess

HOME = Path.home()
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state"))
CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache"))
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "niri-sidecar"
PACKAGE = Path(__file__).resolve().parent
DEFAULTS = {
    "modules": {
        "remote": True,
        "tasks": True,
        "edge": True,
        "file_pins": True,
        "folder_tabs": False,
        "clipboard_pins": False,
        "previews": False,
    },
    "privacy": {"redact_hosts": True},
    "remote": {"interval": 3, "disk_paths": []},
    "tasks": {"app_id": "com.mitchellh.ghostty", "label": "Tasks"},
    "edge": {"app_id": "microsoft-edge", "label": "Edge"},
    "display": "",
    "theme": {
        "background": "#211f24",
        "alpha": 0.28,
        "text": "#e7e0e8",
        "primary": "#d1bcfd",
        "outline": "#948f99",
        "font": "sans-serif",
    },
}


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {} if default is None else default


def config():
    path = Path(os.environ.get("NIRI_SIDECAR_CONFIG", CONFIG_HOME / "niri-sidecar/config.json"))
    value = read_json(path)
    result = json.loads(json.dumps(DEFAULTS))
    for key, item in value.items():
        if isinstance(item, dict) and isinstance(result.get(key), dict):
            result[key].update(item)
        else:
            result[key] = item
    return result


def niri(query):
    return json.loads(subprocess.check_output(["niri", "msg", "-j", query], text=True, timeout=3))


def theme():
    cfg = config()
    settings = read_json(CONFIG_HOME / "DankMaterialShell/settings.json")
    palette = read_json(CACHE_HOME / "DankMaterialShell/dms-colors.json")
    colors = palette.get("colors", {}).get(palette.get("mode", "dark"), {})
    dock = next((d for d in settings.get("dockConfigs", []) if d.get("enabled")), {})
    alpha = min(1, max(0, float(dock.get("transparency", cfg["theme"]["alpha"]))))
    background = colors.get("surface_container", cfg["theme"]["background"]).lstrip("#")
    outline = colors.get("outline", cfg["theme"]["outline"]).lstrip("#")
    icon = dock.get("iconSize", 46)
    apps = set()
    outputs = {}
    try:
        apps = {w["app_id"].lower().removesuffix(".desktop") for w in niri("windows") if w.get("app_id")}
        outputs = niri("outputs")
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    session = read_json(STATE_HOME / "DankMaterialShell/session.json")
    apps.update(
        a.lower().removesuffix(".desktop")
        for a in session.get("dockPins", {}).get(dock.get("id", "dock"), [])
    )
    screens = dock.get("screenPreferences", [])
    output = cfg.get("display") or next((s for s in screens if s in outputs), "")
    if not output:
        output = next(iter(outputs), "")
    return {
        "output": output,
        "background": f"#{round(255 * alpha):02x}{background}",
        "text": colors.get("on_surface", cfg["theme"]["text"]),
        "primary": colors.get("primary", cfg["theme"]["primary"]),
        "outline": "#66" + outline,
        "font": settings.get("fontFamily", cfg["theme"]["font"]),
        "dockWidth": (len(apps) + int(dock.get("launcherEnabled", True)))
        * (icon * 1.2 + dock.get("itemSpacing", 4))
        + dock.get("spacing", 5) * 3,
        "dockBottom": dock.get("margin", 2) + dock.get("bottomGap", 0),
        "dockHeight": icon + 2 * dock.get("spacing", 5),
        "bottom": max(
            2,
            round(
                dock.get("margin", 2)
                + dock.get("bottomGap", 0)
                + (icon + 2 * dock.get("spacing", 5) - 30) / 2
            ),
        ),
        "modules": cfg["modules"],
        "tasks": cfg["tasks"],
        "edge": cfg["edge"],
    }


def rgba(argb):
    value = argb.lstrip("#")
    alpha, red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4, 6))
    return f"rgba({red},{green},{blue},{alpha / 255})"
