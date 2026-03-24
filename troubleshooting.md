# Troubleshooting

## First-time setup issues

### Files landed flat after `git clone`

If your clone puts all files in the repo root instead of subdirectories, the
Docker mounts will fail with errors like:
```
mount src=.../mosquitto.conf: not a directory
```

Fix — create the correct structure and move files:

```bash
cd ~/argus
mkdir -p config voice docs scripts huggingface

mv mosquitto.conf config/
mv frigate.yml config/
mv assistant.py stt.py llm.py tts.py frigate_events.py requirements.txt voice/
mv setup.sh install_hailo.sh download_models.sh scripts/
mv cameras.md troubleshooting.md docs/
mv app.py huggingface/
```

Then retry `docker compose up -d`.

### `config/mosquitto.conf` is a directory, not a file

This happens when git creates `config/mosquitto.conf` as a directory due to
a malformed commit. Fix:

```bash
sudo rm -rf ~/argus/config
mkdir -p ~/argus/config
mv ~/argus/mosquitto.conf ~/argus/config/
mv ~/argus/frigate.yml ~/argus/config/
```

### Docker permission denied after install

```bash
sudo usermod -aG docker $USER
```

Then **log out and back in** — `newgrp docker` requires a password on Trixie
and may not work. A full logout/login is the reliable fix.

### piper not found after install

piper installs to `~/.local/bin` which may not be on PATH by default:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
piper --help
```

### piper crashes with `ModuleNotFoundError: No module named 'pathvalidate'`

```bash
pip install pathvalidate --break-system-packages
```

### `.env` not created by setup.sh

If setup.sh can't find `.env.example`, create it manually:

```bash
cp ~/argus/.env.example ~/argus/.env
nano ~/argus/.env
```

---

## Hailo-10H issues

### `/dev/hailo0` not present after reboot

```bash
sudo modprobe hailo_pci
dmesg | grep -i hailo
ls -l /dev/hailo0
```

If it loads manually but disappears on reboot:

```bash
grep hailo_pci /etc/modules || echo 'hailo_pci' | sudo tee -a /etc/modules
sudo reboot
```

### Driver loads but no `/dev/hailo0` created

The most common cause on an AI HAT+ 2 is installing `hailo-all` (the Hailo-8
metapackage) instead of `hailo-h10-all` (the Hailo-10H package). The Hailo-8
driver loads successfully but its PCI device ID alias doesn't match the
Hailo-10H, so it never binds to the device.

Fix:

```bash
sudo apt install hailo-h10-all
sudo reboot
```

To confirm you have the right package:

```bash
dpkg -l | grep hailo-h10
# Should show: hailo-h10-all
```

You can also verify by checking the driver's PCI alias matches your device:

```bash
sudo modinfo hailo_pci | grep alias
lspci | grep -i hailo
```

### hailo-ollama not responding

```bash
systemctl status hailo-ollama
journalctl -u hailo-ollama -n 50

# Test API directly
curl -s http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen2.5:1.5b", "messages": [{"role": "user", "content": "hi"}], "stream": false}'
```

hailo-ollama requires the GenAI model zoo `.deb` from
[hailo.ai/developer-zone](https://hailo.ai/developer-zone) (free registration).

### PCIe page size error

```
CHECK failed - max_desc_page_size given 16384 is bigger than hw max desc page size 4096
```

```bash
echo 'options hailo_pci force_desc_page_size=4096' | sudo tee /etc/modprobe.d/hailo_pci.conf
sudo reboot
```

---

## Frigate issues

### Config validation errors (Frigate 0.17)

The `record -> retain` schema changed in Frigate 0.16+. The old format:

```yaml
# OLD — no longer valid
record:
  retain:
    days: 3
    mode: motion
```

New format:

```yaml
# CORRECT for Frigate 0.17
record:
  enabled: true
  alerts:
    retain:
      days: 14
  detections:
    retain:
      days: 14
```

Also remove any `events:` blocks under camera-level `record:` sections.

### Webcam stream 404 / go2rtc not opening device

The `device://` go2rtc source can fail on Pi 5. Use the ffmpeg source instead:

```yaml
go2rtc:
  streams:
    webcam:
      - "ffmpeg:device?video=/dev/video0#video=h264#hardware"
```

### Container keeps restarting

```bash
docker compose logs frigate
```

Common causes: webcam device mismatch (`WEBCAM_DEVICE` in `.env`), recordings
path not writable, `shm_size` too small for multiple cameras.

---

## Voice assistant issues

### `No module named hailo_platform`

```bash
python3 -c "import hailo_platform; print('ok')"
```

If missing: `sudo apt install -y python3-hailort`

The assistant falls back to `faster-whisper` (CPU) automatically — startup
banner shows `STT: faster-whisper-cpu` vs `STT: hailo-10h-hybrid`.

### No audio input

```bash
arecord -l
python3 -c "import sounddevice; print(sounddevice.query_devices())"
```

Set `AUDIO_INPUT_DEVICE` in `.env` to the correct index.

### Piper TTS silent

```bash
echo "Test" | piper \
  --model voice/models/en_GB-alan-medium.onnx \
  --output_file /tmp/test.wav && aplay /tmp/test.wav
```

If model missing: `./scripts/download_models.sh`

---

## Performance reference

| Component | Expected |
|---|---|
| Frigate detection (CPU, 1 camera) | ~150–200ms/frame |
| Whisper STT (Hailo-10H hybrid) | ~400–600ms for 5s utterance |
| Whisper STT (CPU fallback) | ~4–6 seconds |
| LLM response (Hailo-10H, qwen2.5:1.5b) | 6–9 tokens/sec, ~5–10s answer |
