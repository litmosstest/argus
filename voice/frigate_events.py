# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
"""
frigate_events.py

Queries Frigate's SQLite database for historical detection events and
maintains a live rolling buffer from the Frigate MQTT event stream.
Both sources are combined into the context window sent to the LLM.
"""

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
import logging

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


def get_recent_events(
    db_path: str,
    hours: int = 24,
    limit: int = 20,
) -> list[dict]:
    """
    Return recent Frigate detection events from SQLite.
    Raises FileNotFoundError if the database doesn't exist yet.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Frigate database not found at {path}. "
            "Has Frigate detected at least one event?"
        )

    cutoff = (datetime.now() - timedelta(hours=hours)).timestamp()
    conn   = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, camera, label,
                   ROUND(top_score, 2)             AS score,
                   start_time, end_time,
                   ROUND(end_time - start_time, 1) AS duration,
                   has_clip
            FROM events
            WHERE start_time >= ?
            ORDER BY start_time DESC
            LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()
    finally:
        conn.close()

    events = []
    for r in rows:
        start = datetime.fromtimestamp(r["start_time"]).strftime("%Y-%m-%d %H:%M:%S")
        end   = (
            datetime.fromtimestamp(r["end_time"]).strftime("%H:%M:%S")
            if r["end_time"] else "ongoing"
        )
        events.append({
            "id":       r["id"],
            "camera":   r["camera"],
            "label":    r["label"],
            "score":    r["score"],
            "start":    start,
            "end":      end,
            "duration": r["duration"],
            "clip":     bool(r["has_clip"]),
        })
    return events


def get_descriptions(descriptions_db_path: str, event_ids: list[str]) -> dict[str, str]:
    """
    Return a mapping of {event_id: description} for the given IDs.
    Returns an empty dict if the descriptions database does not yet exist.
    """
    path = Path(descriptions_db_path)
    if not path.exists() or not event_ids:
        return {}

    placeholders = ",".join("?" * len(event_ids))
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT event_id, description FROM event_descriptions "
            f"WHERE event_id IN ({placeholders})",
            event_ids,
        ).fetchall()
    finally:
        conn.close()

    return {r["event_id"]: r["description"] for r in rows}


def format_events_for_context(
    events: list[dict],
    descriptions: dict[str, str] | None = None,
) -> str:
    if not events:
        return "No detection events in the requested time window."
    lines = [f"Detection history ({len(events)} events):"]
    for e in events:
        clip = " [clip]" if e["clip"] else ""
        line = (
            f"  {e['start']} — {e['label']} on '{e['camera']}' "
            f"(confidence {e['score']:.0%}, {e['duration']}s){clip}"
        )
        if descriptions and e.get("id") in descriptions:
            line += f"\n    Snapshot: {descriptions[e['id']]}"
        lines.append(line)
    return "\n".join(lines)


class FrigateLiveEvents:
    """
    MQTT subscriber — keeps a rolling buffer of the most recent live
    Frigate detection events. Thread-safe.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        topic_prefix: str = "frigate",
        buffer_size: int = 50,
    ):
        self._buf  = []
        self._lock = threading.Lock()
        self._size = buffer_size

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = lambda c, u, f, rc, p: c.subscribe(
            f"{topic_prefix}/events"
        )
        self._client.on_message = self._on_message
        self._client.connect_async(host, port)
        self._client.loop_start()
        logger.info("MQTT live event subscriber started → %s:%d", host, port)

    def _on_message(self, client, userdata, msg):
        try:
            data  = json.loads(msg.payload.decode())
            after = data.get("after", {})
            if not after:
                return
            record = {
                "type":      data.get("type", ""),
                "camera":    after.get("camera", "unknown"),
                "label":     after.get("label", "unknown"),
                "score":     round(after.get("top_score", 0), 2),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with self._lock:
                self._buf.append(record)
                if len(self._buf) > self._size:
                    self._buf.pop(0)
        except (json.JSONDecodeError, KeyError):
            pass

    def get_recent(self, n: int = 5) -> list[dict]:
        with self._lock:
            return list(self._buf[-n:])

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()
