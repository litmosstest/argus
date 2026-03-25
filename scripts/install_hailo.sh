#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# install_hailo.sh — Hailo-10H driver + hailo-ollama setup for Argus
#
# Installs:
#   1. HailoRT PCIe driver (DKMS) — needed for Whisper STT on the NPU
#   2. hailo-ollama — Ollama-compatible LLM server for the Hailo-10H
#   3. Pulls the text LLM (Qwen2.5-1.5B) and vision model (llava-phi3)
#   4. Sets up hailo-ollama as a systemd service
#
# Must be run AFTER setup.sh. Reboots after driver installation.

set -euo pipefail

ARGUS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║      Hailo-10H driver + LLM setup   ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "OS:     $(lsb_release -ds 2>/dev/null || grep PRETTY /etc/os-release | cut -d= -f2)"
echo "Kernel: $(uname -r)"
echo ""

# ─── Verify Trixie ────────────────────────────────────────────────────────────
if ! grep -q "trixie\|13" /etc/os-release 2>/dev/null; then
    echo "⚠  Warning: designed for Raspberry Pi OS Trixie."
    read -rp "   Continue anyway? (y/N) " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 1
fi

# ─── Enable PCIe Gen 3 ────────────────────────────────────────────────────────
CONFIG=/boot/firmware/config.txt
if ! grep -q "pciex1_gen=3" "$CONFIG"; then
    echo "► Enabling PCIe Gen 3..."
    echo 'dtparam=pciex1_gen=3' | sudo tee -a "$CONFIG"
fi

# ─── Install dkms and kernel headers ─────────────────────────────────────────
echo "► Installing dkms..."
sudo apt install -y dkms linux-headers-$(uname -r)

# ─── Install HailoRT from Raspberry Pi repository ─────────────────────────────
# hailo-h10-all is the Hailo-10H metapackage — includes the correct PCIe driver,
# firmware, Python bindings, and TAPPAS for the AI HAT+ 2.
# NOTE: hailo-all is the Hailo-8 package — do NOT install that instead.
# Without hailo-h10-all the driver loads but never binds to the device,
# so /dev/hailo0 will not appear.
echo "► Installing HailoRT for Hailo-10H (hailo-h10-all)..."
sudo apt install -y hailo-h10-all

# ─── Fix PCIe page size (prevents Frigate inference errors) ──────────────────
MODPROBE_CONF=/etc/modprobe.d/hailo_pci.conf
if [ ! -f "$MODPROBE_CONF" ]; then
    echo "► Applying PCIe page size fix..."
    echo 'options hailo_pci force_desc_page_size=4096' | sudo tee "$MODPROBE_CONF"
fi

# ─── Ensure hailo_pci loads at boot ───────────────────────────────────────────
grep -q hailo_pci /etc/modules 2>/dev/null || echo 'hailo_pci' | sudo tee -a /etc/modules

# ─── Download and install hailo-ollama GenAI model zoo ───────────────────────
echo ""
echo "► Installing hailo-ollama (GenAI Model Zoo)..."
echo "  This requires registering at https://hailo.ai/developer-zone/"
echo "  then downloading the GenAI model zoo .deb for Raspberry Pi."
echo ""
echo "  Once downloaded, install with:"
echo "    sudo dpkg -i hailo_gen_ai_model_zoo_5.x.x_arm64.deb"
echo ""
echo "  Then pull the required models:"
echo "    hailo-ollama serve &"
echo "    curl -s http://localhost:8000/api/pull \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"model\": \"qwen2:1.5b\", \"stream\": false}'"
echo ""
echo "  Also pull the vision model for thumbnail descriptions:"
echo "    curl -s http://localhost:8000/api/pull \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"model\": \"llava-phi3\", \"stream\": false}'"
echo ""
echo "  See docs/troubleshooting.md for the full hailo-ollama setup steps."
echo ""

# ─── Install hailo-ollama systemd service (if binary is present) ─────────────
if command -v hailo-ollama &>/dev/null; then
    echo "► hailo-ollama found — setting up systemd service..."
    sudo tee /etc/systemd/system/hailo-ollama.service > /dev/null << 'EOF'
[Unit]
Description=Hailo Ollama LLM server
After=network.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/hailo-ollama
Restart=always
RestartSec=5
Environment=HAILO_LOG_LEVEL=warning

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable hailo-ollama
    echo "  ✓ hailo-ollama.service enabled (will start after reboot)"
else
    echo "  hailo-ollama not yet installed — complete the manual step above first."
fi

# ─── Reboot ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════╗"
echo "║  Hailo driver installed. Rebooting.  ║"
echo "║  After reboot, verify:               ║"
echo "║    ls -l /dev/hailo0                 ║"
echo "║    systemctl status hailo-ollama     ║"
echo "╚══════════════════════════════════════╝"
echo ""
sleep 3
sudo reboot
