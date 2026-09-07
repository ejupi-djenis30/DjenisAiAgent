"""Unit tests for src/perception/audio_transcription.py."""

from __future__ import annotations

import io
import json
import wave
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.perception import audio_transcription as audio_module


def _make_wav_bytes(
    *,
    channels: int = 1,
    sample_width: int = 2,
    sample_rate: int = 16_000,
    frames: bytes | None = None,
) -> bytes:
    frame_bytes = frames if frames is not None else (b"\x00\x00" * 16 * channels)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frame_bytes)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def reset_cached_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audio_module, "_MODEL", None)


class TestEnsureModel:
    def test_missing_vosk_dependency_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(audio_module, "KaldiRecognizer", None)
        monkeypatch.setattr(audio_module, "Model", None)

        with pytest.raises(audio_module.TranscriptionError, match="vosk"):
            audio_module._ensure_model()

    def test_missing_model_path_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(audio_module, "KaldiRecognizer", object())
        monkeypatch.setattr(audio_module, "Model", MagicMock())
        monkeypatch.setattr(audio_module.config, "vosk_model_path", "")

        with pytest.raises(audio_module.TranscriptionError, match="DJENIS_VOSK_MODEL_PATH"):
            audio_module._ensure_model()

    def test_invalid_model_path_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(audio_module, "KaldiRecognizer", object())
        monkeypatch.setattr(audio_module, "Model", MagicMock())
        monkeypatch.setattr(audio_module.config, "vosk_model_path", str(tmp_path / "missing-model"))

        with pytest.raises(audio_module.TranscriptionError, match="does not exist"):
            audio_module._ensure_model()

    def test_model_is_loaded_once_and_cached(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        model_dir = tmp_path / "vosk-model"
        model_dir.mkdir()
        mock_model_cls = MagicMock(return_value=object())

        monkeypatch.setattr(audio_module, "KaldiRecognizer", object())
        monkeypatch.setattr(audio_module, "Model", mock_model_cls)
        monkeypatch.setattr(audio_module.config, "vosk_model_path", str(model_dir))

        first = audio_module._ensure_model()
        second = audio_module._ensure_model()

        assert first is second
        mock_model_cls.assert_called_once_with(str(model_dir))

    def test_model_load_errors_are_wrapped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        model_dir = tmp_path / "vosk-model"
        model_dir.mkdir()

        monkeypatch.setattr(audio_module, "KaldiRecognizer", object())
        monkeypatch.setattr(audio_module, "Model", MagicMock(side_effect=RuntimeError("boom")))
        monkeypatch.setattr(audio_module.config, "vosk_model_path", str(model_dir))

        with pytest.raises(audio_module.TranscriptionError, match="load the Vosk model"):
            audio_module._ensure_model()


class TestPrepareAudio:
    @pytest.mark.parametrize(
        "wav_bytes",
        [
            b"not a wav",
            b"RIFF",
            b"RIFF\x00\x00\x00\x00WAVE",
            b"RIFF\x0c\x00\x00\x00WAVEJUNK\xff\xff\xff\x7f",
        ],
    )
    def test_malformed_wav_raises_a_controlled_error(self, wav_bytes: bytes) -> None:
        with pytest.raises(audio_module.TranscriptionError, match="PCM WAV"):
            audio_module._prepare_audio(wav_bytes, 16_000)

    @pytest.mark.parametrize("sample_rate", [1, 7_999, 192_001])
    def test_unsupported_input_rate_is_rejected_before_resampling(
        self, monkeypatch: pytest.MonkeyPatch, sample_rate: int
    ) -> None:
        fake_audioop = MagicMock()
        monkeypatch.setattr(audio_module, "audioop", fake_audioop)
        with pytest.raises(audio_module.TranscriptionError, match="Audio sample rate"):
            audio_module._prepare_audio(_make_wav_bytes(sample_rate=sample_rate), 16_000)
        fake_audioop.ratecv.assert_not_called()

    @pytest.mark.parametrize("target_rate", [0, 7_999, 48_001, 2**32])
    def test_unsupported_output_rate_is_rejected(self, target_rate: int) -> None:
        with pytest.raises(audio_module.TranscriptionError, match="transcription sample rate"):
            audio_module._prepare_audio(_make_wav_bytes(), target_rate)

    def test_duration_is_rejected_before_reading_or_resampling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(audio_module.config, "transcription_max_duration_seconds", 1)
        fake_audioop = MagicMock()
        monkeypatch.setattr(audio_module, "audioop", fake_audioop)
        wav_bytes = _make_wav_bytes(sample_rate=8_000, frames=b"\x00\x00" * 8_001)
        readframes = MagicMock(side_effect=AssertionError("frames must not be read"))
        monkeypatch.setattr(wave.Wave_read, "readframes", readframes)
        with pytest.raises(audio_module.TranscriptionError, match="duration limit"):
            audio_module._prepare_audio(wav_bytes, 16_000)
        readframes.assert_not_called()
        fake_audioop.ratecv.assert_not_called()

    @pytest.mark.parametrize("channels,sample_rate", [(1, 8_000), (2, 44_100), (1, 192_000)])
    def test_exact_duration_limit_remains_valid(
        self, monkeypatch: pytest.MonkeyPatch, channels: int, sample_rate: int
    ) -> None:
        monkeypatch.setattr(audio_module.config, "transcription_max_duration_seconds", 1)
        wav_bytes = _make_wav_bytes(
            channels=channels, sample_rate=sample_rate, frames=b"\x00\x00" * sample_rate * channels
        )
        processed, rate = audio_module._prepare_audio(wav_bytes, 16_000)
        assert rate == 16_000
        assert 0 < len(processed) <= 2 * rate

    @pytest.mark.parametrize("channels,frames", [(1, b"\x00" * 33), (2, b"\x00" * 7)])
    def test_incomplete_frames_are_rejected(self, channels: int, frames: bytes) -> None:
        with pytest.raises(audio_module.TranscriptionError, match="truncated or incomplete"):
            audio_module._prepare_audio(_make_wav_bytes(channels=channels, frames=frames), 16_000)

    def test_truncated_pcm_is_rejected(self) -> None:
        with pytest.raises(audio_module.TranscriptionError, match="truncated or incomplete"):
            audio_module._prepare_audio(_make_wav_bytes()[:-2], 16_000)

    def test_empty_pcm_is_rejected(self) -> None:
        with pytest.raises(audio_module.TranscriptionError, match="no complete frames"):
            audio_module._prepare_audio(_make_wav_bytes(frames=b""), 16_000)

    def test_direct_calls_preserve_the_upload_byte_limit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(audio_module.config, "web_upload_max_bytes", 20)
        with pytest.raises(audio_module.TranscriptionError, match="payload exceeds"):
            audio_module._prepare_audio(_make_wav_bytes(), 16_000)

    def test_invalid_sample_width_raises(self) -> None:
        wav_bytes = _make_wav_bytes(sample_width=1)

        with pytest.raises(audio_module.TranscriptionError, match="16-bit"):
            audio_module._prepare_audio(wav_bytes, 16_000)

    def test_invalid_channel_count_raises(self) -> None:
        wav_bytes = _make_wav_bytes(channels=3)

        with pytest.raises(audio_module.TranscriptionError, match="mono or stereo"):
            audio_module._prepare_audio(wav_bytes, 16_000)

    def test_missing_audioop_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        wav_bytes = _make_wav_bytes()
        monkeypatch.setattr(audio_module, "audioop", None)

        with pytest.raises(audio_module.TranscriptionError, match="audioop"):
            audio_module._prepare_audio(wav_bytes, 16_000)

    def test_stereo_audio_is_downmixed_and_resampled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        wav_bytes = _make_wav_bytes(channels=2, sample_rate=44_100)

        fake_audioop = MagicMock()
        fake_audioop.tomono.return_value = b"mono-bytes"
        fake_audioop.ratecv.return_value = (b"resampled-bytes", None)
        monkeypatch.setattr(audio_module, "audioop", fake_audioop)

        processed, sample_rate = audio_module._prepare_audio(wav_bytes, 16_000)

        assert processed == b"resampled-bytes"
        assert sample_rate == 16_000
        fake_audioop.tomono.assert_called_once()
        fake_audioop.ratecv.assert_called_once()

    def test_rate_conversion_errors_are_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        wav_bytes = _make_wav_bytes(sample_rate=44_100)

        fake_audioop = MagicMock()
        fake_audioop.ratecv.side_effect = RuntimeError("rate failure")
        monkeypatch.setattr(audio_module, "audioop", fake_audioop)

        with pytest.raises(audio_module.TranscriptionError, match="sample rate"):
            audio_module._prepare_audio(wav_bytes, 16_000)


class TestTranscribeWavBytes:
    def test_empty_payload_raises(self) -> None:
        with pytest.raises(audio_module.TranscriptionError, match="payload is empty"):
            audio_module.transcribe_wav_bytes(b"")

    def test_successful_transcription(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recognizer = MagicMock()
        recognizer.FinalResult.return_value = json.dumps({"text": "ciao mondo"})

        monkeypatch.setattr(audio_module.config, "transcription_sample_rate", 16_000)
        monkeypatch.setattr(audio_module, "_prepare_audio", lambda wav, rate: (b"a" * 9000, rate))
        monkeypatch.setattr(audio_module, "_ensure_model", lambda: object())
        monkeypatch.setattr(audio_module, "KaldiRecognizer", lambda model, rate: recognizer)

        result = audio_module.transcribe_wav_bytes(b"wav")

        assert result == "ciao mondo"
        recognizer.SetWords.assert_called_once_with(True)
        assert recognizer.AcceptWaveform.call_count >= 2

    def test_invalid_recognizer_json_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recognizer = MagicMock()
        recognizer.FinalResult.return_value = "not-json"

        monkeypatch.setattr(audio_module.config, "transcription_sample_rate", 16_000)
        monkeypatch.setattr(audio_module, "_prepare_audio", lambda wav, rate: (b"abc", rate))
        monkeypatch.setattr(audio_module, "_ensure_model", lambda: object())
        monkeypatch.setattr(audio_module, "KaldiRecognizer", lambda model, rate: recognizer)

        with pytest.raises(audio_module.TranscriptionError, match="invalid result"):
            audio_module.transcribe_wav_bytes(b"wav")

    def test_empty_transcription_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recognizer = MagicMock()
        recognizer.FinalResult.return_value = json.dumps({"text": "   "})

        monkeypatch.setattr(audio_module.config, "transcription_sample_rate", 16_000)
        monkeypatch.setattr(audio_module, "_prepare_audio", lambda wav, rate: (b"abc", rate))
        monkeypatch.setattr(audio_module, "_ensure_model", lambda: object())
        monkeypatch.setattr(audio_module, "KaldiRecognizer", lambda model, rate: recognizer)

        with pytest.raises(audio_module.TranscriptionError, match="transcription is empty"):
            audio_module.transcribe_wav_bytes(b"wav")
