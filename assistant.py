# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
"""
assistant.py — Argus voice assistant

Fully local pipeline — no cloud, no API keys:
  ENTER → record mic → Hailo-10H Whisper STT → Hailo-10H LLM → Piper TTS

Controls:
  Press ENTER to start recording.
  Press ENTER again to stop.
  Ctrl+C to quit.
"""

import logging
import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import numpy as np
import sounddevice as sd

from frigate_events import FrigateLiveEvents
from llm import ask_local_llm
from stt import HailoWhisperSTT
from tts import PiperTTS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("argus")

# ─── Config ──────────────────────────────────────────────────────────────────

SAMPLE_RATE     = 16000
AUDIO_DEVICE    = int(os.environ.get("AUDIO_INPUT_DEVICE", 0))
FRIGATE_DB      = os.environ.get("FRIGATE_DB_PATH", "../data/db/frigate.db")
MQTT_HOST       = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT       = int(os.environ.get("MQTT_PORT", 1883))
CONTEXT_HOURS   = int(os.environ.get("VOICE_CONTEXT_HOURS", 24))
CONTEXT_EVENTS  = int(os.environ.get("VOICE_CONTEXT_EVENTS", 20))
OLLAMA_URL      = os.environ.get("HAILO_OLLAMA_URL", "http://localhost:8000")
OLLAMA_MODEL    = os.environ.get("HAILO_OLLAMA_MODEL", "qwen2:1.5b")


# ─── Audio recording ─────────────────────────────────────────────────────────

def record_until_keypress() -> np.ndarray:
    print("  🎙  Recording... press ENTER to stop.")
    chunks: list[np.ndarray] = []
    active = threading.Event()
    active.set()

    def cb(indata, frames, time, status):
        if active.is_set():
            chunks.append(indata.copy())

    def wait():
        input()
        active.clear()

    t = threading.Thread(target=wait, daemon=True)
    t.start()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        device=AUDIO_DEVICE,
        dtype="float32",
        callback=cb,
        blocksize=1024,
    ):
        t.join()

    return np.concatenate(chunks).flatten() if chunks else np.array([], dtype="float32")


# ─── Main loop ───────────────────────────────────────────────────────────────

def main():
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║           🦅  Argus voice assistant           ║")
    print("╠══════════════════════════════════════════════╣")

    print("║  Loading Whisper STT...                      ║")
    stt = HailoWhisperSTT(fallback_to_cpu=True)
    backend_str = f"{stt.backend:<38}"
    print(f"║  STT: {backend_str}║")

    tts = PiperTTS()

    print("║  Connecting to Frigate MQTT...               ║")
    live_events = FrigateLiveEvents(host=MQTT_HOST, port=MQTT_PORT)

    model_str = f"{OLLAMA_MODEL} @ {OLLAMA_URL}"
    print(f"║  LLM: {model_str:<38}║")
    print("╠══════════════════════════════════════════════╣")
    print("║  Press ENTER to ask a question. Ctrl+C quit. ║")
    print("╚══════════════════════════════════════════════╝")

    try:
        while True:
            input("\n[Press ENTER to start recording]")

            audio = record_until_keypress()
            if len(audio) < SAMPLE_RATE * 0.3:
                print("  ⚠  Too short — try again.")
                continue

            print("  ⏳ Transcribing...")
            question = stt.transcribe(audio)
            if not question:
                print("  ⚠  No speech detected — try again.")
                continue

            print(f"\n  You: {question}")
            print("  ⏳ Asking local LLM...")

            try:
                answer = ask_local_llm(
                    question=question,
                    db_path=FRIGATE_DB,
                    live_events=live_events,
                    hours=CONTEXT_HOURS,
                    limit=CONTEXT_EVENTS,
                    base_url=OLLAMA_URL,
                    model=OLLAMA_MODEL,
                )
            except RuntimeError as exc:
                answer = "Sorry, I couldn't reach the local language model right now."
                logger.error(exc)

            print(f"\n  Argus: {answer}")
            tts.speak(answer)

    except KeyboardInterrupt:
        print("\n\nShutting down.")
        live_events.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
