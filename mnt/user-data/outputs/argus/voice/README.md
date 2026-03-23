# Argus voice assistant

Fully local voice pipeline — no cloud, no API keys required.

## Pipeline

```
USB mic → sounddevice → Hailo-10H Whisper encoder → Pi 5 CPU decoder → text
                                                                          ↓
                                                  Frigate SQLite + MQTT events
                                                                          ↓
                                               Qwen2.5-1.5B on Hailo-10H NPU
                                               (via hailo-ollama REST API)
                                                                          ↓
                                                       Piper TTS → speaker
```

## STT architecture

The Whisper encoder (spectrogram → embeddings) runs on the Hailo-10H NPU via a compiled
`.hef` model. The decoder (embeddings → text tokens) runs on the Pi 5 CPU with KV caching.
This hybrid approach gives ~8× speedup over CPU-only faster-whisper. If the HAT is absent,
the assistant falls back automatically.

## LLM

`hailo-ollama` runs as a systemd service and exposes an Ollama-compatible REST API on
`localhost:8000`. `llm.py` calls it directly with Python's built-in `urllib` — no
additional dependencies. The model (Qwen2.5-1.5B by default) runs entirely on the
Hailo-10H NPU at ~6–8 tokens/second.

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt --break-system-packages
pip install piper-tts --break-system-packages
```

### 2. Download model assets

```bash
../scripts/download_models.sh
```

### 3. Configure microphone

```bash
arecord -l
python3 -c "import sounddevice; print(sounddevice.query_devices())"
```

Set `AUDIO_INPUT_DEVICE` in `.env` to your mic's index.

### 4. Run

```bash
python assistant.py
```

## Run as a systemd service

```bash
sudo tee /etc/systemd/system/argus-voice.service > /dev/null << 'EOF'
[Unit]
Description=Argus voice assistant
After=network.target hailo-ollama.service docker.service
Requires=hailo-ollama.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/argus/voice
ExecStart=/usr/bin/python3 /home/pi/argus/voice/assistant.py
Restart=on-failure
RestartSec=10
EnvironmentFile=/home/pi/argus/.env

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable argus-voice
sudo systemctl start argus-voice
```

## Example questions

- "Has anyone been detected in the last hour?"
- "What happened on the webcam overnight?"
- "When was the last person seen?"
- "Were there any detections in the past ten minutes?"
- "Which camera has had the most activity today?"
