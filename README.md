# Network Camera Console

A lightweight native Linux application for viewing and controlling ONVIF/RTSP IP cameras. It uses GTK3 for the desktop interface, OpenCV for live preview, ONVIF SOAP services for PTZ control, and FFmpeg for recording.

[中文说明](README.zh-CN.md)
## Features

- Native GTK3 Linux interface with a cyberpunk theme
- Independent ONVIF and RTSP connections
- RTSP live preview over TCP
- Eight-direction PTZ movement, variable speed and zoom
- Keyboard controls: arrows/WASD, Q/E zoom and Space to stop
- ONVIF snapshots with RTSP-frame fallback
- MP4 recording with direct H.264/HEVC video copy
- Editable ONVIF service URL and RTSP stream URL
- Detailed terminal diagnostics and concise UI status messages

RTSP preview and recording do not require ONVIF. PTZ control requires a successful ONVIF connection.

## Requirements

### Hardware

- 64-bit ARM or x86 Linux computer/development board
- Two CPU cores and 1 GB RAM minimum; four cores and 2 GB RAM recommended
- X11 or Wayland desktop session
- 960 × 680 display minimum; 1280 × 800 recommended
- Network path from the host to the camera
- RTSP camera; ONVIF PTZ support is required for movement and zoom

HEVC software decoding can be CPU-intensive. Recording is lighter because video is copied without re-encoding; only incompatible audio such as G.711/PCM is converted to AAC.

### Software

- Python 3.9+
- GTK 3 and PyGObject
- OpenCV Python bindings
- FFmpeg and ffprobe
- Bash

Install dependencies on Ubuntu/Debian:

```bash
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-3.0 python3-opencv ffmpeg
```

## Configuration

Copy the public template and replace all example values with your camera settings:

```bash
cp .env.example .env
```

| Variable | Purpose |
| --- | --- |
| `CAMERA_IP` | Default camera host |
| `CAMERA_USER` / `CAMERA_PASSWORD` | RTSP credentials |
| `ONVIF_USER` / `ONVIF_PASSWORD` | ONVIF credentials |
| `ONVIF_PORT` | Initial ONVIF port |
| `ONVIF_URL` | Full ONVIF device service URL |
| `RTSP_URL` | Full RTSP stream URL |

The committed configuration uses `192.0.2.10`, an IANA documentation-only address. It must be replaced before connecting.

ONVIF paths, RTSP paths and ports vary between camera vendors. Both complete URLs are editable in the application.

## Run

```bash
./run_desktop.sh
```

ONVIF and RTSP can be connected in either order. If the camera does not implement ONVIF `GetSnapshotUri`, start RTSP preview before taking a snapshot so the current frame can be saved.

## Network routing

The host and camera need IP connectivity but do not need the same Wi-Fi SSID. A dual-interface development board can keep development traffic on Ethernet and camera traffic on Wi-Fi:

```text
Internet and development tools -> eth0 -> default gateway
Camera subnet                 -> wlan0 -> camera network
```

Useful checks:

```bash
ip route get CAMERA_IP
nc -vz CAMERA_IP ONVIF_PORT
nc -vz CAMERA_IP 554
```

Some cameras block ICMP, so a failed ping does not prove that ONVIF or RTSP is unavailable.

## Output and security

- Recordings are written to `recordings/*.mp4`.
- Snapshots are written to `snapshots/*.jpg`.
- `.env`, recordings and snapshots are ignored by Git.
- Never commit real credentials, private addresses or sensitive media.
- Prefer a dedicated least-privilege camera account.

## Technical support and contributions

If you encounter any problems during use, please submit a technical inquiry on the [Quectel official forum](https://forums.quectel.com/c/quectel-pi/80). The Quectel technical support team will respond promptly.