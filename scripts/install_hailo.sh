#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# install_hailo.sh — Hailo-8 (Pi AI HAT+) driver setup for Argus
#
# Installs the Hailo PCIe driver using Frigate's official installation script,
# which builds the driver from source, installs firmware, and sets up udev rules.
#
# Supports both Raspberry Pi OS Bookworm and Trixie (64-bit).
# On Bookworm only: the first run disables the conflicting built-in kernel
# driver and reboots. Re-run the script after reboot to complete installation.
#
# Must be run AFTER setup.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║       Hailo-8 driver setup           ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "OS:     $(lsb_release -ds 2>/dev/null || grep PRETTY /etc/os-release | cut -d= -f2)"
echo "Kernel: $(uname -r)"
echo ""

# ─── Detect OS ────────────────────────────────────────────────────────────────
IS_BOOKWORM=false
IS_TRIXIE=false
if grep -qi "bookworm\|VERSION_ID=\"12\"" /etc/os-release 2>/dev/null; then
    IS_BOOKWORM=true
elif grep -qi "trixie\|VERSION_ID=\"13\"" /etc/os-release 2>/dev/null; then
    IS_TRIXIE=true
else
    echo "⚠  Unrecognised OS. Designed for Raspberry Pi OS Bookworm or Trixie."
    read -rp "   Continue anyway? (y/N) " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 1
fi

# ─── Reboot-required guard ────────────────────────────────────────────────────
#
# setup.sh runs apt full-upgrade, which can upgrade the kernel. If the system
# hasn't rebooted since that upgrade, the running kernel won't match the newly
# installed one and the driver will be compiled against the wrong headers.
#
# Debian sets /var/run/reboot-required whenever a package needing a reboot is
# installed. We also cross-check uname -r against the installed kernel headers
# to catch cases where the flag file was already cleared.
#
_NEED_REBOOT=false

if [ -f /var/run/reboot-required ]; then
    _NEED_REBOOT=true
fi

# Belt-and-suspenders: check that headers for the running kernel are installed
if ! dpkg -l "linux-headers-$(uname -r)" 2>/dev/null | grep -q "^ii"; then
    _NEED_REBOOT=true
fi

if $_NEED_REBOOT; then
    echo "✗  A system reboot is required before installing the Hailo driver."
    echo "   A kernel upgrade was installed but the system hasn't rebooted yet."
    echo "   Running kernel : $(uname -r)"
    echo ""
    echo "   Please reboot and then re-run this script:"
    echo "     sudo reboot"
    echo "     # (after reboot)"
    echo "     ./scripts/install_hailo.sh"
    echo ""
    exit 1
fi

# ─── Enable PCIe Gen 3 ────────────────────────────────────────────────────────
CONFIG=/boot/firmware/config.txt
if ! grep -q "pciex1_gen=3" "$CONFIG"; then
    echo "► Enabling PCIe Gen 3 in $CONFIG..."
    echo 'dtparam=pciex1_gen=3' | sudo tee -a "$CONFIG"
fi

# ─── Bookworm only: disable conflicting built-in kernel driver ────────────────
#
# Raspberry Pi OS Bookworm ships a Hailo kernel driver that is incompatible
# with the version required by Frigate. It must be renamed before installation.
# This step is skipped automatically on subsequent runs (bak file already exists).
#
if $IS_BOOKWORM; then
    BUILTIN=$(modinfo -n hailo_pci 2>/dev/null || true)
    if [ -n "$BUILTIN" ] && [ ! -f "${BUILTIN}.bak" ]; then
        echo ""
        echo "► Bookworm: disabling built-in Hailo kernel driver..."

        # Unload if currently loaded
        if lsmod | grep -q hailo_pci; then
            sudo modprobe -r hailo_pci
        fi

        # Rename, not delete — allows restoration if needed
        sudo mv "$BUILTIN" "${BUILTIN}.bak"
        sudo depmod -a

        echo ""
        echo "╔══════════════════════════════════════════════════════╗"
        echo "║  Built-in driver disabled. Reboot required.          ║"
        echo "║  After reboot, re-run this script to complete setup: ║"
        echo "║    ./scripts/install_hailo.sh                        ║"
        echo "╚══════════════════════════════════════════════════════╝"
        echo ""
        sleep 3
        sudo reboot
        exit 0
    elif [ -n "$BUILTIN" ] && [ -f "${BUILTIN}.bak" ]; then
        echo "► Bookworm: built-in driver already disabled — continuing"
    fi
fi

# ─── Download and run Frigate's official installation script ──────────────────
#
# This script builds the Hailo PCIe driver from source, installs firmware,
# and configures udev rules. Source:
# https://github.com/blakeblackshear/frigate/blob/dev/docker/hailo8l/user_installation.sh
#
INSTALL_SCRIPT="$(mktemp /tmp/hailo_install_XXXXXX.sh)"
trap 'rm -f "$INSTALL_SCRIPT"' EXIT

echo "► Downloading Frigate Hailo installation script..."
wget -q -O "$INSTALL_SCRIPT" \
    https://raw.githubusercontent.com/blakeblackshear/frigate/dev/docker/hailo8l/user_installation.sh
sudo chmod +x "$INSTALL_SCRIPT"

echo "► Running Frigate Hailo installation script..."
echo ""
"$INSTALL_SCRIPT"

# ─── Optional: fix PCIe descriptor page size ──────────────────────────────────
# Prevents: CHECK failed - max_desc_page_size given 16384 is bigger than
#           hw max desc page size 4096
MODPROBE_CONF=/etc/modprobe.d/hailo_pci.conf
if [ ! -f "$MODPROBE_CONF" ]; then
    echo "► Applying PCIe page size fix..."
    echo 'options hailo_pci force_desc_page_size=4096' | sudo tee "$MODPROBE_CONF"
fi

# ─── Reboot ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Driver installed. Rebooting to load firmware.       ║"
echo "║  After reboot, verify:                               ║"
echo "║    ls -l /dev/hailo0                                 ║"
echo "║    lsmod | grep hailo_pci                            ║"
echo "║    cat /sys/module/hailo_pci/version                 ║"
echo "║    ls -l /lib/firmware/hailo/hailo8_fw.bin           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
sleep 3
sudo reboot
