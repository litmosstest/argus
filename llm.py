# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
"""
llm.py — Local LLM client for Argus

Calls hailo-ollama running on the Hailo-10H NPU via its Ollama-compatible
REST API (http://localhost:8000/api/chat).

No cloud dependency. No API key required.
Model: Qwen2.5-1.5B (default) — ~6-8 tokens/sec on Hailo-10H.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime

from frigate_events import get_recent_events, format_events_for_context, FrigateLiveEvents

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are Argus — a local AI security camera assistant running on a Raspberry Pi 5 \
with a Hailo-10H AI accelerator. You help the user understand what their cameras have detected.

You will be given a log of recent detection events from Frigate NVR. Answer the user's \
question based strictly on this data. Be concise — your answer will be spoken aloud, \
so use plain sentences with no markdown, bullet points, or special characters.

If the answer is not in the event data, say so briefly. Do not guess or invent events.\
"""


def _call_hailo_ollama(
    messages: list[dict],
    base_url: str,
    model: str,
    timeout: int = 30,
) -> str:
    """
    POST to hailo-ollama /api/chat and return the response text.
    Raises RuntimeError on connection failure so callers can handle gracefully.
    """
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data["message"]["content"].strip()
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach hailo-ollama at {base_url}. "
            f"Is it running? (sudo systemctl status hailo-ollama) — {exc}"
        ) from exc
    except (KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unexpected response from hailo-ollama: {exc}") from exc


def ask_local_llm(
    question: str,
    db_path: str,
    live_events: FrigateLiveEvents,
    camera_names: list[str] | None = None,
    hours: int = 24,
    limit: int = 20,
    base_url: str = "http://localhost:8000",
    model: str = "qwen2:1.5b",
) -> str:
    """
    Query the local Hailo-10H LLM with Frigate event context.
    Returns a plain string suitable for TTS playback.
    """
    # Build event context from SQLite history
    try:
        history = get_recent_events(db_path, hours=hours, limit=limit)
        history_text = format_events_for_context(history)
    except FileNotFoundError as exc:
        history_text = f"(Event history unavailable: {exc})"

    # Add live MQTT events (last few minutes)
    live = live_events.get_recent(n=5)
    if live:
        live_lines = ["Live events (past few minutes):"]
        for e in live:
            live_lines.append(
                f"  {e['timestamp']} — {e['type']} event: "
                f"{e['label']} on '{e['camera']}' ({e['score']:.0%} confidence)"
            )
        live_text = "\n".join(live_lines)
    else:
        live_text = "No live events in the past few minutes."

    cameras = ", ".join(camera_names) if camera_names else "webcam"
    now     = datetime.now().strftime("%Y-%m-%d %H:%M")

    user_content = (
        f"Current time: {now}\n"
        f"Active cameras: {cameras}\n\n"
        f"{history_text}\n\n"
        f"{live_text}\n\n"
        f"Question: {question}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]

    return _call_hailo_ollama(messages, base_url=base_url, model=model)
