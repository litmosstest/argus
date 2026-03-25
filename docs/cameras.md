# Camera setup

## Phase 1: USB webcam (current)

Any UVC-compatible USB webcam works out of the box. Logitech C920/C922 are
reliable choices with solid Linux support and good low-light performance.

Verify detection after plugging in:

```bash
ls /dev/video*
v4l2-ctl --list-devices
```

If your webcam isn't `/dev/video0`, update `WEBCAM_DEVICE` in `.env`.

---

## Phase 2: RTSP PoE cameras

### Recommended: Dahua IPC-T5442TM-AS

The camera most consistently recommended by the Frigate community. Available
in the UK as **Loryta** or **EmpireTech** on Amazon — same hardware, rebranded.

| Spec | Value |
|---|---|
| Resolution | 4MP |
| Sensor | 1/1.8" — large sensor, excellent low light |
| Night vision | 0.002 lux at F1.6 |
| Connection | PoE (802.3af) |
| RTSP streams | 3 independent (main, sub1, sub2) |
| Price | ~£50–70 UK |

Available in **2.8mm** (wide ~100° FoV) and **3.6mm** (narrower, more detail).
A varifocal variant (IPC-T5442T-ZE) lets you dial in the FoV after mounting.

**Why not Reolink?** Their RTSP implementation drops streams under load.
Dahua/Hikvision are rock solid by comparison.

### PoE switch

**TP-Link TL-SG1005P** — 4 PoE ports, 65W total budget. Each Dahua camera
draws ~8W, so 4 cameras fit comfortably.

---

## Adding a camera to Frigate

Add entries to both `go2rtc` and `cameras` in `config/frigate.yml`.
Dahua RTSP URL pattern:

- Main stream (full res, for recording): `channel=1&subtype=0`
- Sub-stream (low res, for detection): `channel=1&subtype=2`

```yaml
go2rtc:
  streams:
    front:
      - "rtsp://admin:PASSWORD@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0"
    front_sub:
      - "rtsp://admin:PASSWORD@192.168.1.100:554/cam/realmonitor?channel=1&subtype=2"

cameras:
  front:
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/front_sub
          roles:
            - detect
        - path: rtsp://127.0.0.1:8554/front
          roles:
            - record
    detect:
      width: 640
      height: 480
      fps: 5
```

Default Dahua credentials are `admin` / `admin` — change these immediately
via the camera's web UI at its IP address before adding it to Frigate.

Each camera added increases CPU load. Two Logitech webcams or two Dahua PoE
cameras run comfortably on the Pi 5 CPU for detection. The Hailo-8 supports
Frigate detection — see the Frigate docs for adding a Hailo detector to
`config/frigate.yml` to increase capacity.
