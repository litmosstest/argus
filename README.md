# 🦅 Argus

[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](LICENSE)
[![Hugging Face Space](https://img.shields.io/badge/🤗%20Hugging%20Face-Space-blue)](https://huggingface.co/spaces/YOUR_HF_USERNAME/argus)

**Fully local AI camera system — Frigate NVR + Hailo-10H voice assistant on a Raspberry Pi 5.**

Argus watches your cameras, detects objects, and answers questions about what it has seen — entirely on-device. No cloud, no subscriptions, no data leaving your home.

```
Cameras ──► Frigate NVR (CPU detection) ──► Event store (SQLite + MQTT)
                                                        │
Microphone ──► Whisper STT (Hailo-10H) ──► Local LLM (Hailo-10H) ──► Piper TTS ──► Speaker
```

## Hardware

| Component | Part | Notes |
|---|---|---|
| SBC | Raspberry Pi 5 (16GB) | 8GB also works |
| AI accelerator | Raspberry Pi AI HAT+ 2 (Hailo-10H, 40 TOPS) | Runs STT + LLM locally |
| Storage | USB SSD ≥256GB | SD cards wear out under continuous writes |
| Camera | Any UVC USB webcam | Logitech C920/C922 recommended |
| Microphone | Any USB microphone | |
| Speaker | USB or 3.5mm | |

> **Note on Frigate + Hailo-10H:** Frigate currently supports Hailo-8/8L for object detection.
> Hailo-10H support is [in active development](https://community.hailo.ai/t/hailo-10h-smart-home-integration-status-update/18852)
> by the Hailo team. Until it lands, Argus runs Frigate detection on the Pi 5 CPU, which is
> perfectly usable for a PoC with 1–2 cameras. The voice pipeline (STT + LLM) runs on the
> Hailo-10H with no compromise.

## How it works

**Object detection** — Frigate NVR runs in Docker and watches your cameras continuously,
detecting people, cars, animals. Events are stored in SQLite and published over MQTT.

**Voice pipeline** — entirely on-device:
1. Press ENTER (or use a button) — microphone starts recording
2. **Whisper encoder** runs on the Hailo-10H NPU (~8× faster than CPU)
3. **Whisper decoder** runs on the Pi 5 CPU with KV caching
4. Transcribed question + recent Frigate events → **Qwen2.5 1.5B LLM** on Hailo-10H via hailo-ollama
5. Answer spoken aloud by **Piper TTS** (local, no cloud)

## System diagrams

### Hardware

![Argus hardware diagram](docs/hardware-diagram.svg)

| Component | Role |
|---|---|
| Raspberry Pi 5 (16GB) | Host CPU — runs Frigate, Docker, OS |
| Hailo-10H AI HAT+ 2 | NPU — Whisper STT encoder + Qwen2.5 LLM |
| USB SSD | Frigate recordings and SQLite event database |
| USB webcams | Camera feeds (Logitech C920/C922 recommended) |
| USB microphone | Voice input for the assistant |
| Speaker | Piper TTS audio output |
| Ethernet | Reliable network for SSH and remote access |

### Software and data flow

![Argus software diagram](docs/software-diagram.svg)

**Vision pipeline** (Pi 5 CPU)

Camera frames flow from USB devices through `go2rtc` for stream management, then into Frigate NVR running in Docker. Frigate performs object detection on the CPU, storing events in SQLite on the USB SSD and publishing live event notifications over MQTT via Mosquitto.

**Voice pipeline** (Hailo-10H NPU + Pi 5 CPU)

Speech is captured from the USB microphone. The Whisper encoder runs on the Hailo-10H NPU (~8× faster than CPU), converting audio to embeddings. The Whisper decoder runs on the Pi 5 CPU with KV caching to produce the transcript. The question plus recent Frigate event context is sent to Qwen2.5-1.5B, which runs entirely on the Hailo-10H via `hailo-ollama`. The answer is spoken by Piper TTS locally.

No data leaves the device at any point.

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/argus.git
cd argus

# 1. System setup (Docker, audio deps, webcam check)
chmod +x scripts/setup.sh && ./scripts/setup.sh

# 2. Install Hailo-10H drivers and hailo-ollama
chmod +x scripts/install_hailo.sh && ./scripts/install_hailo.sh
# System reboots — SSH back in and continue

# 3. Download Whisper model assets and pull LLM
chmod +x scripts/download_models.sh && ./scripts/download_models.sh

# 4. Configure
cp .env.example .env && nano .env

# 5. Install voice assistant Python deps
pip install -r voice/requirements.txt --break-system-packages

# 6. Start Frigate
docker compose up -d

# 7. Start the voice assistant
python voice/assistant.py
```

Frigate web UI: `http://argus.local:8971`

## Project structure

```
argus/
├── docker-compose.yml          # Frigate + Mosquitto
├── .env.example
├── config/
│   ├── frigate.yml             # Camera and detection config
│   └── mosquitto.conf
├── voice/
│   ├── assistant.py            # Main push-to-talk loop
│   ├── stt.py                  # Hailo-10H hybrid Whisper STT
│   ├── llm.py                  # hailo-ollama LLM client
│   ├── tts.py                  # Piper TTS wrapper
│   ├── frigate_events.py       # SQLite + MQTT event queries
│   ├── requirements.txt
│   └── README.md
├── scripts/
│   ├── setup.sh                # System dependencies + Docker
│   ├── install_hailo.sh        # Hailo-10H driver + hailo-ollama
│   └── download_models.sh      # Whisper HEF + Piper voice model
├── docs/
│   ├── cameras.md              # Adding RTSP PoE cameras
│   └── troubleshooting.md
├── huggingface/
│   ├── app.py                  # Gradio demo Space
│   ├── README.md               # HF Space card
│   └── requirements.txt
└── .github/workflows/
    └── validate.yml
```

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md).

## Contributing

PRs welcome. Open an issue before starting significant work.

## Licence

Apache 2.0 — see [LICENSE](LICENSE)
