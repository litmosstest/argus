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
mkdir -p config docs scripts

mv mosquitto.conf config/
mv frigate.yml config/
mv setup.sh install_hailo.sh scripts/
mv cameras.md troubleshooting.md docs/
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

### `.env` not created by setup.sh

Create it manually:

```bash
cp ~/argus/.env.example ~/argus/.env
nano ~/argus/.env
```

---

## Hailo-8 issues

### `/dev/hailo0` not present after reboot

First verify whether the driver module is loaded:

```bash
lsmod | grep hailo_pci
dmesg | grep -i hailo
```

If the module is present but the device is not:

```bash
cat /sys/module/hailo_pci/version      # confirm correct driver version
ls -l /lib/firmware/hailo/hailo8_fw.bin  # confirm firmware installed
```

If either is missing, re-run the installation script:

```bash
./scripts/install_hailo.sh
```

### Bookworm only: driver loads but `/dev/hailo0` never appears

Raspberry Pi OS Bookworm ships a built-in Hailo driver that is incompatible
with Frigate. The `install_hailo.sh` script handles this automatically — on
first run it renames the built-in driver and reboots. On the second run it
installs the correct driver.

If you installed the driver manually and are seeing this issue, check whether
the built-in driver is still active:

```bash
modinfo -n hailo_pci
# If this returns a path like /lib/modules/.../kernel/drivers/media/pci/hailo/hailo_pci.ko.xz
# the built-in driver is still present.
```

Rename it and allow the Frigate-built driver to take over:

```bash
BUILTIN=$(modinfo -n hailo_pci)
sudo modprobe -r hailo_pci
sudo mv "$BUILTIN" "${BUILTIN}.bak"
sudo depmod -a
sudo reboot
```

### PCIe page size error

```
CHECK failed - max_desc_page_size given 16384 is bigger than hw max desc page size 4096
```

```bash
echo 'options hailo_pci force_desc_page_size=4096' | sudo tee /etc/modprobe.d/hailo_pci.conf
sudo reboot
```

The `install_hailo.sh` script applies this fix automatically. Only needed if
you installed manually.

---

## Frigate issues

### Config validation errors (Frigate 0.17+)

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
# CORRECT for Frigate 0.17+
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

## Performance reference

| Component | Expected |
|---|---|
| Frigate detection (Hailo-8, 1 camera) | ~20–30ms/frame |
| Frigate detection (CPU fallback, 1 camera) | ~150–200ms/frame |
