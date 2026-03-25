# Troubleshooting

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

### hailo-ollama not responding

```bash
systemctl status hailo-ollama
journalctl -u hailo-ollama -n 50

# Test the API directly
curl -s http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen2:1.5b", "messages": [{"role": "user", "content": "hi"}], "stream": false}'
```

If not installed yet, follow the manual step in `scripts/install_hailo.sh` —
hailo-ollama requires registering at [hailo.ai/developer-zone](https://hailo.ai/developer-zone/)
to download the GenAI model zoo `.deb` package.

### hailo-ollama: model not found

```bash
# List available models
curl -s http://localhost:8000/api/tags

# Pull the default model
curl -s http://localhost:8000/api/pull \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen2:1.5b", "stream": false}'
```

### PCIe page size error in logs

```
CHECK failed - max_desc_page_size given 16384 is bigger than hw max desc page size 4096
```

```bash
echo 'options hailo_pci force_desc_page_size=4096' | sudo tee /etc/modprobe.d/hailo_pci.conf
sudo reboot
```

---

## Frigate issues

### Container keeps restarting

```bash
docker compose logs frigate
```

Common causes:
- Webcam device mismatch — check `WEBCAM_DEVICE` in `.env` against `ls /dev/video*`
- `shm_size` too small — increase to `512mb` in `docker-compose.yml` for more cameras
- Recordings path not writable — check `RECORDINGS_PATH` in `.env`

### Webcam not detected in Frigate

```bash
ls /dev/video*
v4l2-ctl --list-devices
```

Update `WEBCAM_DEVICE` in `.env` to match the actual device (e.g. `/dev/video2`).

---

## Voice assistant issues

### `No module named hailo_platform`

```bash
python3 -c "import hailo_platform; print('ok')"
```

If it fails, the Hailo Python bindings may not be on the path. Try:

```bash
sudo apt install -y python3-hailort
```

The voice assistant falls back to `faster-whisper` automatically — you'll see
`STT: faster-whisper-cpu` in the startup banner instead of `hailo-10h-hybrid`.

### No audio input

```bash
arecord -l
python3 -c "import sounddevice; print(sounddevice.query_devices())"
```

Set `AUDIO_INPUT_DEVICE` in `.env` to the correct device index.

### Piper TTS silent

```bash
echo "Test from Argus" | piper \
  --model voice/models/en_GB-alan-medium.onnx \
  --output_file /tmp/test.wav && aplay /tmp/test.wav
```

If the model is missing: `./scripts/download_models.sh`

### LLM response very slow (>30 seconds)

Verify hailo-ollama is using the NPU and not falling back to CPU:

```bash
journalctl -u hailo-ollama -n 20 | grep -i "hailo\|cpu\|npu"
```

Also check `/dev/hailo0` is present — if the driver isn't loaded, inference falls to CPU.

---

## Performance reference

| Component | Expected performance |
|---|---|
| Frigate detection (CPU) | ~200ms/frame, 1–2 cameras comfortable |
| Whisper STT (Hailo-10H hybrid) | ~400–600ms for 5s utterance |
| Whisper STT (CPU fallback) | ~4–6 seconds |
| LLM response (Hailo-10H, qwen2:1.5b) | 6–8 tokens/sec, ~5–10s for typical answer |
