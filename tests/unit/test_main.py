"""Unit tests for main.py FastAPI endpoints and queue helpers."""

from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

pytest.importorskip("pyautogui")
pytest.importorskip("pywinauto")


@pytest.fixture()
def main_module() -> object:
    module = importlib.import_module("main")
    module.runtime = module.create_runtime_context()
    module.manager.active_connections.clear()
    return module


@pytest.mark.asyncio
async def test_enqueue_command_trims_and_rejects_empty(main_module: object) -> None:
    assert await main_module.enqueue_command("   ") is False
    assert await main_module.enqueue_command("  do something  ") is True
    assert main_module.runtime.command_queue.get_nowait() == "do something"


@pytest.mark.asyncio
async def test_request_task_cancellation_drains_queue(main_module: object) -> None:
    await main_module.runtime.command_queue.put("first")
    await main_module.runtime.command_queue.put("second")

    drained = await main_module.request_task_cancellation("stop now")

    assert drained == 2
    assert main_module.runtime.task_cancel_event.is_set() is True
    assert main_module.runtime.command_queue.empty() is True
    assert await main_module.runtime.status_queue.get() == "stop now"


def test_health_and_root_endpoints(main_module: object) -> None:
    main_module.runtime.agent_state = "running"

    with TestClient(main_module.app) as client:
        health = client.get("/health")
        root = client.get("/")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["agent_state"] == "running"
    assert root.status_code == 200
    assert "DjenisAiAgent" in root.text


def test_websocket_rejects_invalid_payload(main_module: object) -> None:
    with TestClient(main_module.app) as client, client.websocket_connect("/ws") as websocket:
        initial = websocket.receive_json()
        websocket.send_text(json.dumps({"type": "bogus", "payload": "hello"}))
        invalid = websocket.receive_json()

    assert initial["type"] == "status"
    assert invalid["type"] == "log"
    assert "Invalid message" in invalid["payload"]


def test_websocket_command_queues_work_and_broadcasts_status(main_module: object) -> None:
    with TestClient(main_module.app) as client, client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_text(json.dumps({"type": "command", "payload": "  open notepad  "}))
        messages = [websocket.receive_json(), websocket.receive_json()]

    types = {message["type"] for message in messages}
    assert types == {"status", "log"}
    assert main_module.runtime.command_queue.get_nowait() == "open notepad"
    assert main_module.runtime.agent_state == "running"
    assert any(
        "Command queued" in message["payload"] for message in messages if message["type"] == "log"
    )


def test_websocket_cancel_clears_queue(main_module: object) -> None:
    main_module.runtime.command_queue.put_nowait("queued")

    with TestClient(main_module.app) as client, client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_text(json.dumps({"type": "cancel", "payload": ""}))
        messages = [websocket.receive_json(), websocket.receive_json()]

    assert main_module.runtime.task_cancel_event.is_set() is True
    assert main_module.runtime.command_queue.empty() is True
    assert main_module.runtime.agent_state == "cancelling"
    assert any(
        "Cancellation requested" in message["payload"]
        for message in messages
        if message["type"] == "log"
    )


def test_transcribe_audio_endpoint_success(
    main_module: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module.config, "enable_local_transcription", True)
    monkeypatch.setattr(main_module, "transcribe_wav_bytes", lambda audio_bytes: "ciao")

    with TestClient(main_module.app) as client:
        response = client.post(
            "/api/transcribe",
            files={"file": ("clip.wav", b"RIFFdata", "audio/wav")},
        )

    assert response.status_code == 200
    assert response.json() == {"transcript": "ciao"}


def test_transcribe_audio_endpoint_handles_disabled_empty_and_invalid_audio(
    main_module: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(main_module.app) as client:
        monkeypatch.setattr(main_module.config, "enable_local_transcription", False)
        disabled = client.post(
            "/api/transcribe",
            files={"file": ("clip.wav", b"RIFFdata", "audio/wav")},
        )

        monkeypatch.setattr(main_module.config, "enable_local_transcription", True)
        empty = client.post(
            "/api/transcribe",
            files={"file": ("clip.wav", b"", "audio/wav")},
        )

        def raise_transcription_error(audio_bytes: bytes) -> str:
            raise main_module.TranscriptionError("bad wav")

        monkeypatch.setattr(main_module, "transcribe_wav_bytes", raise_transcription_error)
        invalid = client.post(
            "/api/transcribe",
            files={"file": ("clip.wav", b"RIFFdata", "audio/wav")},
        )

    assert disabled.status_code == 503
    assert empty.status_code == 400
    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "bad wav"


@pytest.mark.asyncio
async def test_screen_generator_and_video_stream(
    main_module: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module.config, "stream_resize_factor", 0.5)
    monkeypatch.setattr(main_module.config, "stream_frame_quality", 70)
    monkeypatch.setattr(main_module.config, "stream_max_fps", 5)
    monkeypatch.setattr(
        main_module.pyautogui, "screenshot", lambda: Image.new("RGB", (20, 20), "white")
    )

    generator = main_module.screen_generator()
    frame = await generator.__anext__()
    await generator.aclose()
    response = await main_module.video_stream()

    assert frame.startswith(b"--frame\r\nContent-Type: image/jpeg")
    assert response.media_type == "multipart/x-mixed-replace; boundary=frame"
