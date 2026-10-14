#!/usr/bin/env python3
"""Shared ONVIF and RTSP helpers for the native Linux camera application."""
from pathlib import Path
import base64
import datetime as dt
import hashlib
import os
import re
import socket
import threading
import urllib.error
import urllib.request
import datetime

ROOT = Path(__file__).parent
RECORDINGS = ROOT / "recordings"
SNAPSHOTS = ROOT / "snapshots"
RECORDINGS.mkdir(exist_ok=True)
SNAPSHOTS.mkdir(exist_ok=True)

CAMERA_IP = os.getenv("CAMERA_IP", "192.0.2.10")
CAMERA_USER = os.getenv("CAMERA_USER", "admin")
CAMERA_PASSWORD = os.getenv("CAMERA_PASSWORD", "")
ONVIF_USER = os.getenv("ONVIF_USER", CAMERA_USER)
ONVIF_PASSWORD = os.getenv("ONVIF_PASSWORD", CAMERA_PASSWORD)
ONVIF_PORT = os.getenv("ONVIF_PORT", "80")
ONVIF_URL = os.getenv("ONVIF_URL", f"http://{CAMERA_IP}:{ONVIF_PORT}/onvif/device_service")
RTSP_URL = os.getenv("RTSP_URL", f"rtsp://{CAMERA_USER}:{CAMERA_PASSWORD}@{CAMERA_IP}:554/media/video1")

state = {"profile_token": None, "ptz_url": None, "snapshot_uri": None, "media_url": None}
lock = threading.Lock()

def runtime_log(message, level="INFO"):
    stamp = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] [{level}] {message}", flush=True)

def tcp_probe(host, port, timeout=2):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, ""
    except OSError as exc:
        return False, str(exc)

def recording_command(rtsp_url, target):
    """Copy HEVC video and convert G.711/PCM audio to MP4-compatible AAC."""
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "warning",
        "-rtsp_transport", "tcp", "-fflags", "+genpts+discardcorrupt",
        "-i", rtsp_url,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "copy", "-tag:v", "hvc1",
        "-c:a", "aac", "-b:a", "64k",
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        "-y", str(target),
    ]

def soap(action, body, url=None, timeout=5):
    url = url or ONVIF_URL
    nonce = os.urandom(20)
    created = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    password_digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + ONVIF_PASSWORD.encode()).digest()).decode()
    nonce_text = base64.b64encode(nonce).decode()
    envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
 <s:Header><wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><wsse:UsernameToken><wsse:Username>{xml(ONVIF_USER)}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_text}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></s:Header>
 <s:Body><{action}>{body}</{action}></s:Body>
