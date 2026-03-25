# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
"""
tts.py — Piper TTS wrapper

Local text-to-speech via piper-tts. Plays audio through ALSA (aplay).
Falls back to printing the text if piper is not installed.

Voice model: en_GB-alan-medium — UK English, medium quality.
Downloaded by scripts/download_models.sh.
"""

import os
import subprocess
import tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MODELS_DIR     = Path(__file__).parent / "models"
DEFAULT_MODEL  = MODELS_DIR / "en_GB-alan-medium.onnx"


class PiperTTS:

    def __init__(self, model_path: Path | None = None):
        self.model_path = Path(model_path or DEFAULT_MODEL)
        self._ok = self._check()

    def _check(self) -> bool:
        try:
            subprocess.run(["piper", "--help"], capture_output=True, check=True)
        except FileNotFoundError:
            logger.warning(
                "piper not found. Install: pip install piper-tts --break-system-packages"
            )
            return False
        if not self.model_path.exists():
            logger.warning(
                "Piper model not found at %s. Run scripts/download_models.sh.",
                self.model_path,
            )
            return False
        return True

    def speak(self, text: str) -> None:
        if not text:
            return
        if not self._ok:
            print(f"\n[Argus]: {text}\n")
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out = f.name
        try:
            subprocess.run(
                ["piper", "--model", str(self.model_path), "--output_file", out],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
            )
            subprocess.run(["aplay", "-q", out], check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            logger.error("TTS error: %s", exc.stderr.decode())
            print(f"\n[Argus]: {text}\n")
        finally:
            try:
                os.unlink(out)
            except OSError:
                pass
