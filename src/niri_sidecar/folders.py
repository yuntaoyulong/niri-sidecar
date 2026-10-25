#!/usr/bin/python3
import json, os, subprocess, sys, time
from pathlib import Path
from gi.repository import Gio, GLib

BUS = "io.github.nirisidecar.FileDock"
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)


def call(method, ident=None, managed=None):
    args = (
        GLib.Variant("(ub)", (int(ident), managed))
        if managed is not None
        else (GLib.Variant("(u)", (int(ident),)) if ident is not None else None)
    )
    return bus.call_sync(
        BUS, "/FileDock", BUS, method, args, None, Gio.DBusCallFlags.NONE, 1000, None
    ).unpack()


def windows():
    try:
        return sorted(call("List")[0], key=lambda w: w[0])
    except GLib.Error:
        return []


def show(ident):
    # Open on the current workspace/output when restoring a parked folder.
    ws = json.loads(subprocess.check_output(["niri", "msg", "-j", "workspaces"]))
    call("Show", ident)
    time.sleep(0.12)
    current = next((w for w in ws if w["is_focused"]), None)
    items = json.loads(subprocess.check_output(["niri", "msg", "-j", "windows"]))
    title = next((w[1] for w in windows() if w[0] == int(ident)), None)
    target = next(
        (w for w in items if w.get("app_id") in ("org.gnome.Nautilus", "nautilus") and w["title"] == title),
        None,
    )
    if current and target:
        subprocess.run(
            [
                "niri",
                "msg",
                "action",
                "move-window-to-workspace",
                "--window-id",
                str(target["id"]),
                "--focus",
                "false",
                str(current["idx"]),
            ],
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            ["niri", "msg", "action", "focus-window", "--id", str(target["id"])], stdout=subprocess.DEVNULL
        )


def launch(paths):
    hook = Path(__file__).resolve().parents[2] / "native/filedock.so"
    if not hook.exists():
        raise RuntimeError("Install with --with-folder-hook before using folder parking")
    env = dict(os.environ, LD_PRELOAD=str(hook))
    subprocess.Popen(["nautilus", "--new-window", *paths], env=env, start_new_session=True)


def snapshot():
    from niri_sidecar.common import theme

    state = theme()
    items = windows()
    wins = json.loads(subprocess.check_output(["niri", "msg", "-j", "windows"]))
    for ident, title, visible, managed in items:
        match = (
            next(
                (
                    w
                    for w in wins
                    if w.get("app_id") in ("org.gnome.Nautilus", "nautilus") and w["title"] == title
                ),
                None,
            )
            if visible
            else None
        )
        if match and bool(match["is_floating"]) != managed:
            call("Manage", ident, bool(match["is_floating"]))
    state.update(
        windows=[{"id": i, "title": t, "shown": v} for i, t, v, m in windows() if m],
        tabBottom=state["bottom"],
    )
    return state


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "watch"
    if mode == "show":
        show(sys.argv[2])
    elif mode == "hide":
        call("Hide", sys.argv[2])
    elif mode == "open":
        items = [w for w in windows() if w[3]]
        if items:
            show(items[-1][0])
        else:
            launch(sys.argv[2:])
    elif mode == "list":
        print(json.dumps(snapshot(), ensure_ascii=False))
    else:
        previous = None
        while True:
            try:
                value = json.dumps(snapshot(), ensure_ascii=False)
                if value != previous:
                    print(value, flush=True)
                    previous = value
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            time.sleep(0.6)
