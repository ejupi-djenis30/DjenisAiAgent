"""Local audio transcription utilities using Vosk."""

from __future__ import annotations

import io
import json
import logging
import wave
from pathlib import Path
from threading import Lock
from typing import Any, Final

from src.config import config

stdlib_audioop: Any | None
try:
    import audioop as stdlib_audioop
except ImportError:  # pragma: no cover - minimal Python builds
    stdlib_audioop = None

try:
    from vosk import KaldiRecognizer as VoskKaldiRecognizer
    from vosk import Model as VoskModel
except ImportError:  # pragma: no cover - optional dependency during install
    VoskKaldiRecognizer = None
    VoskModel = None

logger = logging.getLogger(__name__)

audioop: Any | None = stdlib_audioop
KaldiRecognizer: Any = VoskKaldiRecognizer
Model: Any = VoskModel

_MODEL_LOCK: Final[Lock] = Lock()
_MODEL: Any = None


class TranscriptionError(RuntimeError):
    """Raised when local audio transcription cannot be completed."""


def _ensure_model() -> object:
    """Lazily load and cache the Vosk model defined in configuration."""

    if KaldiRecognizer is None or Model is None:  # pragma: no cover - import guard
        raise TranscriptionError(
            "The 'vosk' package is not installed. Run 'pip install vosk' or install "
            "the transcription extra."
        )

    global _MODEL
    if _MODEL is not None:
        return _MODEL

    model_path = config.vosk_model_path.strip()
    if not model_path:
        raise TranscriptionError(
            "Vosk cannot start because DJENIS_VOSK_MODEL_PATH is not configured."
        )

    path = Path(model_path)
    if not path.exists() or not path.is_dir():
        raise TranscriptionError(
            f"The Vosk model path '{model_path}' does not exist or is not a directory."
        )

    with _MODEL_LOCK:
        if _MODEL is None:
            logger.info("Loading the Vosk model from %s", path)
            try:
                _MODEL = Model(model_path)
            except Exception as exc:  # pragma: no cover - third party errors
                raise TranscriptionError(f"Could not load the Vosk model: {exc}") from exc
    return _MODEL


def _prepare_audio(wav_bytes: bytes, target_sample_rate: int) -> tuple[bytes, int]:
    """Validate raw WAV data, convert to mono 16-bit PCM and target sample rate."""

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        raise TranscriptionError("Audio must use 16-bit PCM (sample width = 2).")

    if channels not in (1, 2):
        raise TranscriptionError("Only mono or stereo audio is supported.")

    if audioop is None:
        raise TranscriptionError(
            "The standard 'audioop' module is not available in this Python runtime."
        )

    processed = frames

    if channels == 2:
        processed = audioop.tomono(processed, sample_width, 0.5, 0.5)
        channels = 1

    if sample_rate != target_sample_rate:
        try:
            processed, _ = audioop.ratecv(
                processed,
                sample_width,
                channels,
                sample_rate,
                target_sample_rate,
                None,
            )
        except Exception as exc:  # pragma: no cover - audioop specific failures
            raise TranscriptionError(
                f"Could not convert the sample rate ({sample_rate} → {target_sample_rate}): {exc}"
            ) from exc
        sample_rate = target_sample_rate

    return processed, sample_rate


def transcribe_wav_bytes(wav_bytes: bytes) -> str:
    """Transcribe audio data provided as WAV bytes using a local Vosk model."""

    if not wav_bytes:
        raise TranscriptionError("Invalid audio: the payload is empty.")

    target_sample_rate = config.transcription_sample_rate
    waveform, sample_rate = _prepare_audio(wav_bytes, target_sample_rate)

    model = _ensure_model()
    recognizer = KaldiRecognizer(model, sample_rate)
    recognizer.SetWords(True)

    buffer_size = 4000
    stream = io.BytesIO(waveform)

    while True:
        chunk = stream.read(buffer_size)
        if not chunk:
            break
        recognizer.AcceptWaveform(chunk)

    try:
        result_json = recognizer.FinalResult()
        result = json.loads(result_json)
    except json.JSONDecodeError as exc:  # pragma: no cover - unexpected recognizer output
        raise TranscriptionError(f"Vosk returned an invalid result: {exc}") from exc

    text = str(result.get("text", "")).strip()
    if not text:
        raise TranscriptionError("The transcription is empty. Check the microphone and try again.")

    logger.debug("Local transcription produced %d characters", len(text))
    return text


__all__ = ["TranscriptionError", "transcribe_wav_bytes"]
