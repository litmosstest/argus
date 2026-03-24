#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# setup.sh — one-shot system setup for Argus
# Run once on a freshly flashed Raspberry Pi OS Trixie Lite (64-bit)
# Usage: chmod +x scripts/setup.sh && ./scripts/setup.sh
#
# NOTE: Run this from the repo root:  ./scripts/setup.sh
# or:  bash scripts/setup.sh

set -euo pipefail

# Resolve repo root regardless of where the script is called from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARGUS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║          Argus — system setup        ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Repo root: $ARGUS_DIR"
echo ""

# ─── System update ────────────────────────────────────────────────────────────
echo "► Updating system packages..."
sudo apt update -qq && sudo apt full-upgrade -y -qq

# ─── Core dependencies ────────────────────────────────────────────────────────
echo "► Installing system dependencies..."
sudo apt install -y \
    curl git jq htop wget \
    v4l-utils \
    ffmpeg \
    portaudio19-dev \
    libportaudio2 \
    alsa-utils \
    python3-pip \
    dkms \
    linux-headers-$(uname -r)

# ─── Docker ───────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "► Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo "  ✓ Docker installed"
    echo "  ⚠  Log out and back in (or run 'newgrp docker') for group changes to take effect"
else
    echo "► Docker: $(docker --version)"
fi

# ─── piper-tts ────────────────────────────────────────────────────────────────
echo "► Installing piper-tts..."
pip install piper-tts pathvalidate --break-system-packages -q
echo "  ✓ piper-tts installed"

# ─── Ensure ~/.local/bin is on PATH ──────────────────────────────────────────
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo "► Adding ~/.local/bin to PATH in ~/.bashrc..."
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    export PATH="$HOME/.local/bin:$PATH"
    echo "  ✓ PATH updated (takes effect on next login)"
fi

# ─── USB SSD ──────────────────────────────────────────────────────────────────
echo ""
echo "► USB storage devices:"
USB=$(lsblk -d -o NAME,TRAN,SIZE,MODEL | grep -i usb || echo "  (none detected)")
echo "$USB" | sed 's/^/  /'
if echo "$USB" | grep -qi usb; then
    echo ""
    echo "  To configure the SSD for recordings:"
    echo "    sudo mkfs.ext4 /dev/sda1       # WARNING: erases the drive"
    echo "    sudo mkdir -p /mnt/recordings"
    echo "    sudo mount /dev/sda1 /mnt/recordings"
    echo "    echo '/dev/sda1 /mnt/recordings ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab"
    echo "  Then set RECORDINGS_PATH=/mnt/recordings/frigate in .env"
fi

# ─── Webcam ───────────────────────────────────────────────────────────────────
echo ""
echo "► Video devices:"
if ls /dev/video* &>/dev/null; then
    v4l2-ctl --list-devices 2>/dev/null | sed 's/^/  /' || ls /dev/video* | sed 's/^/  /'
else
    echo "  ⚠  No /dev/video* found — plug in webcam and re-run"
fi

# ─── Microphone ───────────────────────────────────────────────────────────────
echo ""
echo "► Audio input devices:"
arecord -l 2>/dev/null | grep "card " | sed 's/^/  /' || echo "  ⚠  No recording devices found"

# ─── .env ─────────────────────────────────────────────────────────────────────
ENV_EXAMPLE="$ARGUS_DIR/.env.example"
ENV_FILE="$ARGUS_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_EXAMPLE" ]; then
        echo ""
        echo "► Creating .env from template..."
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo "  Edit $ENV_FILE before starting services."
    else
        echo "  ⚠  .env.example not found at $ENV_EXAMPLE"
    fi
else
    echo "► .env already exists — skipping"
fi

# ─── Data dirs ────────────────────────────────────────────────────────────────
mkdir -p "$ARGUS_DIR/data/recordings" "$ARGUS_DIR/data/db"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║           Setup complete ✓           ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1.  Install Hailo driver:   ./scripts/install_hailo.sh"
echo "  2.  Download model assets:  ./scripts/download_models.sh"
echo "  3.  Edit environment:       nano $ENV_FILE"
echo "  4.  Start Frigate:          docker compose up -d"
echo "  5.  Start voice assistant:  python voice/assistant.py"
echo ""
