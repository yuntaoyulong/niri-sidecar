#!/usr/bin/python3
"""On-demand PipeWire window previews; video frames remain in memory."""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from niri_sidecar.common import theme, rgba
import gi

gi.require_version("Gst", "1.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gio, GLib, Gst, Gtk, Gdk

Gst.init(None)
BASE = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "niri-sidecar-preview"
SOCKET = BASE / "control.sock"
DEST = "org.gnome.Mutter.ScreenCast"
SESSION = DEST + ".Session"
PREVIEW_WIDTH = 360
PREVIEW_HEIGHT = 220
MAX_TEXTURE_WIDTH = 3840
MAX_TEXTURE_HEIGHT = 2160


def windows():
    return json.loads(subprocess.check_output(["niri", "msg", "-j", "windows"], text=True, timeout=2))


class PreviewPicture(Gtk.Picture):
    def __init__(self, width, height):
        super().__init__()
        self.preview_width = width
        self.preview_height = height

    def do_measure(self, orientation, for_size):
        # Card dimensions stay independent of the native-resolution texture.
        size = self.preview_width if orientation == Gtk.Orientation.HORIZONTAL else self.preview_height
        return size, size, -1, -1


class Stream:
    def __init__(self, window_id, on_frame=None):
        self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.pipeline = None
        self.bus = None
        self.bus_handler = None
        self.sink = None
        self.sink_handler = None
        self.source_pad = None
        self.probe_id = None
        self.frames = 0
        self.unique = set()
        self.latencies = []
        self.started = time.monotonic()
        self.on_frame = on_frame
        self.last_delivery = 0
        self.delivered_frames = 0
        self.pending_frame = None
        self.delivery_queued = False
        self.delivery_lock = threading.Lock()
        self.pixel_stats = {}
        window = next((w for w in windows() if w["id"] == int(window_id)), {})
        source_width, source_height = window.get("layout", {}).get(
            "window_size", [PREVIEW_WIDTH, PREVIEW_HEIGHT]
        )
        self.source_width, self.source_height = source_width, source_height
        # Keep native pixels; Gtk performs the only downscale at display time.
        scale = min(1, MAX_TEXTURE_WIDTH / max(source_width, 1), MAX_TEXTURE_HEIGHT / max(source_height, 1))
        self.frame_width = max(2, int(source_width * scale / 2) * 2)
        self.frame_height = max(2, int(source_height * scale / 2) * 2)
        self.closed = False
        self.subscription = None
        self.session = self.call(
            "/org/gnome/Mutter/ScreenCast", DEST, "CreateSession", GLib.Variant("(a{sv})", ({},))
        )[0]
        try:
            path = self.call(
                self.session,
                SESSION,
                "RecordWindow",
                GLib.Variant(
                    "(a{sv})",
                    ({"window-id": GLib.Variant("t", int(window_id)), "cursor-mode": GLib.Variant("u", 0)},),
                ),
            )[0]
            self.subscription = self.connection.signal_subscribe(
                DEST,
                DEST + ".Stream",
                "PipeWireStreamAdded",
                path,
                None,
                Gio.DBusSignalFlags.NONE,
                self.node_added,
                None,
            )
            self.call(self.session, SESSION, "Start")
        except Exception:
            self.stop()
            raise

    def call(self, path, interface, method, args=None):
        return self.connection.call_sync(
            DEST, path, interface, method, args, None, Gio.DBusCallFlags.NONE, 3000, None
        ).unpack()

    def node_added(self, conn, sender, path, interface, signal, args, data):
        if self.closed or self.pipeline is not None:
            return
        node = args.unpack()[0]
        self.pipeline = Gst.parse_launch(
            f"pipewiresrc name=capture path={node} do-timestamp=true "
            "! video/x-raw(memory:DMABuf),pixel-aspect-ratio=1/1 "
            "! glupload ! glcolorconvert "
            "! video/x-raw(memory:GLMemory),format=BGRA,pixel-aspect-ratio=1/1 "
            "! gldownload ! video/x-raw,format=BGRA,pixel-aspect-ratio=1/1 "
            "! videocrop name=contentcrop ! videoconvert ! videoscale method=lanczos "
            f"! video/x-raw,format=RGBA,width={self.frame_width},height={self.frame_height},pixel-aspect-ratio=1/1 "
            "! appsink name=frames emit-signals=true max-buffers=1 drop=true sync=false"
        )
        self.source_pad = self.pipeline.get_by_name("capture").get_static_pad("src")
        self.probe_id = self.source_pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, self.source_event)
        self.sink = self.pipeline.get_by_name("frames")
        self.sink_handler = self.sink.connect("new-sample", self.sample)
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus_handler = self.bus.connect("message::error", self.error)
        self.pipeline.set_state(Gst.State.PLAYING)

    def source_event(self, pad, info):
        event = info.get_event()
        if event.type == Gst.EventType.CAPS:
            caps = event.parse_caps().get_structure(0)
            width = caps.get_value("width")
            height = caps.get_value("height")
            # Niri exports the surrounding effect bounds along with the window.
            extra_width = max(0, width - self.source_width)
            extra_height = max(0, height - self.source_height)
            crop = self.pipeline.get_by_name("contentcrop")
            crop.set_property("left", extra_width // 2)
            crop.set_property("right", extra_width - extra_width // 2)
            crop.set_property("top", extra_height // 2)
            crop.set_property("bottom", extra_height - extra_height // 2)
        return Gst.PadProbeReturn.OK

    def error(self, bus, message):
        error, detail = message.parse_error()
        print("Preview stream:", error.message, file=sys.stderr, flush=True)
        self.stop()

    def sample(self, sink):
        sample = sink.emit("pull-sample")
        if not sample:
            return Gst.FlowReturn.OK
        buffer = sample.get_buffer()
        self.frames += 1
        now = time.monotonic()
        if now - self.last_delivery < 0.05:
            return Gst.FlowReturn.OK
        self.last_delivery = now
        mapped, info = buffer.map(Gst.MapFlags.READ)
        if not mapped:
            return Gst.FlowReturn.OK
        try:
            pixels = bytes(info.data)
        finally:
            buffer.unmap(info)
        if pixels and not self.pixel_stats:
            # Sample pixels for diagnostics without scanning large frames in Python.
            channels = [pixels[i::256] for i in range(4)]
            self.pixel_stats = {
                "bytes": len(pixels),
                "caps": sample.get_caps().to_string(),
                "source_caps": self.pipeline.get_by_name("capture")
                .get_static_pad("src")
                .get_current_caps()
                .to_string(),
                "rgba_mean": [round(sum(c) / len(c), 1) for c in channels],
                "alpha_range": [min(channels[3]), max(channels[3])],
            }
        self.unique.add(hashlib.blake2s(pixels[::64], digest_size=8).digest())
        if len(self.unique) > 256:
            self.unique.pop()
        if self.on_frame:
            with self.delivery_lock:
                self.pending_frame = (pixels, now)
                if not self.delivery_queued:
                    self.delivery_queued = True
                    GLib.idle_add(self.deliver)
        return Gst.FlowReturn.OK

    def deliver(self):
        with self.delivery_lock:
            frame = self.pending_frame
            self.pending_frame = None
            self.delivery_queued = False
        if frame is None:
            return GLib.SOURCE_REMOVE
        pixels, received = frame
        if not self.closed:
            texture = Gdk.MemoryTexture.new(
                self.frame_width,
                self.frame_height,
                Gdk.MemoryFormat.R8G8B8A8,
                GLib.Bytes.new(pixels),
                self.frame_width * 4,
            )
            self.on_frame(texture)
            self.delivered_frames += 1
            self.latencies.append((time.monotonic() - received) * 1000)
            self.latencies = self.latencies[-120:]
        return GLib.SOURCE_REMOVE

    def stats(self):
        elapsed = time.monotonic() - self.started
        return {
            "frames": self.frames,
            "different_frames": len(self.unique),
            "texture_size": [self.frame_width, self.frame_height],
            "displayed_frames": self.delivered_frames,
            "displayed_fps": round(self.delivered_frames / max(elapsed, 0.01), 1),
            "pixels": self.pixel_stats,
            "seconds": round(elapsed, 2),
            "received_fps": round(self.frames / max(elapsed, 0.01), 1),
            "ui_queue_delay_ms": round(sum(self.latencies) / len(self.latencies), 1)
            if self.latencies
            else None,
        }

    def stop(self):
        if self.closed:
            return
        self.closed = True
        if self.subscription:
            self.connection.signal_unsubscribe(self.subscription)
            self.subscription = None
        # Stop streaming threads before releasing callbacks and their targets.
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.bus:
            self.bus.disconnect(self.bus_handler)
            self.bus.remove_signal_watch()
            self.bus = None
            self.bus_handler = None
        if self.sink:
            self.sink.disconnect(self.sink_handler)
            self.sink = None
            self.sink_handler = None
        if self.source_pad:
            self.source_pad.remove_probe(self.probe_id)
            self.source_pad = None
            self.probe_id = None
        self.pipeline = None
        with self.delivery_lock:
            self.pending_frame = None
            self.on_frame = None
        try:
            self.call(self.session, SESSION, "Stop")
        except GLib.Error:
            pass


class Preview:
    def __init__(self):
        self.app = Gtk.Application(application_id="local.niri.LivePreview")
        self.app.connect("activate", self.activate)
        self.streams = []
        self.owner = ""
        self.inside = False
        self.hide_timer = 0
        self.frame_box = None
        self.target_ids = ()
        self.preview_request = None
        self.refresh_timer = 0

    def activate(self, app):
        app.hold()
        self.window = Gtk.ApplicationWindow(application=app, title="窗口实时预览")
        self.window.set_decorated(False)
        lib = ctypes.CDLL("libgtk4-layer-shell.so.0")
        self.layer = lib
        for name, types in {
            "gtk_layer_init_for_window": [ctypes.c_void_p],
            "gtk_layer_set_namespace": [ctypes.c_void_p, ctypes.c_char_p],
            "gtk_layer_set_layer": [ctypes.c_void_p, ctypes.c_int],
            "gtk_layer_set_keyboard_mode": [ctypes.c_void_p, ctypes.c_int],
            "gtk_layer_set_anchor": [ctypes.c_void_p, ctypes.c_int, ctypes.c_bool],
            "gtk_layer_set_margin": [ctypes.c_void_p, ctypes.c_int, ctypes.c_int],
            "gtk_layer_set_monitor": [ctypes.c_void_p, ctypes.c_void_p],
        }.items():
            f = getattr(lib, name)
            f.argtypes = types
            f.restype = None
        get_pointer = ctypes.pythonapi.PyCapsule_GetPointer
        get_pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
        get_pointer.restype = ctypes.c_void_p
        self.pointer = get_pointer(self.window.__gpointer__, None)
        self.get_pointer = get_pointer
        lib.gtk_layer_init_for_window(self.pointer)
        lib.gtk_layer_set_namespace(self.pointer, b"niri-sidecar:preview")
        lib.gtk_layer_set_layer(self.pointer, 3)
        lib.gtk_layer_set_keyboard_mode(self.pointer, 0)
        motion = Gtk.EventControllerMotion.new()
        motion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        motion.connect("enter", self.enter)
        motion.connect("leave", self.leave)
        self.window.add_controller(motion)
        self.style_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.style_provider, 600)
        self.style_stamp = None
        self.update_style()
        GLib.timeout_add(1000, self.update_style)
        BASE.mkdir(mode=0o700, exist_ok=True)
        BASE.chmod(0o700)
        SOCKET.unlink(missing_ok=True)
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(str(SOCKET))
        SOCKET.chmod(0o600)
        self.server.listen(8)
        threading.Thread(target=self.listen, daemon=True).start()

    def update_style(self):
        value = theme()
        background = rgba(value["background"])
        text = value["text"]
        border = rgba(value["outline"])
        self.style_provider.load_from_string(
            f"window{{background:{background};border-radius:10px;border:1px solid {border};}}"
            f"button,tooltip{{padding:6px;border-radius:10px;background:{background};color:{text};border:1px solid {border};box-shadow:none;}}"
            f"button:hover{{background:{background};}} label{{color:{text};}}"
        )
        return GLib.SOURCE_CONTINUE

    def listen(self):
        while True:
            conn, _ = self.server.accept()
            try:
                conn.settimeout(2)
                request = json.loads(conn.makefile("rb").readline(4096))
                if request.get("op") == "stats":
                    conn.sendall(
                        json.dumps(
                            {
                                "visible": self.window.get_visible(),
                                "inside": self.inside,
                                "owner": self.owner,
                                "streams": [s.stats() for s in self.streams],
                            }
                        ).encode()
                        + b"\n"
                    )
                    continue
                GLib.idle_add(self.request, request)
                conn.sendall(b'{"accepted":true}\n')
            except (ValueError, OSError):
                pass
            finally:
                conn.close()

    def request(self, r):
        if r.get("op") == "hide":
            if not r.get("app"):
                self.hide()
            elif r["app"] == self.owner:
                self.defer_hide()
        elif r.get("op") == "show":
            self.show(r)
        return GLib.SOURCE_REMOVE

    def enter(self, controller, x, y):
        self.inside = True
        self.cancel_hide()

    def leave(self, controller):
        self.inside = False
        self.defer_hide()

    def cancel_hide(self):
        if self.hide_timer:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = 0

    def defer_hide(self):
        self.cancel_hide()

        def close():
            self.hide_timer = 0
            if not self.inside:
                self.hide()
            return GLib.SOURCE_REMOVE

        self.hide_timer = GLib.timeout_add(350, close)

    def hide(self):
        self.cancel_hide()
        if self.refresh_timer:
            GLib.source_remove(self.refresh_timer)
            self.refresh_timer = 0
        self.window.set_visible(False)
        self.inside = False
        for stream in self.streams:
            stream.stop()
        self.streams = []
        self.owner = ""
        self.target_ids = ()
        self.preview_request = None

    def refresh(self):
        request = self.preview_request
        self.refresh_timer = 0
        if request:
            try:
                if not self.hide_timer:
                    self.show(request, refreshing=True)
            except (subprocess.SubprocessError, OSError, ValueError) as error:
                print(error, file=sys.stderr, flush=True)
            if self.preview_request and not self.refresh_timer:
                self.refresh_timer = GLib.timeout_add(1000, self.refresh)
        return GLib.SOURCE_REMOVE

    def show(self, r, refreshing=False):
        app_id = r.get("app", "")
        normalize = lambda value: value.lower().removesuffix(".desktop")
        targets = [w for w in windows() if normalize(w.get("app_id", "")) == normalize(app_id)]
        targets.sort(key=lambda w: (w.get("focus_timestamp") or {}).get("secs", 0), reverse=True)
        if not targets:
            self.hide()
            return
        if not refreshing:
            self.cancel_hide()
        target_ids = tuple(sorted(w["id"] for w in targets))
        same_placement = self.preview_request and all(
            self.preview_request.get(key) == r.get(key)
            for key in ("layout", "screen", "edge", "right_margin")
        )
        if self.owner == app_id and self.target_ids == target_ids and self.streams and same_placement:
            return
        self.hide()
        self.owner = app_id
        self.target_ids = target_ids
        self.preview_request = dict(r)
        monitors = Gdk.Display.get_default().get_monitors()
        selected_monitor = monitors.get_item(0)
        for i in range(monitors.get_n_items()):
            monitor = monitors.get_item(i)
            if monitor.get_connector() == r.get("screen"):
                self.layer.gtk_layer_set_monitor(self.pointer, self.get_pointer(monitor.__gpointer__, None))
                selected_monitor = monitor
                break
        # Center near the Dock; follow its edge without taking keyboard focus.
        edge = {"left": 0, "right": 1, "top": 2, "bottom": 3}.get(r.get("edge"), 3)
        for e in range(4):
            self.layer.gtk_layer_set_anchor(self.pointer, e, e == edge)
            self.layer.gtk_layer_set_margin(self.pointer, e, 82 if e == edge else 0)
        sidebar = r.get("layout") == "sidebar"
        if sidebar:
            self.layer.gtk_layer_set_anchor(self.pointer, 1, True)
            self.layer.gtk_layer_set_margin(self.pointer, 1, r.get("right_margin", 304))
            self.layer.gtk_layer_set_margin(self.pointer, 3, 56)
        vertical = edge < 2 or sidebar
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=6
        )
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        viewport = Gtk.ScrolledWindow()
        viewport.set_policy(
            Gtk.PolicyType.NEVER if vertical else Gtk.PolicyType.AUTOMATIC,
            Gtk.PolicyType.AUTOMATIC if vertical else Gtk.PolicyType.NEVER,
        )
        viewport.set_propagate_natural_width(True)
        viewport.set_propagate_natural_height(True)
        geometry = selected_monitor.get_geometry()
        viewport.set_max_content_width(max(1, geometry.width - 180))
        viewport.set_max_content_height(
            max(1, min(650, geometry.height - 180) if sidebar else geometry.height - 180)
        )
        viewport.set_child(box)
        self.window.set_child(viewport)
        for w in targets:
            source_width, source_height = w.get("layout", {}).get(
                "window_size", [PREVIEW_WIDTH, PREVIEW_HEIGHT]
            )
            scale = min(PREVIEW_WIDTH / max(source_width, 1), PREVIEW_HEIGHT / max(source_height, 1))
            preview_width = max(1, round(source_width * scale))
            preview_height = max(1, round(source_height * scale))
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            picture = PreviewPicture(preview_width, preview_height)
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            picture.set_can_shrink(True)
            label = Gtk.Label(label=w.get("title", ""))
            label.set_max_width_chars(max(1, preview_width // 8))
            label.set_ellipsize(3)
            card.append(picture)
            card.append(label)
            button = Gtk.Button(child=card)
            button.set_halign(Gtk.Align.CENTER)
            button.set_valign(Gtk.Align.END)
            button.set_tooltip_text(w.get("title", ""))
            button.connect("clicked", lambda b, wid=w["id"]: self.select(wid))
            box.append(button)
            try:
                self.streams.append(Stream(w["id"], picture.set_paintable))
            except GLib.Error as error:
                label.set_text("预览暂不可用")
                print(error.message, file=sys.stderr, flush=True)
        self.window.set_visible(True)
        self.refresh_timer = GLib.timeout_add(1000, self.refresh)

    def select(self, window_id):
        self.hide()
        subprocess.run(
            ["niri", "msg", "action", "focus-window", "--id", str(window_id)], stdout=subprocess.DEVNULL
        )


def main():
    parser = argparse.ArgumentParser(description="Niri 内存实时窗口预览")
    parser.add_argument("op", choices=["daemon", "show", "hide", "probe", "stats"])
    parser.add_argument("app", nargs="?", default="")
    parser.add_argument("--screen", default="")
    parser.add_argument("--edge", default="bottom")
    parser.add_argument("--window-id", type=int)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--layout", choices=["dock", "sidebar"], default="dock")
    parser.add_argument("--right-margin", type=int, default=304)
    args = parser.parse_args()
    if args.op == "daemon":
        app = Preview()
        try:
            app.app.run([sys.argv[0]])
        finally:
            for stream in app.streams:
                stream.stop()
            SOCKET.unlink(missing_ok=True)
        return
    if args.op == "probe":
        loop = GLib.MainLoop()
        stream = Stream(args.window_id)
        GLib.timeout_add(int(args.seconds * 1000), lambda: (loop.quit(), False)[1])
        try:
            loop.run()
            print(json.dumps(stream.stats()))
        finally:
            stream.stop()
        return
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(2)
        s.connect(str(SOCKET))
        s.sendall(
            json.dumps(
                {
                    "op": args.op,
                    "app": args.app,
                    "screen": args.screen,
                    "edge": args.edge,
                    "layout": args.layout,
                    "right_margin": args.right_margin,
                }
            ).encode()
            + b"\n"
        )
        print(s.makefile("rb").readline(65536).decode().strip())


if __name__ == "__main__":
    main()
