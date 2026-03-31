# Argus — Frigate NVR on NVIDIA DGX Spark

[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](LICENSE)

**Frigate NVR with NVIDIA GPU-accelerated object detection on an NVIDIA DGX Spark.**

Argus running on the DGX Spark uses the onboard **GB10 Blackwell GPU** for object detection via ONNX Runtime + CUDA. A looping [Kitware demo video](https://data.kitware.com/#item/56f5863a8d777f753209ca89) is used as the input camera stream.

> **Branch:** `dgx-spark` — DGX Spark deployment.
> See `main` for the Raspberry Pi 5 + Hailo-8 variant.

---

## Hardware

| Component    | Detail |
|--------------|--------|
| Platform     | NVIDIA DGX Spark |
| SoC          | NVIDIA GB10 Superchip (Grace Arm CPU + Blackwell GPU) |
| GPU          | NVIDIA GB10 — Compute Capability 12.1 |
| CUDA         | 13.0+ |
| Architecture | aarch64 (ARM64) |
| OS           | Ubuntu 24.04 LTS |

## Software

| Component | Detail |
|-----------|--------|
| OS        | Ubuntu 24.04 LTS (aarch64) |
| Frigate   | Docker (`ghcr.io/blakeblackshear/frigate:stable`) |
| Detector  | `onnx` — ONNX Runtime with CUDA execution provider on GB10 GPU |
| MQTT      | Mosquitto (Docker) — Frigate event bus |

---

## Quick start

```bash
git clone git@github.com:litmosstest/argus.git
cd argus
git checkout dgx-spark

# 1. System setup (NVIDIA Container Toolkit, Docker runtime, demo video download)
chmod +x scripts/setup.sh && sudo ./scripts/setup.sh

# 2. Review / edit environment file
nano .env

# 3. Start
sudo docker compose up -d
```

Frigate web UI: `http://<DGX_SPARK_IP>:5000`

---

## Full setup guide

### 1. Clone and check out the branch

```bash
git clone git@github.com:litmosstest/argus.git
cd argus
git checkout dgx-spark
```

### 2. Verify the NVIDIA driver

```bash
nvidia-smi
```

Expected output: `NVIDIA GB10`, Driver ≥ 580, CUDA ≥ 13.0.

### 3. Run the setup script

```bash
chmod +x scripts/setup.sh
sudo ./scripts/setup.sh
```

`setup.sh` performs these steps automatically:

| Step | Action |
|------|--------|
| 1 | Verify `nvidia-smi` reports the GB10 GPU |
| 2 | Install NVIDIA Container Toolkit (if missing) |
| 3 | Run `nvidia-ctk runtime configure --runtime=docker` and restart Docker |
| 4 | Confirm GPU devices are visible inside a test container |
| 5 | Install `curl`, `ffmpeg`, `jq`, `htop` (if missing) |
| 6 | Download the Kitware demo video to `config/demo/kitware_demo.mp4` |
| 7 | Create `data/recordings/` and `data/db/` |
| 8 | Copy `.env.example` → `.env` |

### 4. Configure

```bash
nano .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `TZ` | `Europe/London` | Timezone for timestamps |
| `RECORDINGS_PATH` | `./data/recordings` | Where Frigate stores recordings |

### 5. Start Frigate

```bash
sudo docker compose up -d
sudo docker compose logs -f frigate
```

On first start, Frigate pulls the image (~1–2 GB) and initialises the ONNX CUDA detector. This takes ~60 seconds. Watch for a line similar to:

```
[onnxruntime] CUDA execution provider registered — device: NVIDIA GB10
```

### 6. Open the web UI

```
http://<DGX_SPARK_IP>:5000
```

The `demo_camera` feed should be running with bounding boxes appearing over detected objects.

---

## How GPU acceleration works

The official Frigate TensorRT image (`stable-tensorrt`) targets **x86_64 only**. The DGX Spark is **aarch64** with a full discrete-class NVIDIA GPU, so the correct path is:

- Detector type: `onnx`
- Device: `cuda:0`
- Provider: ONNX Runtime CUDA execution provider (ships for aarch64)

```yaml
# config/frigate.yml
detectors:
  onnx_gpu:
    type: onnx
    device: cuda:0
```

The NVIDIA runtime passes GPU devices into the container:

```yaml
# docker-compose.yml
runtime: nvidia
environment:
  NVIDIA_VISIBLE_DEVICES: all
  NVIDIA_DRIVER_CAPABILITIES: all
```

---

## Demo video stream

`setup.sh` downloads a Kitware MP4 to `config/demo/kitware_demo.mp4`. go2rtc (embedded in Frigate) serves it as a looping RTSP stream via FFmpeg:

```
config/demo/kitware_demo.mp4
        │
        ▼  ffmpeg -stream_loop -1 -re
   go2rtc  →  rtsp://127.0.0.1:8554/demo_camera
        │
        ▼
   Frigate detect + record pipeline
        │
        ▼
   Web UI  http://<host>:5000
```

To swap in a live RTSP camera, replace the `go2rtc.streams` entry in `config/frigate.yml`.

---

## Project structure

```
argus/
├── docker-compose.yml         # Frigate + MQTT (NVIDIA runtime)
├── .env.example               # Environment variable template
├── config/
│   ├── frigate.yml            # Frigate config (onnx/cuda detector, demo stream)
│   └── mosquitto.conf         # MQTT broker config
└── scripts/
    └── setup.sh               # One-shot host setup for DGX Spark
```

---

## Stopping and starting

```bash
sudo docker compose down       # stop
sudo docker compose up -d      # start
sudo docker compose ps         # status
sudo docker compose logs -f    # live logs
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Unknown runtime specified nvidia` | Docker not configured with NVIDIA runtime | Re-run `sudo ./scripts/setup.sh` |
| GPU not visible inside container | Toolkit configured but Docker not restarted | `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker` |
| `demo_camera` shows Offline | Demo video missing | Check `config/demo/kitware_demo.mp4` exists; re-run `setup.sh` |
| ONNX detector falls back to CPU | CUDA execution provider unavailable in image | Check `docker compose logs frigate` for ONNX CUDA errors; verify NVIDIA runtime is active |
| CUDA error — SM 12.1 unsupported | Bundled ONNX Runtime predates Blackwell | Pull a newer Frigate image (`docker compose pull`), or set `device: cpu` as a fallback |
| High `shm_size` usage / OOM | Multiple streams added | Increase `shm_size` in `docker-compose.yml` (~64 MB per additional 1080p stream) |

---

## Licence

Apache 2.0 — see [LICENSE](LICENSE)
