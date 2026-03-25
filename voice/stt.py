# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Argus Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
"""
stt.py — Hailo-8 hybrid Whisper speech-to-text

Architecture:
  Encoder → Hailo-8 NPU (compiled .hef, ~8× faster than CPU)
  Decoder → Pi 5 CPU via ONNX Runtime with KV caching

Falls back to faster-whisper (CPU only) if Hailo is unavailable,
so the assistant still works during development without the HAT.

Credit: ktomanek/edge_whisper for the hybrid inference approach.
"""

import os
import logging
import tempfile
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "models"
ENCODER_HEF  = MODELS_DIR / "whisper_tiny_encoder.hef"
DECODER_ONNX = MODELS_DIR / "whisper_tiny_decoder.onnx"
DECODER_ASSETS_DIR = MODELS_DIR / "decoder_assets" / "tiny" / "decoder_tokenization"

SAMPLE_RATE          = 16000
ENCODER_DURATION_SEC = 10
N_MELS               = 80
HOP_LENGTH           = 160
N_FFT                = 400


class HailoWhisperSTT:
    """
    Hybrid Hailo-8 encoder + CPU decoder Whisper transcription.
    Gracefully falls back to faster-whisper (CPU) if the HAT is absent.
    """

    def __init__(self, fallback_to_cpu: bool = True):
        self._hailo_ok = False
        self._fallback  = None
        self._try_init_hailo(fallback_to_cpu)

    # ─── Initialisation ───────────────────────────────────────────────────

    def _try_init_hailo(self, fallback: bool) -> None:
        if not ENCODER_HEF.exists():
            logger.warning(
                "Hailo encoder HEF not found at %s. "
                "Run scripts/download_models.sh first.", ENCODER_HEF
            )
            self._init_fallback(fallback)
            return

        try:
            import hailo_platform as hpf

            self._vdevice = hpf.VDevice()
            hef = hpf.HEF(str(ENCODER_HEF))
            cfg = hpf.ConfigureParams.create_from_hef(
                hef, interface=hpf.HailoStreamInterface.PCIe
            )
            self._ng       = self._vdevice.configure(hef, cfg)[0]
            self._ng_params = self._ng.create_params()
            self._in_params  = hpf.InputVStreamParams.make(
                self._ng, quantized=False, format_type=hpf.FormatType.FLOAT32
            )
            self._out_params = hpf.OutputVStreamParams.make(
                self._ng, quantized=False, format_type=hpf.FormatType.FLOAT32
            )
            self._init_cpu_decoder()
            self._hailo_ok = True
            logger.info("Hailo-8 Whisper encoder ready.")

        except Exception as exc:
            logger.warning("Hailo init failed (%s) — falling back to CPU.", exc)
            self._init_fallback(fallback)

    def _init_cpu_decoder(self) -> None:
        import onnxruntime as ort
        from transformers import WhisperProcessor

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 2

        self._dec_session = ort.InferenceSession(
            str(DECODER_ONNX),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self._onnx_add_input    = np.load(str(DECODER_ASSETS_DIR / "onnx_add_input_tiny.npy"))
        self._token_embedding   = np.load(str(DECODER_ASSETS_DIR / "token_embedding_weight_tiny.npy"))
        self._processor         = WhisperProcessor.from_pretrained("openai/whisper-tiny")
        logger.info("Whisper CPU decoder ready.")

    def _init_fallback(self, allow: bool) -> None:
        if not allow:
            raise RuntimeError("Hailo unavailable and CPU fallback disabled.")
        try:
            from faster_whisper import WhisperModel
            self._fallback = WhisperModel("base.en", device="cpu", compute_type="int8")
            logger.info(
                "STT: using faster-whisper (CPU). "
                "Attach Hailo-8 Pi AI HAT for ~8× speedup."
            )
        except ImportError:
            raise RuntimeError(
                "Neither Hailo nor faster-whisper is available. "
                "Run: pip install faster-whisper --break-system-packages"
            )

    # ─── Audio preprocessing ──────────────────────────────────────────────

    def _audio_to_mel(self, audio: np.ndarray) -> np.ndarray:
        import librosa

        target = SAMPLE_RATE * ENCODER_DURATION_SEC
        if len(audio) < target:
            audio = np.pad(audio, (0, target - len(audio)))
        else:
            audio = audio[:target]

        mel     = librosa.feature.melspectrogram(
            y=audio, sr=SAMPLE_RATE,
            n_fft=N_FFT, hop_length=HOP_LENGTH, n_mels=N_MELS,
        )
        log_mel = librosa.power_to_db(mel, ref=np.max)
        log_mel = (log_mel - log_mel.min()) / (log_mel.max() - log_mel.min() + 1e-8)
        return log_mel[np.newaxis, :, :].astype(np.float32)

    # ─── Hailo encoder ────────────────────────────────────────────────────

    def _encode_hailo(self, mel: np.ndarray) -> np.ndarray:
        import hailo_platform as hpf

        with hpf.InferVStreams(self._ng, self._in_params, self._out_params) as pipe:
            with self._ng.activate(self._ng_params):
                name = pipe.get_input_vstream_infos()[0].name
                pipe.send({name: mel})
                out  = pipe.recv()
        return list(out.values())[0]

    # ─── CPU decoder ──────────────────────────────────────────────────────

    def _decode_cpu(self, encoder_hidden_states: np.ndarray) -> str:
        tokenizer = self._processor.tokenizer
        bos       = tokenizer.encode("<|startoftranscript|>")[0]
        eot       = tokenizer.encode("<|endoftext|>")[0]

        input_ids = np.array([[bos]], dtype=np.int64)
        generated = [bos]
        past_kv   = None

        for _ in range(100):
            feed = {"input_ids": input_ids,
                    "encoder_hidden_states": encoder_hidden_states}
            if past_kv:
                feed.update(past_kv)

            outs    = self._dec_session.run(None, feed)
            logits  = outs[0]
            next_id = int(np.argmax(logits[0, -1, :]))

            if next_id == eot:
                break

            generated.append(next_id)
            input_ids = np.array([[next_id]], dtype=np.int64)

            names   = [o.name for o in self._dec_session.get_outputs()]
            past_kv = dict(zip(names[1:], outs[1:]))

        return tokenizer.decode(generated, skip_special_tokens=True).strip()

    # ─── Public API ───────────────────────────────────────────────────────

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe float32 16 kHz mono audio. Returns plain text."""
        if len(audio) < SAMPLE_RATE * 0.3:
            return ""

        if self._hailo_ok:
            mel     = self._audio_to_mel(audio)
            enc_out = self._encode_hailo(mel)
            return self._decode_cpu(enc_out)

        # CPU fallback
        import soundfile as sf
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio, SAMPLE_RATE)
            tmp = f.name
        try:
            segs, _ = self._fallback.transcribe(tmp, language="en")
            return " ".join(s.text for s in segs).strip()
        finally:
            os.unlink(tmp)

    @property
    def backend(self) -> str:
        return "hailo-8-hybrid" if self._hailo_ok else "faster-whisper-cpu"
