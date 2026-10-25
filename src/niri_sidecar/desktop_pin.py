#!/usr/bin/python3
"""Local MIME-aware pin cards for Wayland; independent of the screenshot editor."""

import argparse
import datetime
import json
import mimetypes
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.parse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from niri_sidecar.common import theme, rgba

APP = Path(__file__).resolve()
ROOT = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/desktop-pin-{os.getuid()}")) / "niri-sidecar-cards"


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=20, **kwargs)


def new_card():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    ROOT.chmod(0o700)
    return Path(tempfile.mkdtemp(prefix="pin-", dir=ROOT))


def file_card(path, folder):
    path = Path(path).expanduser().resolve(strict=True)
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    d = {"kind": "file", "title": path.name, "source": str(path), "mime": mime, "folder": str(folder)}
    if path.is_dir():
        d["text"] = (
            str(path)
            + "\n\n"
            + "\n".join(p.name + ("/" if p.is_dir() else "") for p in sorted(path.iterdir())[:60])
        )
    elif mime.startswith("image/"):
        d.update(kind="image", preview=str(path))
    elif mime == "application/pdf" and shutil.which("pdftoppm"):
        run(
            [
                "pdftoppm",
                "-f",
                "1",
                "-singlefile",
                "-scale-to",
                "1100",
                "-png",
                str(path),
                str(folder / "preview"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        d.update(preview=str(folder / "preview.png"), text="PDF · 首页预览")
    elif mime.startswith("video/") and shutil.which("ffmpeg"):
        preview = folder / "preview.png"
        run(
            [
                "ffmpeg",
                "-nostdin",
                "-loglevel",
                "error",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                "scale=800:-1",
                str(preview),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        d.update(preview=str(preview), text="视频 · 首帧预览")
    elif path.stat().st_size <= 1024 * 1024:
        try:
            content = path.read_text(encoding="utf-8")
            if "\x00" not in content:
                d.update(kind="text", text=content[:100000])
        except (UnicodeError, OSError):
            pass
    if "text" not in d:
        d["text"] = str(path) + "\n" + mime
    return d


def clipboard_card(folder):
    offered = run(["wl-paste", "--list-types"], capture_output=True, text=True).stdout.splitlines()
    for mime in ["image/png", "image/jpeg", "image/webp", "image/bmp"]:
        if mime in offered:
            data = run(["wl-paste", "--no-newline", "--type", mime], capture_output=True).stdout
            if len(data) > 64 * 1024 * 1024:
                raise ValueError("图片超过 64 MiB，请使用文件入口")
            p = folder / ("clipboard" + (mimetypes.guess_extension(mime) or ".png"))
            p.write_bytes(data)
            return {"kind": "image", "title": "剪贴板图片", "preview": str(p), "source": str(p), "mime": mime}
    for mime in ["text/uri-list", "x-special/gnome-copied-files"]:
        if mime in offered:
            text = run(["wl-paste", "--no-newline", "--type", mime], capture_output=True, text=True).stdout
            paths = []
            for line in text.splitlines():
                u = urllib.parse.urlsplit(line)
                if u.scheme == "file" and u.netloc in ("", "localhost"):
                    paths.append(urllib.parse.unquote(u.path))
            if paths:
                return [file_card(p, new_card()) for p in paths[:12]]
    text = run(["wl-paste", "--no-newline", "--type", "text"], capture_output=True, text=True).stdout
    if not text:
        raise ValueError("请先复制图片、文字或文件")
    if len(text) > 100000:
        text = text[:100000] + "\n…（显示前 100000 字符）"
    d = {"kind": "text", "title": "剪贴板文字", "text": text, "mime": "text/plain"}
    uri = text.strip()
    if "\n" not in uri and urllib.parse.urlsplit(uri).scheme in ("http", "https"):
        d.update(title="链接", uri=uri)
    return d


def launch(d, folder):
    d["folder"] = str(folder)
    path = folder / "card.json"
    path.write_text(json.dumps(d, ensure_ascii=False))
    with open(ROOT / "pin.log", "ab") as log:
        subprocess.Popen(
            ["/usr/bin/python3", str(APP), "--show", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )


def edit(path):
    satty = shutil.which("satty") or str(Path.home() / ".local/bin/satty")
    callback = "niri-sidecar pin-image"
    subprocess.Popen(
        [
            satty,
            "--filename",
            str(path),
            "--copy-command",
            callback,
            "--actions-on-enter",
            "save-to-clipboard,exit",
        ],
        start_new_session=True,
    )


def show(path):
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gtk, Gdk, GdkPixbuf, GtkLayerShell, GLib

    d = json.loads(Path(path).read_text())
    folder = Path(d["folder"])
    (folder / "pid").write_text(str(os.getpid()))
    if not GtkLayerShell.is_supported():
        raise RuntimeError("当前会话需要 Wayland layer-shell 支持")
    win = Gtk.Window(title="Desktop Pin · " + d["title"])
    win.set_wmclass("niri-sidecar:pin", "DesktopPin")
    win.set_resizable(True)
    win.set_visual(Gdk.Screen.get_default().get_rgba_visual())
    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_namespace(win, "niri-sidecar:pin")
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.TOP)
    GtkLayerShell.set_exclusive_zone(win, -1)
    GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.ON_DEMAND)
    win.set_size_request(430, 340)
    display = Gdk.Display.get_default()
    mon = 0
    try:
        focused = json.loads(
            run(["niri", "msg", "--json", "focused-output"], capture_output=True, text=True).stdout
        )["name"]
        for i in range(display.get_n_monitors()):
            if Gdk.Screen.get_default().get_monitor_plug_name(i) == focused:
                mon = i
    except Exception:
        pass
    GtkLayerShell.set_monitor(win, display.get_monitor(mon))
    for edge in [GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.LEFT]:
        GtkLayerShell.set_anchor(win, edge, True)
    count = len(list(ROOT.glob("pin-*/pid")))
    pos = [90 + (count % 6) * 28, 90 + (count % 6) * 28]

    def place():
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, int(pos[0]))
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, int(pos[1]))

    place()
    css = Gtk.CssProvider()

    def apply_theme():
        value = theme()
        color = value["background"][3:]
        red, green, blue = (int(color[i : i + 2], 16) for i in (0, 2, 4))
        alpha = int(value["background"][1:3], 16) / 255
        style = f"""window {{background:rgba({red},{green},{blue},{alpha});color:#edf0f7;border:1px solid rgba(127,121,109,0.4);border-radius:10px;}}
        button {{background:rgba(255,255,255,0.06);color:#edf0f7;padding:4px 7px;min-height:20px;box-shadow:none;}}
        button:hover {{background:rgba(255,255,255,0.14);}}
        textview,textview text,scrolledwindow,viewport {{background:transparent;color:#edf0f7;}}
        tooltip,menu {{background:rgba({red},{green},{blue},{alpha});color:#edf0f7;}}
        .pin-title {{font-weight:bold;}}"""
        css.load_from_data(style.encode())
        return True

    apply_theme()
    GLib.timeout_add(1500, apply_theme)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.set_border_width(8)
    win.add(box)
    header = Gtk.EventBox()
    header.add_events(
        Gdk.EventMask.BUTTON_PRESS_MASK
        | Gdk.EventMask.BUTTON_RELEASE_MASK
        | Gdk.EventMask.POINTER_MOTION_MASK
    )
    title = Gtk.Label(label=d["title"], xalign=0)
    title.set_ellipsize(3)
    title.get_style_context().add_class("pin-title")
    title.set_tooltip_text("拖动标题移动 · Ctrl+滚轮缩放 · Esc 关闭")
    header.add(title)
    box.pack_start(header, False, False, 2)
    drag = []

    def press(w, e):
        if e.button == 1:
            drag[:] = [e.x_root, e.y_root, pos[0], pos[1]]
        return True

    def motion(w, e):
        if drag:
            m = GtkLayerShell.get_monitor(win).get_geometry()
            pos[:] = [
                max(0, min(m.width - 80, drag[2] + e.x_root - drag[0])),
                max(0, min(m.height - 40, drag[3] + e.y_root - drag[1])),
            ]
            place()
        return True

    header.connect("button-press-event", press)
    header.connect("motion-notify-event", motion)
    header.connect("button-release-event", lambda *a: drag.clear())
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.set_min_content_width(260)
    scroll.set_min_content_height(100)
    box.pack_start(scroll, True, True, 0)
    pix = None
    if d.get("preview"):
        pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(d["preview"], 1000, 1000, True)
        picture = Gtk.Image()
        scroll.add_with_viewport(picture)

        def fit(w, alloc):
            width = max(1, alloc.width - 6)
            height = max(1, alloc.height - 6)
            ratio = min(width / pix.get_width(), height / pix.get_height())
            picture.set_from_pixbuf(
                pix.scale_simple(
                    max(1, int(pix.get_width() * ratio)),
                    max(1, int(pix.get_height() * ratio)),
                    GdkPixbuf.InterpType.BILINEAR,
                )
            )

        scroll.connect("size-allocate", fit)
    else:
        text = Gtk.TextView()
        text.set_editable(False)
        text.set_cursor_visible(False)
        text.set_monospace(True)
        text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text.set_left_margin(8)
        text.set_right_margin(8)
        text.get_buffer().set_text(d.get("text", d.get("source", "")))
        scroll.add(text)
    controls = Gtk.Box(spacing=4)
    box.pack_start(controls, False, False, 0)

    def button(label, callback):
        b = Gtk.Button(label=label)
        b.connect("clicked", callback)
        controls.pack_start(b, False, False, 0)

    def copy(*a):
        if d.get("kind") == "image":
            with open(d["source"], "rb") as f:
                subprocess.Popen(["wl-copy", "--type", d.get("mime", "image/png")], stdin=f)
        elif d.get("source"):
            subprocess.run(
                ["wl-copy", "--type", "text/uri-list"],
                input=(Path(d["source"]).as_uri() + "\r\n").encode(),
                timeout=4,
            )
        else:
            subprocess.run(
                ["wl-copy", "--type", "text/plain;charset=utf-8"], input=d.get("text", "").encode(), timeout=4
            )

    button("复制", copy)
    if d.get("source"):
        button("打开", lambda *a: subprocess.Popen(["xdg-open", d["source"]]))
    elif d.get("uri"):
        button("打开链接", lambda *a: subprocess.Popen(["xdg-open", d["uri"]]))
    if d.get("preview"):
        button("标注→贴屏", lambda *a: edit(d["preview"]))

    def resize(factor):
        width, height = win.get_size()
        win.set_size_request(
            max(280, min(1400, int(width * factor))), max(180, min(1000, int(height * factor)))
        )

    button("−", lambda *a: resize(0.85))
    button("+", lambda *a: resize(1.15))
    if display.get_n_monitors() > 1:

        def next_monitor(*a):
            current = GtkLayerShell.get_monitor(win)
            i = next((i for i in range(display.get_n_monitors()) if display.get_monitor(i) == current), 0)
            GtkLayerShell.set_monitor(win, display.get_monitor((i + 1) % display.get_n_monitors()))
            pos[:] = [90, 90]
            place()

        button("换屏", next_monitor)
    button("×", lambda *a: win.destroy())

    def key(w, e):
        if e.keyval == Gdk.KEY_Escape:
            win.destroy()
            return True
        return False

    win.connect("key-press-event", key)

    def close(*a):
        shutil.rmtree(folder, ignore_errors=True)
        Gtk.main_quit()

    win.connect("destroy", close)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: win.destroy())
    win.show_all()
    Gtk.main()


def main():
    parser = argparse.ArgumentParser(description="将剪贴板图片、文字和本地文件固定到桌面")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--show", help=argparse.SUPPRESS)
    parser.add_argument("--clipboard", action="store_true")
    parser.add_argument("--image-stdin", action="store_true")
    parser.add_argument("--screenshot", action="store_true")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--edit", metavar="IMAGE", help="使用 Satty 标注，Enter 复制并贴屏")
    args = parser.parse_args()
    if args.show:
        show(args.show)
        return
    if args.edit:
        edit(Path(args.edit).expanduser().resolve(strict=True))
        return
    if args.clear:
        for pidfile in ROOT.glob("pin-*/pid"):
            try:
                pid = int(pidfile.read_text())
                if str(APP).encode() in Path(f"/proc/{pid}/cmdline").read_bytes():
                    os.kill(pid, signal.SIGTERM)
            except (OSError, ValueError):
                pass
        return
    folder = new_card()
    try:
        if args.image_stdin:
            p = folder / "clipboard.png"
            data = sys.stdin.buffer.read(64 * 1024 * 1024 + 1)
            if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 64 * 1024 * 1024:
                raise ValueError("输入应为 64 MiB 以内的 PNG")
            p.write_bytes(data)
            d = file_card(p, folder)
            d["title"] = "Satty 标注"
        elif args.screenshot:
            geometry = run(["slurp"], capture_output=True, text=True).stdout.strip()
            p = folder / "capture.png"
            run(["grim", "-g", geometry, str(p)])
            d = file_card(p, folder)
            d["title"] = "截图贴屏"
        elif args.files:
            for f in args.files:
                subfolder = new_card()
                launch(file_card(f, subfolder), subfolder)
            shutil.rmtree(folder, ignore_errors=True)
            return
        else:
            d = clipboard_card(folder)
        if isinstance(d, list):
            for item in d:
                launch(item, Path(item["folder"]))
            shutil.rmtree(folder, ignore_errors=True)
        else:
            launch(d, folder)
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        subprocess.run(["notify-send", "贴屏", str(e)[:220]], check=False)
        raise


if __name__ == "__main__":
    main()