</s:Envelope>'''
    action_name = action.split(":")[-1]
    action_namespace = {
        "GetDeviceInformation": "http://www.onvif.org/ver10/device/wsdl",
        "GetCapabilities": "http://www.onvif.org/ver10/device/wsdl",
        "GetProfiles": "http://www.onvif.org/ver10/media/wsdl",
        "GetStreamUri": "http://www.onvif.org/ver10/media/wsdl",
        "GetSnapshotUri": "http://www.onvif.org/ver10/media/wsdl",
        "ContinuousMove": "http://www.onvif.org/ver20/ptz/wsdl",
        "Stop": "http://www.onvif.org/ver20/ptz/wsdl",
    }.get(action_name, "http://www.onvif.org/ver10/device/wsdl")
    headers = {
        "Content-Type": f'application/soap+xml; charset=utf-8; action="{action_namespace}/{action_name}"',
        "SOAPAction": f'"{action_namespace}/{action_name}"',
    }
    payload = envelope.encode()
    req = urllib.request.Request(url, data=payload, headers=headers)
    password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_manager.add_password(None, url, ONVIF_USER, ONVIF_PASSWORD)
    digest_handler = urllib.request.HTTPDigestAuthHandler(password_manager)
    opener = urllib.request.build_opener(digest_handler)
    response = opener.open(req, timeout=timeout)
    with response:
        return response.read().decode("utf-8", "ignore")

def xml(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def tag(text, name):
    match = re.search(r"<(?:[\w-]+:)?" + re.escape(name) + r"\b[^>]*>(.*?)</(?:[\w-]+:)?" + re.escape(name) + r">", text, re.S)
    return re.sub(r"<[^>]+>", "", match.group(1)).strip() if match else None

def soap_fault_detail(exc):
    if not isinstance(exc, urllib.error.HTTPError):
        return type(exc).__name__
    try:
        payload = exc.read().decode("utf-8", "ignore")
        reason = tag(payload, "Text") or tag(payload, "faultstring") or tag(payload, "Value")
        return f"HTTP {exc.code}" + (f"：{reason}" if reason else "")
    except Exception:
        return f"HTTP {exc.code}"

def endpoint(text, service_name):
    wanted = "media" if service_name.lower() == "media" else "ptz"
    direct = re.search(r"<(?:[\w-]+:)?" + wanted + r"\b[^>]*>(.*?)</(?:[\w-]+:)?" + wanted + r">", text, re.S | re.I)
    if direct:
        address = tag(direct.group(1), "XAddr")
        if address:
            return address
    for service in re.findall(r"<(?:[\w-]+:)?Service\b[^>]*>(.*?)</(?:[\w-]+:)?Service>", text, re.S):
        namespace = tag(service, "Namespace") or ""
        if wanted in namespace.lower():
            return tag(service, "XAddr")
    return None

def init_onvif():
    result = {"ok": False, "message": "Not tested"}
    try:
        runtime_log(f"Connecting to ONVIF service: {ONVIF_URL}")
        result["stage"] = "device information"
        device = soap("tds:GetDeviceInformation", "")
        result["stage"] = "capabilities"
        capabilities = soap("tds:GetCapabilities", "<tds:Category>All</tds:Category>")
        result["stage"] = "media service endpoint"
        media_url = endpoint(capabilities, "Media") or ONVIF_URL.replace("device_service", "media_service")
        result["stage"] = "media profiles"
        profiles = soap("trt:GetProfiles", "", media_url)
        token_match = re.search(r"<[^>]*Profiles[^>]*token=[\"']([^\"']+)", profiles)
        token = token_match.group(1) if token_match else "Profile_1"
        result["stage"] = "RTSP URI"
        media = soap("trt:GetStreamUri", f"<trt:ProfileToken>{xml(token)}</trt:ProfileToken><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>", media_url)
        ptz_url = endpoint(capabilities, "PTZ") or endpoint(device, "PTZ")
        stream_uri = tag(media, "Uri")
        snapshot_uri = None
        snapshot_warning = None
        try:
            result["stage"] = "snapshot URI"
            snapshot = soap("trt:GetSnapshotUri", f"<trt:ProfileToken>{xml(token)}</trt:ProfileToken>", media_url)
            snapshot_uri = tag(snapshot, "Uri")
        except Exception as exc:
            snapshot_warning = f"ONVIF snapshot is unavailable ({soap_fault_detail(exc)}); RTSP frame capture will be used"
        with lock:
            state.update(profile_token=token, media_url=stream_uri, snapshot_uri=snapshot_uri, ptz_url=ptz_url)
        result.update(ok=True, message="ONVIF connected", model=tag(device, "Model"), manufacturer=tag(device, "Manufacturer"), stream_uri=stream_uri)
        result["stage"] = "complete"
        runtime_log(f"ONVIF connected: {result.get('manufacturer') or 'Unknown'} {result.get('model') or ''}".strip())
        if snapshot_warning:
            result["warning"] = snapshot_warning
            runtime_log(snapshot_warning, "WARN")
    except Exception as exc:
        stage = result.get("stage", "connection")
        if isinstance(exc, urllib.error.HTTPError):
            result["message"] = f"ONVIF {stage} failed: HTTP {exc.code}"
        elif isinstance(exc, (TimeoutError, urllib.error.URLError)):
            result["message"] = f"ONVIF {stage} timed out"
        else:
            result["message"] = f"ONVIF {stage} failed: {type(exc).__name__}"
        result["detail"] = str(exc)
        runtime_log(f"{result['message']}: {exc}", "ERROR")
    return result

def ptz(action, speed=0.5):
    speed = max(0.1, min(1.0, float(speed)))
    with lock:
        token, url = state.get("profile_token"), state.get("ptz_url")
    if not token:
        init_onvif()
        token, url = state.get("profile_token"), state.get("ptz_url")
    if not url:
        url = ONVIF_URL.replace("device_service", "ptz_service")
    if action == "stop":
        body = f'<tptz:ProfileToken>{xml(token or "Profile_1")}</tptz:ProfileToken><tptz:PanTilt>true</tptz:PanTilt><tptz:Zoom>true</tptz:Zoom>'
        soap("tptz:Stop", body, url)
        return
    vectors = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0), "upleft": (-1, 1), "upright": (1, 1), "downleft": (-1, -1), "downright": (1, -1)}
    if action in vectors:
        x, y = vectors[action]
        x, y = x * speed, y * speed
        body = f'<tptz:ProfileToken>{xml(token or "Profile_1")}</tptz:ProfileToken><tptz:Velocity><tt:PanTilt x="{x}" y="{y}"/><tt:Zoom x="0"/></tptz:Velocity>'
        soap("tptz:ContinuousMove", body, url)
    elif action in ("zoom_in", "zoom_out"):
        z = speed if action == "zoom_in" else -speed
        body = f'<tptz:ProfileToken>{xml(token or "Profile_1")}</tptz:ProfileToken><tptz:Velocity><tt:PanTilt x="0" y="0"/><tt:Zoom x="{z}"/></tptz:Velocity>'
        soap("tptz:ContinuousMove", body, url)

def capture():
    uri = state.get("snapshot_uri")
    if not uri:
        init_onvif(); uri = state.get("snapshot_uri")
    if not uri: raise RuntimeError("The camera does not provide an ONVIF snapshot URI")
    auth = base64.b64encode(f"{CAMERA_USER}:{CAMERA_PASSWORD}".encode()).decode()
    req = urllib.request.Request(uri, headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(req, timeout=8) as res:
        data = res.read()
    name = dt.datetime.now().strftime("%Y%m%d-%H%M%S.jpg")
    path = SNAPSHOTS / name; path.write_bytes(data)
    return name, data
