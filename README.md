# Argus

[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](LICENSE)

**Frigate NVR with Hailo-8 object detection on a Raspberry Pi 5.**

Argus is a minimal, fully local home security setup: Frigate running in Docker, accelerated by the Raspberry Pi AI HAT+ (Hailo-8), with a Logitech USB webcam as the camera input. No cloud, no subscriptions.

## Hardware

| Component | Part | Notes |
|---|---|---|
| SBC | Raspberry Pi 5 (8GB or 16GB) | |
| AI accelerator | Raspberry Pi AI HAT+ (Hailo-8, 26 TOPS) | PCIe-attached, runs object detection |
| Storage | USB SSD ≥256GB | SD cards wear out under continuous writes |
| Camera | USB webcam (UVC-compatible) | Logitech C920/C922 recommended |

## Software

| Component | Detail |
|---|---|
| OS | Raspberry Pi OS Trixie Lite (64-bit) |
| Frigate | Docker (`ghcr.io/blakeblackshear/frigate:stable-h8l`) |
| Detector | `hailo8l` — runs YOLOx on the Hailo-8 NPU |
| MQTT | Mosquitto (Docker) — Frigate event bus |

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/argus.git
cd argus

# 1. System setup (Docker, ffmpeg, webcam check)
chmod +x scripts/setup.sh && ./scripts/setup.sh

# 2. Install Hailo-8 driver
# On Bookworm: reboots twice (re-run the script after the first reboot)
# On Trixie:   reboots once
chmod +x scripts/install_hailo.sh && ./scripts/install_hailo.sh

# 3. After reboot — configure and start
cp .env.example .env
nano .env
docker compose up -d
```

Frigate web UI: `http://argus.local:8971`

## Full setup guide

### 1. Flash the OS

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to write
**Raspberry Pi OS Trixie (64-bit)** to your boot media.

In Imager → Edit Settings before writing:
- Enable SSH
- Set username and password
- Hostname: `argus`
- Configure Wi-Fi (or skip for Ethernet)

### 2. First boot

```bash
ssh pi@argus.local

# Install git and curl if not present (Lite images may omit them)
sudo apt update && sudo apt install -y git curl

sudo apt full-upgrade -y
sudo reboot
```

### 3. Mount a USB SSD (recommended)

SD cards will wear out quickly under continuous recording writes.

```bash
lsblk                              # find your SSD — usually /dev/sda
sudo mkfs.ext4 /dev/sda1           # WARNING: erases the drive
sudo mkdir -p /mnt/recordings
sudo mount /dev/sda1 /mnt/recordings
echo '/dev/sda1 /mnt/recordings ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
```

Set `RECORDINGS_PATH=/mnt/recordings/frigate` in `.env`.

### 4. Clone and run setup

```bash
git clone https://github.com/YOUR_USERNAME/argus.git
cd argus
chmod +x scripts/setup.sh && ./scripts/setup.sh
```

### 5. Install Hailo-8 driver

```bash
chmod +x scripts/install_hailo.sh && ./scripts/install_hailo.sh
```

The script downloads and runs Frigate's official Hailo installation script,
which builds the PCIe driver from source, installs firmware, and sets up
udev rules.

> **Bookworm only:** On Raspberry Pi OS Bookworm the first run disables the
> incompatible built-in kernel driver and reboots. SSH back in and
> **re-run the script** to complete the install. Trixie users only need one run.

After the final reboot, SSH back in and verify:

```bash
ls -l /dev/hailo0
lsmod | grep hailo_pci
cat /sys/module/hailo_pci/version
ls -l /lib/firmware/hailo/hailo8_fw.bin
```

### 6. Configure

```bash
cp .env.example .env
nano .env
```

Settings:

| Variable | Default | Description |
|---|---|---|
| `TZ` | `Europe/London` | Timezone |
| `WEBCAM_DEVICE` | `/dev/video0` | USB webcam device node |
| `RECORDINGS_PATH` | `./data/recordings` | Where recordings are stored |

Find your webcam device:

```bash
ls /dev/video*
v4l2-ctl --list-devices
```

### 7. Start Frigate

```bash
docker compose up -d
docker compose logs -f frigate
```

Open `http://argus.local:8971`. On first start Frigate prints admin credentials
to the log — change the password under Settings → Users.

## Stopping and starting

```bash
docker compose down        # stop
docker compose up -d       # start
docker compose ps          # status
docker compose logs -f     # live logs
```

## Adding cameras

The default config (`config/frigate.yml`) uses a single USB webcam. To add
RTSP PoE cameras, see [docs/cameras.md](docs/cameras.md).

## Project structure

```
argus/
├── docker-compose.yml
├── .env.example
├── config/
│   ├── frigate.yml        # Frigate NVR config (hailo8l detector, webcam)
│   └── mosquitto.conf
├── scripts/
│   ├── setup.sh           # System setup (Docker, deps)
│   └── install_hailo.sh   # Hailo-8 PCIe driver install
└── docs/
    ├── cameras.md          # Adding USB and RTSP cameras
    ├── troubleshooting.md
    ├── hardware-diagram.svg
    └── software-diagram.svg
```

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md).

## Licence

Apache 2.0 — see [LICENSE](LICENSE)
