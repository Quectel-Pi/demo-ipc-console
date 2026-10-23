# Architecture

## System design

Network Camera Console is a single-process native Linux application. `desktop_app.py` owns the GTK interface and worker lifecycle; `app.py` provides ONVIF, network and recording helpers.

[中文架构](ARCHITECTURE.zh-CN.md)

```mermaid
flowchart LR
    subgraph Camera[IP Camera]
        Discovery[WS-Discovery]
        ONVIF[ONVIF SOAP]
        RTSP[RTSP Stream]
    end

    subgraph Host[Linux Host]
        GTK[GTK3 UI]
        Scanner[Device Discovery Worker]
        DiscoveryCore[ONVIF Discovery Module]
        Preview[OpenCV Preview Worker]
        PTZ[PTZ Command Queue]
        Core[Python Camera Core]
        Recorder[FFmpeg Process]
        Files[(Snapshots / Recordings)]
    end

    GTK --> Preview
    GTK --> PTZ
    GTK --> Scanner
    Scanner --> DiscoveryCore
    DiscoveryCore -->|IPv4 UDP multicast 3702| Discovery
    PTZ --> Core
    Core -->|SOAP over HTTP/HTTPS| ONVIF
    Preview -->|RTSP over TCP| RTSP
    GTK --> Recorder
    Recorder -->|RTSP over TCP| RTSP
    Core --> Files
    Recorder --> Files
```

ONVIF and RTSP are independent. RTSP provides preview and recording; ONVIF provides device metadata, stream discovery and PTZ.

## Technology stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Desktop UI | GTK3, PyGObject, GTK CSS | Native controls, layout, status and theme |
| UI runtime | GLib/GDK | Main loop, thread-safe updates, keyboard and pointer input |
| Preview | OpenCV with FFmpeg backend, GdkPixbuf | Decode, resize and render RTSP frames |
| Core | Python 3 standard library | Configuration, networking, SOAP and worker orchestration |
| ONVIF discovery | WS-Discovery, IPv4 UDP multicast, ElementTree | Scan active interfaces, parse device addresses and deduplicate results |
| ONVIF control | SOAP 1.2, HTTP Digest, WS-Security PasswordDigest | Device information, profiles, stream URI and PTZ |
| Recording | FFmpeg | Copy H.264/HEVC video and convert audio to AAC |
| Storage | Local filesystem | MP4 recordings and JPEG snapshots |

The frontend and backend are modules inside one Python process, not separate services.

## Runtime flow

### Automatic device discovery

```mermaid
sequenceDiagram
    participant UI as GTK Discovery Dialog
    participant Scanner as onvif_discovery.py
    participant Camera as ONVIF Camera
    UI->>Scanner: Start scan (4 seconds)
    Scanner->>Scanner: Enumerate active non-loopback IPv4 interfaces
    Scanner->>Camera: Send WS-Discovery Probe on each interface
    Camera-->>Scanner: ProbeMatches (UUID, XAddrs, Scopes)
    Scanner->>Scanner: Deduplicate by UUID or XAddr
    Scanner-->>UI: Return device list
    UI->>UI: User selects a device
    UI->>Camera: Connect to the selected XAddr with UI credentials
```

Discovery runs in a worker thread so the GTK main loop remains responsive. The module sends two `NetworkVideoTransmitter` Probe rounds to `239.255.255.250:3702` and displays the response source IP, ONVIF service URL, local interface and device identifier. Selecting a result copies its service URL into the main window and starts the existing ONVIF initialization flow.

WS-Discovery locates devices but does not carry credentials. Device metadata, media profiles, RTSP addresses and PTZ capabilities are still retrieved with the username and password entered in the main window.

### ONVIF

```mermaid
sequenceDiagram
    participant UI as GTK UI
    participant Core as app.py
    participant Camera as ONVIF Camera
    UI->>Core: Connect with service URL and credentials
    Core->>Camera: GetDeviceInformation
    Core->>Camera: GetCapabilities
    Core->>Camera: GetProfiles
    Core->>Camera: GetStreamUri
    Core->>Camera: GetSnapshotUri (optional)
    Core-->>UI: Device, profile, PTZ and media state
```

Camera-provided service addresses are preferred. If `GetSnapshotUri` is unsupported, the latest RTSP preview frame is saved instead.

### RTSP preview

1. Validate the full RTSP URL and add URL-encoded credentials.
2. Probe the configured TCP endpoint.
3. Open RTSP over TCP through OpenCV's FFmpeg backend.
4. Decode and resize frames in a worker thread.
5. Send only the latest JPEG frame to GTK, dropping stale frames.

### PTZ and recording

- PTZ operations use one queue and one worker to preserve move/stop ordering.
- Movement speed is normalized to the ONVIF range `0.1`–`1.0`.
- FFmpeg copies the first H.264/HEVC video stream without re-encoding.
- The optional first audio stream is converted to AAC for MP4 compatibility.
- Stopping sends `SIGINT` so FFmpeg can finalize the MP4 container.

## Concurrency

| Context | Responsibility |
| --- | --- |
| GTK main thread | UI rendering and input |
| Device discovery worker | Enumerate IPv4 interfaces, send Probes, collect and parse ProbeMatches |
| ONVIF worker | Blocking SOAP initialization |
| Preview worker | RTSP decoding and frame preparation |
| PTZ worker | Ordered SOAP movement commands |
| Recording monitor | FFmpeg completion and error reporting |
| FFmpeg process | MP4 writing |

## Source layout

```text
app.py                  ONVIF, network and recording helpers
onvif_discovery.py      IPv4 WS-Discovery scan, response parsing and device deduplication
desktop_app.py          GTK application and workers
run_desktop.sh          Environment loader and launcher
.env.example            Public configuration template
recordings/             Generated MP4 files
snapshots/              Generated JPEG files
```

## Software requirements

- Linux with X11 or Wayland
- Python 3.9+
- GTK3, PyGObject and `gir1.2-gtk-3.0`
- OpenCV Python bindings
- FFmpeg and ffprobe
- Bash

```bash
sudo apt install python3 python3-gi gir1.2-gtk-3.0 python3-opencv ffmpeg
```

## Hardware requirements

| Component | Minimum | Recommended |
| --- | --- | --- |
| CPU | 64-bit ARM/x86, 2 cores | 4 cores or hardware video decoding |
| Memory | 1 GB | 2 GB or more |
| Display | 960 × 680 | 1280 × 800 or higher |
| Network | Route to camera ONVIF/RTSP ports | Ethernet for development plus Wi-Fi camera subnet |
| Camera | RTSP | ONVIF PTZ and H.264/HEVC |

## Technical constraints

- One camera per process
- One credential pair exposed by the current UI
- Lightweight regular-expression ONVIF XML extraction
- No automatic hardware-decoder selection
- Automatic discovery currently supports IPv4 on the local Layer 2 network; devices across VLANs usually require a manually entered service URL
- Devices with WS-Discovery disabled or UDP port 3702 blocked cannot be discovered automatically
- No IPv6 discovery, presets, patrol, retention policy or disk quota

