# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
"""
thumbnail_describer.py

Subscribes to Frigate MQTT events. When a snapshot is available for a new
detection, fetches the image from the Frigate API and sends it to the local
vision-capable model running in hailo-ollama. The plain-text description is
stored in a local SQLite table so the voice assistant can include it as
camera context.

All inference is on-device — no cloud, no API keys.
Model default: llava-phi3 (override with HAILO_OLLAMA_VISION_MODEL).
"""

import base64
import json
import logging
import os
import sqlite3
import threading
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

_DEFAULT_DB = str(Path(__file__).parent.parent / "data" / "db" / "descriptions.db")

MQTT_HOST      = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT      = int(os.getenv("MQTT_PORT", "1883"))
FRIGATE_API    = os.getenv("FRIGATE_API_URL", "http://localhost:5000").rstrip("/")
OLLAMA_URL     = os.getenv("HAILO_OLLAMA_URL", "http://localhost:8000").rstrip("/")
VISION_MODEL   = os.getenv("HAILO_OLLAMA_VISION_MODEL", "llava-phi3")
DESCRIPTIONS_DB = os.getenv("DESCRIPTIONS_DB_PATH", _DEFAULT_DB)

VISION_PROMPT = (
    "Describe what you see in this security camera image in one or two plain "
    "sentences. Focus on people, vehicles, animals, and any notable activity. "
    "Do not use markdown and do not start with 'The image shows' or 'I see'."
)


class ThumbnailDescriber:
    """
    Background service that generates plain-text descriptions for Frigate
    event snapshots using the local hailo-ollama vision model.

    Descriptions are persisted in a SQLite table (event_descriptions) and
    can be included in the voice assistant's LLM context via
    frigate_events.get_descriptions().
    """

    def __init__(
        self,
        mqtt_host: str = MQTT_HOST,
        mqtt_port: int = MQTT_PORT,
        frigate_api: str = FRIGATE_API,
        ollama_url: str = OLLAMA_URL,
        vision_model: str = VISION_MODEL,
        db_path: str = DESCRIPTIONS_DB,
    ):
        self._frigate_api  = frigate_api
        self._ollama_url   = ollama_url
        self._vision_model = vision_model
        self._db_path      = db_path

        self._init_db()

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = lambda c, u, f, rc, p: c.subscribe("frigate/events")
        self._client.on_message = self._on_message
        self._client.connect_async(mqtt_host, mqtt_port)

        logger.info(
            "ThumbnailDescriber ready — model: %s  db: %s",
            vision_model,
            db_path,
        )

    # ── SQLite ────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS event_descriptions (
                    event_id    TEXT PRIMARY KEY,
                    camera      TEXT NOT NULL,
                    label       TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                )
                """
            )

    def _has_description(self, event_id: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM event_descriptions WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return row is not None

    def _save_description(
        self, event_id: str, camera: str, label: str, description: str
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO event_descriptions
                    (event_id, camera, label, description, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, camera, label, description, datetime.utcnow().isoformat()),
            )

    # ── MQTT ──────────────────────────────────────────────────────────────────

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            return

        event_type   = payload.get("type", "")
        after        = payload.get("after", {})
        event_id     = after.get("id")
        has_snapshot = after.get("has_snapshot", False)

        # Process "new" or "update" events once a snapshot is available
        if event_type not in ("new", "update"):
            return
        if not has_snapshot or not event_id:
            return
        if self._has_description(event_id):
            return

        threading.Thread(
            target=self._process_event,
            args=(event_id, after.get("camera", "unknown"), after.get("label", "object")),
            daemon=True,
        ).start()

    # ── Inference ─────────────────────────────────────────────────────────────

    def _fetch_snapshot(self, event_id: str) -> bytes | None:
        url = f"{self._frigate_api}/api/events/{event_id}/snapshot.jpg"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return resp.read()
        except urllib.error.URLError as exc:
            logger.debug("Could not fetch snapshot for %s: %s", event_id, exc)
            return None

    def _describe_image(self, image_bytes: bytes) -> str | None:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        payload = json.dumps(
            {
                "model": self._vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": VISION_PROMPT,
                        "images": [encoded],
                    }
                ],
                "stream": False,
            }
        ).encode()

        req = urllib.request.Request(
            f"{self._ollama_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
                return data["message"]["content"].strip()
        except (urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
            logger.debug("Vision inference failed: %s", exc)
            return None

    def _process_event(self, event_id: str, camera: str, label: str) -> None:
        image_bytes = self._fetch_snapshot(event_id)
        if not image_bytes:
            return

        description = self._describe_image(image_bytes)
        if not description:
            return

        self._save_description(event_id, camera, label, description)
        logger.info("[describer] %s %s — %s", camera, label, description)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
