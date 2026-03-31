#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# setup.sh — one-shot system setup for Argus on NVIDIA DGX Spark
# Run once on a freshly provisioned DGX Spark (Ubuntu 24.04, aarch64)
# Usage: chmod +x scripts/setup.sh && sudo ./scripts/setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARGUS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DEMO_VIDEO_URL="https://data.kitware.com/api/v1/item/56f5863a8d777f753209ca89/download"
DEMO_VIDEO_DEST="$ARGUS_DIR/config/demo/kitware_demo.mp4"

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║   Argus — DGX Spark system setup          ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "Repo root: $ARGUS_DIR"
echo ""

# ─── Verify NVIDIA driver ─────────────────────────────────────────────────────
echo "► Checking NVIDIA driver..."
if ! command -v nvidia-smi &>/dev/null; then
    echo "  ERROR: nvidia-smi not found. Install the NVIDIA driver first."
    exit 1
fi
nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader \
    | sed 's/^/  GPU: /'

# ─── NVIDIA Container Toolkit ────────────────────────────────────────────────
echo ""
echo "► Checking NVIDIA Container Toolkit..."
if ! dpkg -l nvidia-container-toolkit &>/dev/null 2>&1; then
    echo "  Installing NVIDIA Container Toolkit..."
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
        | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -sL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    apt-get update -qq
    apt-get install -y nvidia-container-toolkit
    echo "  ✓ NVIDIA Container Toolkit installed"
else
    echo "  ✓ NVIDIA Container Toolkit already installed"
fi

# ─── Configure Docker NVIDIA runtime ─────────────────────────────────────────
echo ""
echo "► Configuring Docker NVIDIA runtime..."
if ! command -v docker &>/dev/null; then
    echo "  Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    echo "  ✓ Docker installed"
fi

nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
echo "  ✓ Docker restarted with NVIDIA runtime"

# ─── Verify GPU in container ──────────────────────────────────────────────────
echo ""
echo "► Verifying GPU visibility inside Docker..."
if docker run --rm --runtime=nvidia \
    -e NVIDIA_VISIBLE_DEVICES=all \
    ubuntu:24.04 \
    bash -c "ls /dev/nvidia* 2>/dev/null | head -5" 2>/dev/null | grep -q nvidia; then
    echo "  ✓ NVIDIA devices visible inside Docker"
else
    echo "  ⚠  Could not confirm GPU device visibility. Check NVIDIA Container Toolkit."
fi

# ─── Core dependencies ────────────────────────────────────────────────────────
echo ""
echo "► Installing system dependencies..."
apt-get install -y -qq curl ffmpeg jq htop python3-venv python3-pip

# ─── Download Kitware demo video ──────────────────────────────────────────────
echo ""
echo "► Downloading Kitware demo video..."
mkdir -p "$(dirname "$DEMO_VIDEO_DEST")"

if [ -f "$DEMO_VIDEO_DEST" ]; then
    echo "  ✓ Demo video already present: $DEMO_VIDEO_DEST"
else
    echo "  Fetching from $DEMO_VIDEO_URL"
    curl -L --progress-bar -o "$DEMO_VIDEO_DEST" "$DEMO_VIDEO_URL"
    echo "  ✓ Saved to: $DEMO_VIDEO_DEST"
fi

# Confirm video is readable by ffprobe
if ffprobe -v quiet -show_entries format=duration "$DEMO_VIDEO_DEST" &>/dev/null; then
    echo "  ✓ Video is valid"
else
    echo "  ⚠  ffprobe could not read the video — check the download."
fi

# Transcode to H.264 if not already (go2rtc uses #video=copy — needs native H.264)
VIDEO_CODEC=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=codec_name \
    -of default=noprint_wrappers=1:nokey=1 "$DEMO_VIDEO_DEST" 2>/dev/null)
if [ "$VIDEO_CODEC" != "h264" ]; then
    echo "  Video codec is '$VIDEO_CODEC', transcoding to H.264..."
    TRANSCODE_TMP="${DEMO_VIDEO_DEST}.h264.mp4"
    ffmpeg -y -i "$DEMO_VIDEO_DEST" -c:v libx264 -preset medium -crf 22 -an \
        -movflags +faststart "$TRANSCODE_TMP" 2>/dev/null
    mv "$TRANSCODE_TMP" "$DEMO_VIDEO_DEST"
    echo "  ✓ Transcoded to H.264"
else
    echo "  ✓ Video is already H.264"
fi

# ─── Export YOLOv8n ONNX detection model ─────────────────────────────────────
echo ""
echo "► Exporting YOLOv8n ONNX model (320×320)..."
MODEL_DEST="$ARGUS_DIR/config/model_cache/yolov8n_320.onnx"
mkdir -p "$(dirname "$MODEL_DEST")"

if [ -f "$MODEL_DEST" ]; then
    echo "  ✓ Model already present: $MODEL_DEST"
else
    VENV_DIR="/tmp/argus_ml_env"
    echo "  Creating Python venv and installing dependencies..."
    python3 -m venv "$VENV_DIR" --clear
    # Install onnx deps first — ultralytics auto-install fails on Ubuntu 24.04 (PEP 668)
    "$VENV_DIR/bin/pip" install ultralytics onnx onnxslim onnxruntime --quiet

    echo "  Exporting to ONNX..."
    EXPORT_TMP=$(mktemp -d)
    pushd "$EXPORT_TMP" > /dev/null
    "$VENV_DIR/bin/python3" -c "
from ultralytics import YOLO
import shutil
YOLO('yolov8n.pt').export(format='onnx', imgsz=320, simplify=True)
shutil.move('yolov8n.onnx', '$MODEL_DEST')
print('  ✓ Model saved')
"
    popd > /dev/null
    rm -rf "$EXPORT_TMP"
    echo "  ✓ Saved to: $MODEL_DEST"
fi
echo ""
echo "► Creating data directories..."
mkdir -p "$ARGUS_DIR/data/recordings" "$ARGUS_DIR/data/db"
echo "  ✓ data/recordings  data/db"

# ─── .env ─────────────────────────────────────────────────────────────────────
ENV_EXAMPLE="$ARGUS_DIR/.env.example"
ENV_FILE="$ARGUS_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo ""
    echo "► Created .env from template — edit $ENV_FILE before starting services."
else
    echo "► .env already exists — skipping"
fi

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║           Setup complete ✓                ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1.  Edit environment:    nano $ENV_FILE"
echo "  2.  Start Frigate:       docker compose up -d"
echo "  3.  Open web UI:         http://$(hostname -I | awk '{print $1}'):5000"
echo ""
