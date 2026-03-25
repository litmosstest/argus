#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# download_models.sh — downloads Whisper Hailo-8 model assets and Piper TTS voice model
#
# Downloads:
#   - Whisper Tiny encoder HEF (compiled for Hailo-8)
#   - Whisper Tiny decoder ONNX (runs on CPU with KV caching)
#   - Decoder tokenization assets (from ktomanek/edge_whisper)
#   - Piper TTS en_GB-alan-medium voice model

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS_DIR="$SCRIPT_DIR/../voice/models"
ASSETS_DIR="$MODELS_DIR/decoder_assets/tiny/decoder_tokenization"

mkdir -p "$MODELS_DIR" "$ASSETS_DIR"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║      Downloading Argus models        ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ─── Whisper encoder HEF (Hailo-8) ────────────────────────────────────────────
ENCODER_HEF="$MODELS_DIR/whisper_tiny_encoder.hef"
if [ ! -f "$ENCODER_HEF" ]; then
    echo "► Whisper Tiny encoder HEF (Hailo-8)..."
    wget -q --show-progress \
        "https://github.com/ktomanek/edge_whisper/raw/main/assets/hailo/hailo8l/whisper_tiny_encoder.hef" \
        -O "$ENCODER_HEF"
    echo "  ✓ Encoder HEF downloaded"
else
    echo "► Encoder HEF already present — skipping"
fi

# ─── Whisper decoder ONNX (CPU-side with KV cache) ───────────────────────────
DECODER_ONNX="$MODELS_DIR/whisper_tiny_decoder.onnx"
if [ ! -f "$DECODER_ONNX" ]; then
    echo "► Exporting Whisper Tiny decoder to ONNX..."
    pip install optimum --break-system-packages -q

    python3 - <<'PYEOF'
import os, shutil
from optimum.exporters.onnx import main_export

main_export(
    model_name_or_path="openai/whisper-tiny",
    output="__decoder_tmp",
    task="automatic-speech-recognition",
    opset=14,
    device="cpu",
)
shutil.copy("__decoder_tmp/decoder_model_merged.onnx", "DECODER_OUT")
shutil.rmtree("__decoder_tmp")
PYEOF

    mv DECODER_OUT "$DECODER_ONNX"
    echo "  ✓ Decoder ONNX exported"
else
    echo "► Decoder ONNX already present — skipping"
fi

# ─── Decoder tokenization assets ─────────────────────────────────────────────
ONNX_ADD="$ASSETS_DIR/onnx_add_input_tiny.npy"
TOKEN_EMB="$ASSETS_DIR/token_embedding_weight_tiny.npy"

if [ ! -f "$ONNX_ADD" ] || [ ! -f "$TOKEN_EMB" ]; then
    echo "► Decoder tokenization assets..."
    BASE="https://github.com/ktomanek/edge_whisper/raw/main/inference/on_hailo/decoder_assets/tiny/decoder_tokenization"
    wget -q --show-progress "$BASE/onnx_add_input_tiny.npy"       -O "$ONNX_ADD"
    wget -q --show-progress "$BASE/token_embedding_weight_tiny.npy" -O "$TOKEN_EMB"
    echo "  ✓ Tokenization assets downloaded"
else
    echo "► Tokenization assets already present — skipping"
fi

# ─── Piper TTS voice model ────────────────────────────────────────────────────
PIPER_MODEL="$MODELS_DIR/en_GB-alan-medium.onnx"
PIPER_JSON="$MODELS_DIR/en_GB-alan-medium.onnx.json"

if [ ! -f "$PIPER_MODEL" ]; then
    echo "► Piper TTS voice model (en_GB-alan-medium)..."
    BASE="https://github.com/rhasspy/piper/releases/download/2023.11.14-2"
    wget -q --show-progress "$BASE/en_GB-alan-medium.onnx"      -O "$PIPER_MODEL"
    wget -q --show-progress "$BASE/en_GB-alan-medium.onnx.json" -O "$PIPER_JSON"
    echo "  ✓ Piper voice model downloaded"
else
    echo "► Piper voice model already present — skipping"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════╗"
echo "║          Models ready ✓              ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Files in voice/models:"
find "$MODELS_DIR" -type f | sort | sed 's|.*/voice/models/||' | sed 's/^/  /'
echo ""
echo "Next: pip install -r voice/requirements.txt --break-system-packages"
echo "Then: python voice/assistant.py"
echo ""
