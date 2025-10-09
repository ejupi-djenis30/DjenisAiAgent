"""Local audio transcription utilities using Vosk."""

from __future__ import annotations

try:
    import audioop  # type: ignore
except ImportError:  # pragma: no cover - minimal Python builds
    audioop = None  # type: ignore
import io
import json
import logging
import wave
from pathlib import Path
from threading import Lock
from typing import Final

try:
    from vosk import KaldiRecognizer, Model  # type: ignore
except ImportError as import_error:  # pragma: no cover - optional dependency during install
    KaldiRecognizer = None  # type: ignore
    Model = None  # type: ignore

from src.config import config

logger = logging.getLogger(__name__)

_MODEL_LOCK: Final[Lock] = Lock()
_MODEL: Model | None = None  # type: ignore[assignment]


class TranscriptionError(RuntimeError):
    """Raised when local audio transcription cannot be completed."""


def _ensure_model() -> object:
    """Lazily load and cache the Vosk model defined in configuration."""

    if KaldiRecognizer is None or Model is None:  # pragma: no cover - import guard
        raise TranscriptionError(
            "Il pacchetto 'vosk' non è installato. Esegui 'pip install vosk' oppure aggiorna requirements.txt."
        )

    global _MODEL
    if _MODEL is not None:
        return _MODEL

    model_path = config.vosk_model_path.strip()
    if not model_path:
        raise TranscriptionError(
            "Impossibile inizializzare Vosk: la variabile DJENIS_VOSK_MODEL_PATH non è configurata."
        )

    path = Path(model_path)
    if not path.exists() or not path.is_dir():
        raise TranscriptionError(
            f"Il percorso del modello Vosk '{model_path}' non esiste o non è una cartella valida."
        )

    with _MODEL_LOCK:
        if _MODEL is None:
            logger.info("Caricamento modello Vosk da %s", path)
            try:
                _MODEL = Model(model_path)  # type: ignore[call-arg]
            except Exception as exc:  # pragma: no cover - third party errors
                raise TranscriptionError(
                    f"Errore durante il caricamento del modello Vosk: {exc}"
                ) from exc
    return _MODEL  # type: ignore[return-value]


def _prepare_audio(wav_bytes: bytes, target_sample_rate: int) -> tuple[bytes, int]:
    """Validate raw WAV data, convert to mono 16-bit PCM and target sample rate."""

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        raise TranscriptionError("L'audio deve essere in formato PCM 16-bit (sample width = 2).")

    if channels not in (1, 2):
        raise TranscriptionError("Sono supportati solo audio mono o stereo.")

    if audioop is None:
        raise TranscriptionError(
            "Il modulo standard 'audioop' non è disponibile in questo interprete Python."
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
                f"Errore durante la conversione del sample rate ({sample_rate} → {target_sample_rate}): {exc}"
            ) from exc
        sample_rate = target_sample_rate

    return processed, sample_rate


def transcribe_wav_bytes(wav_bytes: bytes) -> str:
    """Transcribe audio data provided as WAV bytes using a local Vosk model."""

    if not wav_bytes:
        raise TranscriptionError("Audio non valido: payload vuoto.")

    target_sample_rate = config.transcription_sample_rate
    waveform, sample_rate = _prepare_audio(wav_bytes, target_sample_rate)

    model = _ensure_model()
    recognizer = KaldiRecognizer(model, sample_rate)  # type: ignore[call-arg]
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
        raise TranscriptionError(f"Risultato Vosk non valido: {exc}") from exc

    text = str(result.get("text", "")).strip()
    if not text:
        raise TranscriptionError("Trascrizione vuota: parla più chiaramente o verifica il microfono.")

    logger.debug("Trascrizione locale: %s", text)
    return text


__all__ = ["transcribe_wav_bytes", "TranscriptionError"]
