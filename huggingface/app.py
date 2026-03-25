# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
"""
Argus — Hugging Face Spaces demo

Demonstrates the event query layer from the Argus project.

On the Pi, the full stack runs locally:
  Whisper STT (Hailo-8) → Qwen2.5 LLM (Hailo-8 via hailo-ollama) → Piper TTS

This Space runs the same query logic using the Hugging Face Inference API
so anyone can try it without owning a Pi. Set HF_TOKEN in Space secrets to enable.
"""

import os
import random
from datetime import datetime, timedelta

import gradio as gr
from huggingface_hub import InferenceClient

# ─── Sample event generator ───────────────────────────────────────────────────

LABELS  = ["person", "person", "person", "car", "cat", "dog", "car", "person"]
CAMERAS = ["front_door", "back_garden", "driveway", "side_gate"]


def generate_sample_events(n: int = 15) -> str:
    now   = datetime.now()
    lines = [f"Detection history ({n} events):"]
    for i in range(n):
        t      = now - timedelta(minutes=random.randint(i * 8, i * 8 + 30))
        label  = random.choice(LABELS)
        camera = random.choice(CAMERAS)
        score  = round(random.uniform(0.65, 0.97), 2)
        dur    = round(random.uniform(1.5, 45.0), 1)
        clip   = " [clip]" if random.random() > 0.4 else ""
        lines.append(
            f"  {t.strftime('%Y-%m-%d %H:%M:%S')} — {label} on '{camera}'"
            f" (confidence {score:.0%}, {dur}s){clip}"
        )
    return "\n".join(lines)


# ─── LLM query (HF Inference API — mirrors the on-device hailo-ollama call) ──

SYSTEM_PROMPT = """\
You are Argus — a local AI security camera assistant running on a Raspberry Pi 5 \
with a Hailo-8 AI accelerator. You help the user understand what their cameras \
have detected.

Answer based strictly on the event log provided. Be concise — your answer will \
be spoken aloud, so use plain sentences with no markdown or bullet points.

If the answer is not in the event data, say so briefly.\
"""

HF_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"   # mirrors the on-device model


def ask_llm(question: str, event_log: str) -> str:
    token = os.environ.get("HF_TOKEN")
    if not token:
        return (
            "⚠️ HF_TOKEN not set in Space secrets. "
            "Add it under Settings → Variables and secrets to enable queries."
        )
    if not question.strip():
        return "Please type a question."
    if not event_log.strip():
        return "Please add event data first (click 'Generate sample events')."

    client = InferenceClient(token=token)
    try:
        response = client.chat_completion(
            model=HF_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Event log:\n{event_log}\n\n"
                        f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                        f"Question: {question}"
                    ),
                },
            ],
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"Error: {exc}"


# ─── Gradio UI ────────────────────────────────────────────────────────────────

DESCRIPTION = """
## 🦅 Argus — edge AI camera assistant

Ask natural language questions about what your cameras have detected.

On the Pi, speech recognition and the LLM both run on the **Hailo-8 NPU** — \
no cloud, no API keys. This Space uses the HF Inference API to run the same \
[Qwen2.5-1.5B](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) model so \
you can try the query layer without the hardware.

**[GitHub repo](https://github.com/YOUR_USERNAME/argus)** · Apache 2.0
"""

EXAMPLES = [
    "Has anyone been detected in the last hour?",
    "What happened overnight?",
    "Which camera has seen the most activity?",
    "When was the last person detected?",
    "Were there any detections in the past ten minutes?",
]

with gr.Blocks(title="Argus", theme=gr.themes.Default()) as demo:
    gr.Markdown(DESCRIPTION)

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📋 Event log")
            event_log = gr.Textbox(
                label="Frigate detection events",
                lines=18,
                placeholder="Click 'Generate sample events' or paste your own Frigate export.",
                value=generate_sample_events(),
            )
            with gr.Row():
                gen_btn   = gr.Button("🔄 Generate sample events", variant="secondary")
                clear_btn = gr.Button("Clear", variant="secondary")

        with gr.Column(scale=1):
            gr.Markdown("### 🎙 Ask Argus")
            question = gr.Textbox(
                label="Your question",
                placeholder="e.g. Has anyone been detected in the last hour?",
                lines=2,
            )
            ask_btn = gr.Button("Ask", variant="primary")
            answer  = gr.Textbox(label="Argus's answer", lines=5, interactive=False)

            gr.Markdown("#### Example questions")
            for q in EXAMPLES:
                gr.Button(q, size="sm").click(fn=lambda x=q: x, outputs=question)

    gr.Markdown(
        "---\n"
        "**On the Pi**, Whisper speech recognition runs on the Hailo-8 NPU "
        "(~8× faster than CPU), and the LLM runs via hailo-ollama at ~6–8 tokens/sec. "
        "See the [setup guide](https://github.com/YOUR_USERNAME/argus) to build your own."
    )

    gen_btn.click(fn=generate_sample_events, outputs=event_log)
    clear_btn.click(fn=lambda: "", outputs=event_log)
    ask_btn.click(fn=ask_llm, inputs=[question, event_log], outputs=answer)
    question.submit(fn=ask_llm, inputs=[question, event_log], outputs=answer)

if __name__ == "__main__":
    demo.launch()
