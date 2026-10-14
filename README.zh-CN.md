# 网络摄像头控制台

一个轻量级 Linux 原生网络摄像头应用。应用使用 GTK3 构建桌面界面，使用 OpenCV 预览 RTSP 视频，通过 ONVIF SOAP 服务控制云台，并使用 FFmpeg 录像。

[English README](README.md)

## 功能

- 采用赛博朋克主题的 GTK3 Linux 原生界面
- ONVIF 与 RTSP 独立连接
- RTSP over TCP 实时预览
- 八方向 PTZ 移动、速度调节和变焦
- 方向键/WASD、Q/E 变焦和空格停止快捷键
- ONVIF 抓拍，不支持时回退到 RTSP 当前帧
- MP4 录像，H.264/HEVC 视频直接复制
- 可编辑完整 ONVIF 服务 URL 和 RTSP 视频流 URL
- 终端输出详细诊断，界面显示简短状态

RTSP 预览和录像不依赖 ONVIF，PTZ 控制需要 ONVIF 成功连接。

## 运行要求

### 硬件

- 64 位 ARM 或 x86 Linux 主机/开发板
- 最低双核 CPU 和 1 GB 内存，推荐四核与 2 GB 内存
- X11 或 Wayland 桌面会话
- 最低 960 × 680 显示分辨率，推荐 1280 × 800
- 主机到摄像头之间具备 IP 连通性
- 支持 RTSP 的摄像头；移动和变焦需要 ONVIF PTZ

HEVC 软件解码可能占用较多 CPU。录像不会重新编码视频，只会将 G.711/PCM 等不兼容音频转换为 AAC，因此负载相对较低。

### 软件

- Python 3.9+
- GTK 3 与 PyGObject
- OpenCV Python 绑定
- FFmpeg 和 ffprobe
- Bash

Ubuntu/Debian 安装命令：

```bash
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-3.0 python3-opencv ffmpeg
```

## 配置

复制公开配置模板，并将示例值替换为自己的摄像头配置：

```bash
cp .env.example .env
```

| 变量 | 用途 |
| --- | --- |
| `CAMERA_IP` | 默认摄像头地址 |
| `CAMERA_USER` / `CAMERA_PASSWORD` | RTSP 账户与密码 |
| `ONVIF_USER` / `ONVIF_PASSWORD` | ONVIF 账户与密码 |
| `ONVIF_PORT` | ONVIF 初始端口 |
| `ONVIF_URL` | 完整 ONVIF 设备服务 URL |
| `RTSP_URL` | 完整 RTSP 视频流 URL |

仓库中的默认地址 `192.0.2.10` 是 IANA 文档专用地址，连接前必须替换。

不同厂商的 ONVIF 路径、RTSP 路径和端口可能不同，应用界面允许修改两个协议的完整 URL。

## 启动

```bash
./run_desktop.sh
```

ONVIF 和 RTSP 没有连接顺序要求。如果摄像头不支持 ONVIF `GetSnapshotUri`，请先启动 RTSP 预览，再通过当前视频帧拍照。

## 网络路由

开发板与摄像头需要具备 IP 连通性，但不要求使用同一个 Wi-Fi SSID。双网卡开发板可以让开发流量使用有线网络，让摄像头流量使用 Wi-Fi：

```text
互联网和开发工具 -> eth0 -> 默认网关
摄像头子网       -> wlan0 -> 摄像头网络
```

常用检查命令：

```bash
ip route get CAMERA_IP
nc -vz CAMERA_IP ONVIF_PORT
nc -vz CAMERA_IP 554
```

部分摄像头会禁用 ICMP，因此 ping 失败不能证明 ONVIF 或 RTSP 不可访问。

## 输出与安全

- 录像保存在 `recordings/*.mp4`。
- 抓拍保存在 `snapshots/*.jpg`。
- `.env`、录像和抓拍文件均被 Git 忽略。
- 不要提交真实密码、私人地址或敏感视频。
- 建议使用最小权限的摄像头专用账户。

## 技术支持与贡献

如在使用过程中遇到问题，欢迎在[移远官方论坛](https://forumschinese.quectel.com/c/quectel-pi/58)提交技术咨询，移远技术支持团队将及时为您解答。