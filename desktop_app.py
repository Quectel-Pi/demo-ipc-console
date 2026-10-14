#!/usr/bin/env python3
"""Native GTK Linux client for the ONVIF/RTSP camera console."""
import os
import queue
import signal
import threading
import subprocess
from pathlib import Path
from html import unescape
from urllib.parse import quote, urlsplit, urlunsplit

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
import cv2
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

import app as camera

if hasattr(cv2, "setLogLevel"):
    cv2.setLogLevel(0)

APP_CSS = b"""
window { background-color: #060612; color: #dbeafe; }
headerbar.app-header { background-image: none; background-color: #090718; border-bottom: 1px solid #4d2d7f; box-shadow: 0 2px 10px #02020a; }
headerbar.app-header label { color: #00f5ff; }
headerbar.app-header .subtitle { color: #a78bfa; }
headerbar.app-header button { min-width: 30px; min-height: 30px; padding: 0; color: #d8faff; background-color: #17132f; border-color: #4a3a78; }
headerbar.app-header button:hover { color: #ffffff; background-color: #e317a7; border-color: #ff4fd8; box-shadow: 0 0 8px #ff2bd6; }
.app-title { color: #00f5ff; font-size: 26px; font-weight: 700; text-shadow: 0 0 5px #007f88; }
.app-subtitle, .hint { color: #8fa3c7; font-size: 12px; }
.section-title { color: #f4e9ff; font-size: 16px; font-weight: 700; }
.card { background-color: #0e0d22; border: 1px solid #35285c; border-radius: 14px; padding: 16px; box-shadow: 0 5px 16px #02020b; }
entry { min-height: 34px; padding: 0 10px; color: #ebfaff; caret-color: #00f5ff; background-color: #090817; border: 1px solid #3b3263; border-radius: 8px; }
entry:focus { border-color: #00e7f0; box-shadow: 0 0 7px #006b73; }
entry selection { color: #070711; background-color: #00f5ff; }
button { min-height: 38px; padding: 0 14px; color: #dce9ff; background-image: none; background-color: #17142e; border: 1px solid #46386f; border-radius: 9px; }
button:hover { color: #ffffff; background-color: #242044; border-color: #00dce7; box-shadow: 0 0 6px #005d68; }
button:active { background-color: #30255a; border-color: #ff2bd6; }
.primary { color: #021214; background-color: #00e7f0; border-color: #5ffaff; font-weight: 700; box-shadow: 0 0 8px #007b84; }
.primary:hover { background-color: #5ffaff; border-color: #c5ffff; }
.record { color: #ff8ce2; border-color: #8e2674; background-color: #281124; }
.record:hover { color: #ffd1f4; border-color: #ff2bd6; box-shadow: 0 0 7px #8f176f; }
.recording { color: #ffffff; background-color: #d414a1; border-color: #ff62df; box-shadow: 0 0 10px #a10c78; }
.ptz-button { min-width: 58px; min-height: 58px; padding: 0; border-radius: 29px; font-size: 22px; }
.ptz-button:hover { color: #00f5ff; border-color: #00dce7; box-shadow: 0 0 8px #006b73; }
.ptz-stop { color: #ff65df; background-color: #281126; border-color: #8e2674; font-size: 13px; font-weight: 700; }
.ptz-stop:hover { color: #ffffff; background-color: #d414a1; border-color: #ff65df; box-shadow: 0 0 9px #a10c78; }
.zoom-button { min-width: 108px; }
.badge { padding: 5px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; }
.offline { color: #8c96b5; background-color: #19162e; border: 1px solid #332a55; }
.online { color: #00f5ff; background-color: #09262c; border: 1px solid #007e88; box-shadow: 0 0 6px #005862; }
.status-box { color: #b9c8e4; background-color: #080815; border: 1px solid #2e2850; border-radius: 10px; padding: 12px; }
.video-shell { background-color: #020207; border: 1px solid #322858; border-radius: 12px; box-shadow: inset 0 0 14px #000000; }
scale trough { min-height: 6px; border-radius: 3px; background-color: #282044; }
scale highlight { background-color: #00e7f0; border-radius: 3px; box-shadow: 0 0 5px #00838c; }
scale slider { min-width: 16px; min-height: 16px; border-radius: 8px; background-color: #ff4fd8; border: 1px solid #ffc6f1; box-shadow: 0 0 7px #a81685; }
"""


