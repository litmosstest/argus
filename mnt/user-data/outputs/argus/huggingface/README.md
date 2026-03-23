---
title: Argus
emoji: 🦅
colorFrom: gray
colorTo: blue
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: apache-2.0
tags:
  - frigate
  - hailo
  - hailo-10h
  - raspberry-pi
  - edge-ai
  - object-detection
  - speech-recognition
  - whisper
  - local-llm
  - surveillance
short_description: Ask your cameras what they've seen — fully local AI on a Pi 5
---

# 🦅 Argus — Demo Space

Interactive companion to the [Argus GitHub repo](https://github.com/YOUR_USERNAME/argus).

**Argus** is a fully local AI camera system running on a Raspberry Pi 5 with a
Hailo-10H AI HAT+ 2. It detects objects with Frigate NVR, transcribes voice
questions with Whisper (on the Hailo NPU), and answers them with a local LLM
(Qwen2.5-1.5B via hailo-ollama) — no cloud, no API keys, no data leaving the device.

This Space demonstrates the **event query layer**: paste in Frigate detection events
(or generate sample ones) and ask natural language questions about them, exactly as
the on-device voice assistant does.

## Running the full stack locally

See the [GitHub repo](https://github.com/YOUR_USERNAME/argus) for hardware
requirements and step-by-step setup including Hailo-10H driver installation
and hailo-ollama LLM configuration.

## Licence

Apache 2.0
