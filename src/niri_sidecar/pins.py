#!/usr/bin/python3
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import runpy
import sqlite3
import shutil
import subprocess
import sys
import time
from niri_sidecar.common import config
from urllib.parse import urlsplit, unquote

ROOT = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "niri-sidecar" / "pins"
ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
ROOT.chmod(0o700)
os.umask(0o077)
DB = sqlite3.connect(ROOT / "pins.sqlite3", timeout=5)
DB.execute(
    "CREATE TABLE IF NOT EXISTS pins (id TEXT PRIMARY KEY, mime TEXT, filename TEXT, metadata TEXT, created REAL)"
)


def paste(*args):
    return subprocess.check_output(["wl-paste", "--no-newline", *args], timeout=3)


def clipboard():
    offered = paste("--list-types").decode().splitlines()
    for mime in [
        "text/uri-list",
        "x-special/gnome-copied-files",
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/bmp",
        "text/plain;charset=utf-8",
        "text/plain",
    ]:
        if mime in offered:
            return mime, paste("--type", mime)
    if any(t.startswith("text/") for t in offered):
        return "text/plain;charset=utf-8", paste("--type", "text")
    raise ValueError("请先复制文字、图片或文件")


def describe(mime, data):
    if mime.startswith("image/"):
        return {"kind": "image", "title": "剪贴板图片", "detail": f"{len(data) / 1024:.0f} KB", "paths": []}
    text = data.decode("utf-8", errors="replace")
    if mime in ("text/uri-list", "x-special/gnome-copied-files"):
        paths = [
            unquote(urlsplit(line).path) for line in text.splitlines() if urlsplit(line).scheme == "file"
        ]
        if paths:
            names = [Path(p).name for p in paths]
            return {
                "kind": "files",
                "title": names[0] if len(paths) == 1 else f"{len(paths)} 个文件",
                "detail": "\n".join(names),
                "paths": paths,
            }
    stripped = text.strip()
    link = "\n" not in stripped and urlsplit(stripped).scheme in ("http", "https")
    return {
        "kind": "link" if link else "text",
        "title": (stripped.splitlines() or ["空白文字"])[0][:90],
        "detail": text[:800],
        "paths": [],
    }


def snapshot(message=""):
    entries = []
    for ident, mime, filename, metadata, created in DB.execute("SELECT * FROM pins ORDER BY created DESC"):
        item = json.loads(metadata)
        item.update(id=ident, mime=mime, filename=filename, created=created, preview="")
        if item["kind"] == "image":
            item["preview"] = Path(filename).as_uri()
        elif len(item["paths"]) == 1 and (mimetypes.guess_type(item["paths"][0])[0] or "").startswith(
            "image/"
        ):
            item["preview"] = Path(item["paths"][0]).as_uri()
        entries.append(item)
    try:
        offered = paste("--list-types").decode().splitlines()
        if any(mime in offered for mime in ("text/uri-list", "x-special/gnome-copied-files")):
            current = describe(*clipboard())["title"]
        else:
            current = "Copy files to add them here"
    except (ValueError, subprocess.SubprocessError):
        current = "Clipboard unavailable"
    if not config()["modules"]["clipboard_pins"]:
        entries = [item for item in entries if item["kind"] == "files"]
    return {"ok": True, "entries": entries, "current": current, "message": message}


def save(mime, data):
    ident = hashlib.sha256(mime.encode() + b"\0" + data).hexdigest()[:24]
    suffix = mimetypes.guess_extension(mime.split(";")[0]) or ".bin"
    path = ROOT / (ident + suffix)
    path.write_bytes(data)
    DB.execute(
        "INSERT OR REPLACE INTO pins VALUES (?,?,?,?,?)",
        (ident, mime, str(path), json.dumps(describe(mime, data), ensure_ascii=False), time.time()),
    )
    DB.commit()
    return ident


def entry(ident):
    row = DB.execute("SELECT mime,filename,metadata FROM pins WHERE id=?", (ident,)).fetchone()
    if row is None:
        raise ValueError("条目已取消固定")
    return row[0], Path(row[1]), json.loads(row[2])


def copy(mime, data):
    subprocess.run(
        ["wl-copy", "--type", mime],
        input=data,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=3,
    )


def show(mime, path, info):
    pin = runpy.run_path(str(Path(__file__).with_name("desktop_pin.py")))
    if info["kind"] == "files":
        for source in info["paths"]:
            folder = pin["new_card"]()
            pin["launch"](pin["file_card"](source, folder), folder)
    else:
        folder = pin["new_card"]()
        card = {"kind": info["kind"], "title": info["title"], "mime": mime}
        if info["kind"] == "image":
            image = folder / path.name
            shutil.copyfile(path, image)
            card.update(source=str(image), preview=str(image))
        else:
            card.update(kind="text", text=path.read_text())
            if info["kind"] == "link":
                card["uri"] = path.read_text().strip()
        pin["launch"](card, folder)


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


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    message = ""
    if action in ("tasks", "focus"):
        app_id = (
            sys.argv[2 if action == "tasks" else 3]
            if len(sys.argv) > (2 if action == "tasks" else 3)
            else "com.mitchellh.ghostty"
        )
        state = tasks(app_id)
        if action == "focus":
            ident = int(sys.argv[2])
            if not any(item["id"] == ident for item in state["tasks"]):
                raise ValueError("窗口已关闭")
            subprocess.run(
                ["niri", "msg", "action", "focus-window", "--id", str(ident)],
                check=True,
                stdout=subprocess.DEVNULL,
                timeout=3,
            )
            state = tasks(app_id)
        print(json.dumps(state, ensure_ascii=False))
        return
    if action == "pin" and not config()["modules"]["clipboard_pins"]:
        raise ValueError("Enable clipboard_pins to store non-file clipboard contents")
    if action == "pin-files":
        mime, data = clipboard()
        if describe(mime, data)["kind"] != "files":
            raise ValueError("请先用 copy 路径 或文件管理器复制文件")
        save(mime, data)
        message = "文件已加入暂存"
    elif action == "pin":
        save(*clipboard())
        message = "已固定当前剪贴板"
    elif action == "capture-image":
        data = sys.stdin.buffer.read()
        copy("image/png", data)
        save("image/png", data)
        message = "标注图片已固定"
    elif action in ("copy", "remove", "show", "edit"):
        ident = sys.argv[2]
        mime, path, info = entry(ident)
        if action == "copy":
            copy(mime, path.read_bytes())
            message = "已复制，可直接粘贴"
        elif action == "remove":
            DB.execute("DELETE FROM pins WHERE id=?", (ident,))
            DB.commit()
            path.unlink(missing_ok=True)
            message = "已取消固定"
        elif action == "show":
            show(mime, path, info)
            message = "已贴到桌面"
        else:
            image = str(path) if info["kind"] == "image" else info["paths"][0]
            subprocess.Popen(
                [
                    "satty",
                    "--filename",
                    image,
                    "--copy-command",
                    "niri-sidecar pins capture-image",
                    "--actions-on-enter",
                    "save-to-clipboard,exit",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            message = "已打开 Satty，完成标注后按 Enter 固定"
    elif action != "status":
        raise ValueError("未知操作")
    print(json.dumps(snapshot(message), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        sys.exit(1)
