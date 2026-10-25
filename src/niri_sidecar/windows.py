import json
import subprocess


def tasks(app_id="com.mitchellh.ghostty"):
    windows = json.loads(subprocess.check_output(["niri", "msg", "-j", "windows"], timeout=3))
    workspaces = json.loads(subprocess.check_output(["niri", "msg", "-j", "workspaces"], timeout=3))
    names = {w["id"]: str(w.get("name") or w["idx"]) for w in workspaces}
    items = []
    for window in windows:
        if window.get("app_id", "").lower().removesuffix(".desktop") != app_id.lower().removesuffix(
            ".desktop"
        ):
            continue
        title = window["title"].strip()
        running = bool(title and 0x2800 <= ord(title[0]) <= 0x28FF)
        items.append(
            {
                "id": window["id"],
                "title": title[1:].strip() if running else title,
                "running": running,
                "workspace": names.get(window["workspace_id"], ""),
                "focused": window["is_focused"],
            }
        )
    items.sort(key=lambda item: (not item["running"], not item["focused"], item["id"]))
    return {"ok": True, "tasks": items}


def focus(ident, app_id):
    state = tasks(app_id)
    if not any(item["id"] == int(ident) for item in state["tasks"]):
        raise ValueError("Window closed or does not belong to this selector")
    subprocess.run(
        ["niri", "msg", "action", "focus-window", "--id", str(int(ident))],
        check=True,
        stdout=subprocess.DEVNULL,
        timeout=3,
    )
    return tasks(app_id)