def add_style(widget, *names):
    context = widget.get_style_context()
    for name in names:
        context.add_class(name)


class CameraWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Network Camera Console")
        self.set_default_size(1220, 800)
        self.set_size_request(960, 680)
        titlebar = Gtk.HeaderBar()
        titlebar.set_title("Network Camera Console")
        titlebar.set_subtitle("ONVIF · RTSP CAMERA")
        titlebar.set_show_close_button(True)
        add_style(titlebar, "app-header")
        self.set_titlebar(titlebar)
        self.connect("destroy", self.close)
        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)
        self.capture = None
        self.preview_running = False
        self.preview_stop = None
        self.preview_thread = None
        self.preview_restart_pending = False
        self.closing = False
        self.record_process = None
        self.record_path = None
        self.record_stopping = False
        self.camera_ip = camera.CAMERA_IP
        self.stream_url = camera.RTSP_URL
        self.latest_frame = None
        self.snapshot_frame = None
        self.active_keys = set()
        self.ptz_commands = queue.Queue()
        self._apply_theme()
        self._build_ui()
        threading.Thread(target=self.ptz_command_worker, daemon=True).start()

    def _apply_theme(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(APP_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.set_margin_top(20); root.set_margin_bottom(20)
        root.set_margin_start(22); root.set_margin_end(22)
        self.add(root)
        header = Gtk.Box(spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Device Overview"); title.set_xalign(0); add_style(title, "app-title")
        subtitle = Gtk.Label(label="Live video, PTZ and recording controls"); subtitle.set_xalign(0); add_style(subtitle, "app-subtitle")
        titles.pack_start(title, False, False, 0); titles.pack_start(subtitle, False, False, 0)
        header.pack_start(titles, True, True, 0)
        self.onvif_badge = Gtk.Label(label="ONVIF Offline"); add_style(self.onvif_badge, "badge", "offline")
        self.rtsp_badge = Gtk.Label(label="RTSP Offline"); add_style(self.rtsp_badge, "badge", "offline")
        header.pack_start(self.onvif_badge, False, False, 0); header.pack_start(self.rtsp_badge, False, False, 0)
        root.pack_start(header, False, False, 0)

        settings_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); add_style(settings_card, "card")
        settings_title = Gtk.Label(label="Connection Settings"); settings_title.set_xalign(0); add_style(settings_title, "section-title")
        settings_card.pack_start(settings_title, False, False, 0)
        settings = Gtk.Grid(column_spacing=8, row_spacing=8)
        onvif_label = Gtk.Label(label="ONVIF Service URL"); onvif_label.set_xalign(0)
        settings.attach(onvif_label, 0, 0, 1, 1)
        self.onvif_entry = Gtk.Entry(); self.onvif_entry.set_text(camera.ONVIF_URL)
        self.onvif_entry.set_tooltip_text("Full URL, e.g. http://192.0.2.10:80/onvif/device_service")
        settings.attach(self.onvif_entry, 1, 0, 5, 1)
        rtsp_label = Gtk.Label(label="RTSP Stream URL"); rtsp_label.set_xalign(0)
        settings.attach(rtsp_label, 0, 1, 1, 1)
        rtsp_parts = urlsplit(camera.RTSP_URL)
        rtsp_host = f"[{rtsp_parts.hostname}]" if rtsp_parts.hostname and ":" in rtsp_parts.hostname else (rtsp_parts.hostname or "")
        if rtsp_parts.port: rtsp_host += f":{rtsp_parts.port}"
        default_rtsp = urlunsplit((rtsp_parts.scheme, rtsp_host, rtsp_parts.path, rtsp_parts.query, rtsp_parts.fragment))
        self.rtsp_entry = Gtk.Entry(); self.rtsp_entry.set_text(default_rtsp)
        self.rtsp_entry.set_tooltip_text("Full URL, e.g. rtsp://192.0.2.10:554/Streaming/Channels/101")
        settings.attach(self.rtsp_entry, 1, 1, 5, 1)
        user_label = Gtk.Label(label="Username"); user_label.set_xalign(0)
        settings.attach(user_label, 0, 2, 1, 1)
        self.user_entry = Gtk.Entry(); self.user_entry.set_text(camera.CAMERA_USER); self.user_entry.set_width_chars(10)
        settings.attach(self.user_entry, 1, 2, 1, 1)
        password_label = Gtk.Label(label="Password"); password_label.set_xalign(0)
        settings.attach(password_label, 2, 2, 1, 1)
        self.password_entry = Gtk.Entry(); self.password_entry.set_visibility(False); self.password_entry.set_text(camera.CAMERA_PASSWORD); self.password_entry.set_width_chars(10)
        settings.attach(self.password_entry, 3, 2, 1, 1)
        self.show_password = Gtk.CheckButton(label="Show password")
        self.show_password.connect("toggled", lambda button: self.password_entry.set_visibility(button.get_active()))
        settings.attach(self.show_password, 4, 2, 1, 1)
        settings_card.pack_start(settings, False, False, 0)
        root.pack_start(settings_card, False, False, 0)

        body = Gtk.Box(spacing=14)
        root.pack_start(body, True, True, 0)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12); add_style(left, "card")
        body.pack_start(left, True, True, 0)
        preview_title = Gtk.Label(label="Live Preview"); preview_title.set_xalign(0); add_style(preview_title, "section-title")
        left.pack_start(preview_title, False, False, 0)
        self.video = Gtk.Image()
        self.video.set_size_request(760, 430)
        self.video.set_tooltip_text("RTSP live preview")
        self.video_overlay = Gtk.Overlay(); add_style(self.video_overlay, "video-shell")
        self.video_overlay.add(self.video)
        self.video_placeholder = Gtk.Label(label="Connect RTSP to display live video")
        add_style(self.video_placeholder, "hint")
        self.video_overlay.add_overlay(self.video_placeholder)
        left.pack_start(self.video_overlay, True, True, 0)
        buttons = Gtk.Box(spacing=8)
        left.pack_start(buttons, False, False, 0)
        self.connect_button = Gtk.Button(label="Connect ONVIF")
        add_style(self.connect_button, "primary")
        self.connect_button.connect("clicked", self.connect_camera)
        buttons.pack_start(self.connect_button, False, False, 0)
        self.preview_button = Gtk.Button(label="Connect RTSP")
        self.preview_button.connect("clicked", self.connect_rtsp)
        buttons.pack_start(self.preview_button, False, False, 0)
        shot = Gtk.Button(label="Snapshot")
        shot.connect("clicked", self.take_snapshot); buttons.pack_start(shot, False, False, 0)
        self.record_button = Gtk.Button(label="Start Recording")
        add_style(self.record_button, "record")
        self.record_button.connect("clicked", self.toggle_record); buttons.pack_start(self.record_button, False, False, 0)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12); add_style(panel, "card")
        panel.set_size_request(310, -1); body.pack_start(panel, False, False, 0)
        panel_title = Gtk.Label(label="PTZ Control"); panel_title.set_xalign(0); add_style(panel_title, "section-title")
        panel.pack_start(panel_title, False, False, 0)
        hold_hint = Gtk.Label(label="Hold to move, release to stop"); hold_hint.set_xalign(0); add_style(hold_hint, "hint")
        panel.pack_start(hold_hint, False, False, 0)
        grid = Gtk.Grid(column_spacing=9, row_spacing=9); grid.set_halign(Gtk.Align.CENTER)
        controls = [(0,0,"↖","upleft"),(1,0,"↑","up"),(2,0,"↗","upright"),(0,1,"←","left"),(1,1,"●","stop"),(2,1,"→","right"),(0,2,"↙","downleft"),(1,2,"↓","down"),(2,2,"↘","downright")]
        for x,y,label,action in controls:
            b = Gtk.Button(label="STOP" if action == "stop" else label); add_style(b, "ptz-button")
            b.set_tooltip_text("Stop PTZ" if action == "stop" else f"Hold to move {action}")
            if action == "stop":
                add_style(b, "ptz-stop"); b.connect("clicked", self.stop_ptz)
            else:
                b.connect("pressed", self.start_ptz, action); b.connect("released", self.stop_ptz)
            grid.attach(b,x,y,1,1)
        panel.pack_start(grid, False, False, 4)
        speed_label = Gtk.Label(label="Movement Speed"); speed_label.set_xalign(0)
        panel.pack_start(speed_label, False, False, 0)
        self.speed_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.1, 1.0, 0.1)
        self.speed_scale.set_value(0.5); self.speed_scale.set_draw_value(True)
        self.speed_scale.connect("format-value", lambda _scale, value: f"{int(value * 100)}%")
        panel.pack_start(self.speed_scale, False, False, 0)
        zoom = Gtk.Box(spacing=8); zoom.set_halign(Gtk.Align.CENTER)
        for label, action in (("−  Zoom Out", "zoom_out"),("＋  Zoom In", "zoom_in")):
            b=Gtk.Button(label=label); add_style(b, "zoom-button")
            b.connect("pressed",self.start_ptz,action); b.connect("released",self.stop_ptz); zoom.pack_start(b,False,False,0)
        panel.pack_start(zoom, False, False, 0)
        keyboard_hint = Gtk.Label(label="Shortcuts: Arrows / WASD · Q/E zoom · Space stop")
        keyboard_hint.set_line_wrap(True); keyboard_hint.set_xalign(0); add_style(keyboard_hint, "hint")
        panel.pack_start(keyboard_hint, False, False, 0)
        self.ptz_state = Gtk.Label(label="PTZ ready"); self.ptz_state.set_xalign(0); add_style(self.ptz_state, "hint")
        panel.pack_start(self.ptz_state, False, False, 0)
        self.status = Gtk.Label(label="Ready"); self.status.set_xalign(0); self.status.set_yalign(0); self.status.set_line_wrap(True)
        add_style(self.status, "status-box")
        panel.pack_end(self.status, True, True, 0)
        GLib.timeout_add(100, self.present_latest_frame)

    def terminal_log(self, message, level="INFO"):
        stamp = __import__('datetime').datetime.now().strftime("%H:%M:%S")
        print(f"[{stamp}] [{level}] {message}", flush=True)

    def write_status(self, message, detail=None, level="INFO"):
        self.terminal_log(detail or message, level)
        def update(): self.status.set_text(message); return False
        GLib.idle_add(update)

    def set_badge(self, label, connected, text):
        context = label.get_style_context()
        context.remove_class("online"); context.remove_class("offline")
        context.add_class("online" if connected else "offline")
        label.set_text(text)
        return False

    def set_ptz_state(self, text):
        GLib.idle_add(lambda: self.ptz_state.set_text(text) or False)

    def start_ptz(self, _button, action):
        self.enqueue_ptz(action)

    def stop_ptz(self, *_args):
        self.enqueue_ptz("stop")

    def enqueue_ptz(self, action):
        speed = self.speed_scale.get_value()
        self.ptz_commands.put((action, speed))
        labels = {
            "up": "Moving up", "down": "Moving down", "left": "Moving left", "right": "Moving right",
            "upleft": "Moving up-left", "upright": "Moving up-right", "downleft": "Moving down-left", "downright": "Moving down-right",
            "zoom_in": "Zooming in", "zoom_out": "Zooming out", "stop": "PTZ stopped",
        }
        self.ptz_state.set_text(labels.get(action, action))

    def ptz_command_worker(self):
        while True:
            action, speed = self.ptz_commands.get()
            try:
                camera.ptz(action, speed)
            except Exception as exc:
                self.write_status("PTZ command failed", f"PTZ {action} failed: {exc}", "ERROR")
            finally:
                self.ptz_commands.task_done()

    def keyboard_ptz_action(self):
        if "zoom_in" in self.active_keys: return "zoom_in"
        if "zoom_out" in self.active_keys: return "zoom_out"
        vertical = -1 if "up" in self.active_keys else (1 if "down" in self.active_keys else 0)
        horizontal = -1 if "left" in self.active_keys else (1 if "right" in self.active_keys else 0)
        return {
            (-1, -1): "upleft", (0, -1): "up", (1, -1): "upright",
            (-1, 0): "left", (1, 0): "right",
            (-1, 1): "downleft", (0, 1): "down", (1, 1): "downright",
        }.get((horizontal, vertical), "stop")

    def key_token(self, keyval):
        key = Gdk.keyval_to_lower(keyval)
        return {
            Gdk.KEY_Up: "up", Gdk.KEY_w: "up",
            Gdk.KEY_Down: "down", Gdk.KEY_s: "down",
            Gdk.KEY_Left: "left", Gdk.KEY_a: "left",
            Gdk.KEY_Right: "right", Gdk.KEY_d: "right",
            Gdk.KEY_q: "zoom_out", Gdk.KEY_e: "zoom_in",
            Gdk.KEY_space: "stop",
        }.get(key)

    def on_key_press(self, _widget, event):
        if isinstance(self.get_focus(), Gtk.Entry): return False
        token = self.key_token(event.keyval)
        if not token: return False
        if token == "stop":
            self.active_keys.clear(); self.enqueue_ptz("stop"); return True
        if token not in self.active_keys:
            self.active_keys.add(token); self.enqueue_ptz(self.keyboard_ptz_action())
        return True

    def on_key_release(self, _widget, event):
        if isinstance(self.get_focus(), Gtk.Entry): return False
        token = self.key_token(event.keyval)
        if not token or token == "stop": return False
        self.active_keys.discard(token)
        self.enqueue_ptz(self.keyboard_ptz_action())
        return True

    def apply_credentials(self):
        user = self.user_entry.get_text().strip() or "admin"
        password = self.password_entry.get_text()
        camera.CAMERA_USER = camera.ONVIF_USER = user
        camera.CAMERA_PASSWORD = camera.ONVIF_PASSWORD = password
        return user, password

    def authenticated_rtsp_url(self, url):
        user, password = self.apply_credentials()
        parsed = urlsplit(unescape(url.strip()))
        if parsed.scheme.lower() != "rtsp" or not parsed.hostname:
            raise ValueError("Invalid RTSP URL")
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        if parsed.port:
            host += f":{parsed.port}"
        netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

    def connect_camera(self, *_):
        raw_url = self.onvif_entry.get_text().strip()
        try:
            parsed = urlsplit(raw_url)
            if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
                raise ValueError
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        except ValueError:
            self.write_status("Invalid ONVIF URL", f"Invalid ONVIF URL entered: {raw_url}", "ERROR")
            return
        self.camera_ip = parsed.hostname
        camera.ONVIF_URL = raw_url
        camera.ONVIF_PORT = str(port)
        camera.CAMERA_IP = parsed.hostname
        self.apply_credentials()
        self.set_badge(self.onvif_badge, False, "ONVIF Connecting…")
        self.connect_button.set_sensitive(False); self.write_status("Connecting ONVIF…", f"Connecting to ONVIF service {raw_url}")
        def worker():
            reachable, detail = camera.tcp_probe(parsed.hostname, port)
            result = camera.init_onvif() if reachable else {
                "ok": False,
                "message": f"Cannot reach {parsed.hostname}:{port}",
                "detail": detail,
            }
            GLib.idle_add(self.connection_result, result)
        threading.Thread(target=worker, daemon=True).start()

    def connection_result(self, result):
        self.connect_button.set_sensitive(True)
        if result.get("ok"):
            self.set_badge(self.onvif_badge, True, "ONVIF Online")
            discovered = result.get("stream_uri")
            if discovered:
                current = self.rtsp_entry.get_text().strip()
                if not current or current.endswith("/stream1") or current.endswith("/media/video1"):
                    self.rtsp_entry.set_text(unescape(discovered))
            device = f"{result.get('manufacturer','')} {result.get('model','')}".strip()
            self.write_status("ONVIF ready", f"ONVIF initialized for {device or 'camera'}")
        else:
            self.set_badge(self.onvif_badge, False, "ONVIF Failed")
            detail = f"{result.get('message', 'ONVIF connection failed')}: {result.get('detail', '')}".rstrip(": ")
            self.write_status("ONVIF connection failed", detail, "ERROR")
        return False

    def connect_rtsp(self, *_):
        raw_url = self.rtsp_entry.get_text().strip() or camera.state.get("media_url") or camera.RTSP_URL
        try:
            url = self.authenticated_rtsp_url(raw_url)
        except ValueError as exc:
            self.write_status(str(exc))
            return
        if self.preview_running and url == self.stream_url:
            self.write_status("RTSP already running")
            return
        self.stream_url = url
        self.set_badge(self.rtsp_badge, False, "RTSP Connecting…")
        self.write_status("Connecting RTSP…", f"Opening RTSP stream at {urlsplit(url).hostname}:{urlsplit(url).port or 554}")
        if self.preview_stop:
            self.preview_stop.set()
        if self.preview_thread and self.preview_thread.is_alive():
            self.preview_restart_pending = True
            self.write_status("Switching RTSP stream…")
            return
        self.start_preview()

    def start_preview(self):
        if self.preview_thread and self.preview_thread.is_alive():
            return
        stop_event = threading.Event()
        self.preview_stop = stop_event
        self.preview_running = True
        stream_url = self.stream_url
        def reader():
            cap = None
            try:
                parsed = urlsplit(stream_url)
                reachable, detail = camera.tcp_probe(parsed.hostname, parsed.port or 554)
                if not reachable:
                    GLib.idle_add(self.set_badge, self.rtsp_badge, False, "RTSP Unreachable")
                    GLib.idle_add(self.write_status, "RTSP network unavailable", f"Cannot reach RTSP endpoint {parsed.hostname}:{parsed.port or 554}: {detail}", "ERROR")
                    return
                try:
                    cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG, [
                        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 6000,
                        cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000,
                    ])
                except (TypeError, cv2.error):
                    cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
                self.capture = cap
                if not cap.isOpened():
                    GLib.idle_add(self.set_badge, self.rtsp_badge, False, "RTSP Failed")
                    GLib.idle_add(self.write_status, "RTSP connection failed", "OpenCV could not open the RTSP stream; check URL and credentials", "ERROR")
                    return
                GLib.idle_add(self.set_badge, self.rtsp_badge, True, "RTSP Live")
                GLib.idle_add(self.write_status, "RTSP connected")
                while not stop_event.is_set() and cap.isOpened():
                    ok, frame=cap.read()
                    if not ok:
                        if not stop_event.is_set():
                            GLib.idle_add(self.set_badge, self.rtsp_badge, False, "RTSP Interrupted")
                            GLib.idle_add(self.write_status, "RTSP interrupted", "RTSP frame read failed", "ERROR")
                        break
                    frame=cv2.resize(frame,(760,430),interpolation=cv2.INTER_AREA)
                    ok, encoded=cv2.imencode('.jpg',frame,[int(cv2.IMWRITE_JPEG_QUALITY),72])
                    if ok: self.latest_frame=encoded.tobytes()
            except Exception as exc:
                if not stop_event.is_set():
                    GLib.idle_add(self.set_badge, self.rtsp_badge, False, "RTSP Error")
                    GLib.idle_add(self.write_status, "RTSP error", f"RTSP preview error: {exc}", "ERROR")
            finally:
                if cap is not None:
                    cap.release()
                if self.capture is cap:
                    self.capture = None
                if self.preview_stop is stop_event:
                    self.preview_running = False
                    if self.preview_restart_pending and not self.closing:
                        self.preview_restart_pending = False
                        GLib.timeout_add(100, self.start_preview)
        self.preview_thread = threading.Thread(target=reader,daemon=True)
        self.preview_thread.start()

    def present_latest_frame(self):
        data, self.latest_frame = self.latest_frame, None
        if data:
            self.snapshot_frame = data
            self.video_placeholder.hide()
            self.show_frame(data)
        return self.preview_running or self.get_visible()

    def show_frame(self, data):
        loader=GdkPixbuf.PixbufLoader.new_with_type("jpeg")
        try:
            loader.write(data); loader.close(); self.video.set_from_pixbuf(loader.get_pixbuf())
        except Exception: pass
        return False

    def take_snapshot(self, *_):
        def worker():
            try:
                if camera.state.get("snapshot_uri"):
                    name, _ = camera.capture()
                    source = "ONVIF snapshot"
                else:
                    frame = self.snapshot_frame
                    if not frame:
                        raise RuntimeError("No preview frame is available yet")
                    name = __import__('datetime').datetime.now().strftime("%Y%m%d-%H%M%S.jpg")
                    (camera.SNAPSHOTS / name).write_bytes(frame)
                    source = "RTSP preview frame"
                GLib.idle_add(self.write_status, "Snapshot saved", f"Snapshot saved to snapshots/{name} using {source}")
            except Exception as exc:
                GLib.idle_add(self.write_status, "Snapshot failed", f"Snapshot failed: {exc}", "ERROR")
        threading.Thread(target=worker,daemon=True).start()

    def toggle_record(self, *_):
        if self.record_process and self.record_process.poll() is None:
            self.record_stopping = True
            self.record_button.set_sensitive(False)
            self.write_status("Finalizing recording…")
            self.record_process.send_signal(signal.SIGINT)
            return
        name = __import__('datetime').datetime.now().strftime("recording-%Y%m%d-%H%M%S.mp4")
        target = camera.RECORDINGS / name
        try:
            self.record_stopping = False
            self.record_path = target
            self.record_process=subprocess.Popen(
                camera.recording_command(self.stream_url, target),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            add_style(self.record_button, "recording")
            self.record_button.set_label("●  Stop Recording"); self.write_status("Recording…", f"Recording to recordings/{name}")
            threading.Thread(target=self.monitor_recording, args=(self.record_process, target), daemon=True).start()
        except Exception as exc: self.write_status("Recording failed", f"Could not start recording: {exc}", "ERROR")

    def monitor_recording(self, process, target):
        _stdout, stderr = process.communicate()
        GLib.idle_add(self.recording_finished, process, target, stderr)

    def recording_finished(self, process, target, stderr):
        if self.record_process is not process:
            return False
        was_stopping = self.record_stopping
        self.record_process = None
        self.record_path = None
        self.record_stopping = False
        self.record_button.set_sensitive(True)
        self.record_button.get_style_context().remove_class("recording")
        self.record_button.set_label("Start Recording")
        size = target.stat().st_size if target.exists() else 0
        if size > 1024 and (process.returncode == 0 or was_stopping):
            self.write_status("Recording saved", f"Recording saved to recordings/{target.name} ({size / 1024 / 1024:.1f} MB)")
        else:
            lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
            detail = lines[-1] if lines else f"ffmpeg exit code {process.returncode}"
            self.write_status("Recording failed", detail, "ERROR")
        return False

    def close(self, *_):
        self.terminal_log("Application shutting down")
        self.closing=True
        self.preview_running=False
        if self.preview_stop: self.preview_stop.set()
        if self.record_process and self.record_process.poll() is None:
            self.record_process.send_signal(signal.SIGINT)
        Gtk.main_quit()


if __name__ == "__main__":
    if not Gtk.init_check()[0]:
        raise SystemExit("Unable to open the Linux desktop. Run this application in a session with DISPLAY available.")
    win=CameraWindow(); win.show_all(); win.terminal_log("Network Camera Console started"); Gtk.main()
