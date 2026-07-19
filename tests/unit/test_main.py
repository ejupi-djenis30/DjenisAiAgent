"""Unit tests for main.py FastAPI endpoints and queue helpers."""

from __future__ import annotations

import asyncio
import importlib
import json
import threading
import time

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from PIL import Image

pytest.importorskip("pyautogui")
pytest.importorskip("pywinauto")

TEST_OPERATOR_TOKEN = "test-operator-token-at-least-32-chars"


@pytest.fixture()
def main_module(monkeypatch: pytest.MonkeyPatch) -> object:
    module = importlib.import_module("main")
    module.runtime = module.create_runtime_context()
    module.manager.active_connections.clear()
    module.web_security.clear()
    monkeypatch.setattr(module.config, "web_auth_token", TEST_OPERATOR_TOKEN)
    monkeypatch.setattr(module.config, "web_allowed_origins", ())
    monkeypatch.setattr(module.config, "web_rate_limit_per_minute", 100)
    monkeypatch.setattr(module.config, "web_login_rate_limit_per_minute", 100)
    monkeypatch.setattr(module.config, "web_upload_max_bytes", 1024)
    monkeypatch.setattr(module.config, "web_max_sessions", 8)
    monkeypatch.setattr(module.config, "web_max_connections", 4)
    monkeypatch.setattr(module.config, "web_socket_send_timeout", 1.0)
    monkeypatch.setattr(module.config, "web_stream_max_clients", 2)
    monkeypatch.setattr(module.config, "web_transcription_max_concurrency", 1)
    monkeypatch.setattr(module.config, "web_transcription_timeout", 1.0)
    return module


def authenticate(client: TestClient) -> None:
    response = client.post(
        "/api/session",
        headers={
            "Authorization": f"Bearer {TEST_OPERATOR_TOKEN}",
            "Origin": "http://testserver",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


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
    with TestClient(main_module.app) as client:
        authenticate(client)
        with client.websocket_connect("/ws", headers={"Origin": "http://testserver"}) as websocket:
            initial = websocket.receive_json()
            websocket.send_text(json.dumps({"type": "bogus", "payload": "hello"}))
            invalid = websocket.receive_json()

    assert initial["type"] == "status"
    assert invalid["type"] == "log"
    assert "Invalid message" in invalid["payload"]


def test_websocket_requires_session_and_same_origin(main_module: object) -> None:
    with TestClient(main_module.app) as client:
        with (
            pytest.raises(WebSocketDisconnect) as unauthenticated,
            client.websocket_connect("/ws", headers={"Origin": "http://testserver"}),
        ):
            pass
        assert unauthenticated.value.code == 4401

        authenticate(client)
        with pytest.raises(WebSocketDisconnect) as missing_origin, client.websocket_connect("/ws"):
            pass
        assert missing_origin.value.code == 4403

        with (
            pytest.raises(WebSocketDisconnect) as denied_origin,
            client.websocket_connect("/ws", headers={"Origin": "https://attacker.example"}),
        ):
            pass
        assert denied_origin.value.code == 4403


def test_session_rejects_invalid_token_and_origin(main_module: object) -> None:
    with TestClient(main_module.app) as client:
        invalid_token = client.post(
            "/api/session",
            headers={
                "Authorization": "Bearer definitely-not-valid",
                "Origin": "http://testserver",
            },
        )
        invalid_origin = client.post(
            "/api/session",
            headers={
                "Authorization": f"Bearer {TEST_OPERATOR_TOKEN}",
                "Origin": "https://attacker.example",
            },
        )

    assert invalid_token.status_code == 401
    assert invalid_origin.status_code == 403


def test_login_rate_limit_blocks_repeated_attempts(
    main_module: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module.config, "web_login_rate_limit_per_minute", 1)

    with TestClient(main_module.app) as client:
        first = client.post(
            "/api/session",
            headers={
                "Authorization": "Bearer invalid-token",
                "Origin": "http://testserver",
            },
        )
        second = client.post(
            "/api/session",
            headers={
                "Authorization": f"Bearer {TEST_OPERATOR_TOKEN}",
                "Origin": "http://testserver",
            },
        )

    assert first.status_code == 401
    assert second.status_code == 429


def test_session_logout_revokes_cookie(main_module: object) -> None:
    with TestClient(main_module.app) as client:
        authenticate(client)
        logout = client.delete("/api/session", headers={"Origin": "http://testserver"})
        protected = client.post(
            "/api/transcribe",
            headers={"Origin": "http://testserver"},
            files={"file": ("clip.wav", b"RIFFdata", "audio/wav")},
        )

    assert logout.status_code == 204
    assert protected.status_code == 401


def test_cookie_authenticated_mutation_requires_origin(main_module: object) -> None:
    with TestClient(main_module.app) as client:
        authenticate(client)
        response = client.delete("/api/session")

    assert response.status_code == 403
    assert response.json()["detail"] == "Origin required"


def test_invalid_authorization_header_does_not_fall_back_to_cookie(main_module: object) -> None:
    with TestClient(main_module.app) as client:
        authenticate(client)
        response = client.get(
            "/api/session",
            headers={"Authorization": "Bearer an-invalid-replacement-token"},
        )

    assert response.status_code == 401


def test_logout_closes_websocket_bound_to_revoked_session(main_module: object) -> None:
    with TestClient(main_module.app) as client:
        authenticate(client)
        with client.websocket_connect("/ws", headers={"Origin": "http://testserver"}) as websocket:
            websocket.receive_json()
            response = client.delete("/api/session", headers={"Origin": "http://testserver"})
            with pytest.raises(WebSocketDisconnect) as disconnected:
                websocket.receive_json()

    assert response.status_code == 204
    assert disconnected.value.code == 4401


def test_websocket_connection_limit_is_enforced(
    main_module: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module.config, "web_max_connections", 1)

    with TestClient(main_module.app) as client:
        authenticate(client)
        with client.websocket_connect("/ws", headers={"Origin": "http://testserver"}) as first:
            first.receive_json()
            with (
                pytest.raises(WebSocketDisconnect) as rejected,
                client.websocket_connect("/ws", headers={"Origin": "http://testserver"}),
            ):
                pass

    assert rejected.value.code == 4429


@pytest.mark.asyncio
async def test_expired_websocket_does_not_consume_connection_capacity(
    main_module: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module.config, "web_max_connections", 1)

    class FakeWebSocket:
        def __init__(self) -> None:
            self.accepted = False
            self.closed: tuple[int, str] | None = None

        async def accept(self) -> None:
            self.accepted = True

        async def close(self, *, code: int, reason: str) -> None:
            self.closed = (code, reason)

    expired_socket = FakeWebSocket()
    replacement_socket = FakeWebSocket()
    expired_session = main_module.web_security.create_session()
    replacement_session = main_module.web_security.create_session()
    assert await main_module.manager.connect(expired_socket, expired_session) is True

    main_module.web_security.revoke_session(expired_session)
    assert await main_module.manager.connect(replacement_socket, replacement_session) is True

    assert expired_socket.closed == (4401, "Session expired")
    assert replacement_socket.accepted is True
    assert list(main_module.manager.active_connections) == [replacement_socket]


def test_stream_requires_authentication(main_module: object) -> None:
    with TestClient(main_module.app) as client:
        response = client.get("/stream")

    assert response.status_code == 401


def test_websocket_command_queues_work_and_broadcasts_status(main_module: object) -> None:
    with TestClient(main_module.app) as client:
        authenticate(client)
        with client.websocket_connect("/ws", headers={"Origin": "http://testserver"}) as websocket:
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

    with TestClient(main_module.app) as client:
        authenticate(client)
        with client.websocket_connect("/ws", headers={"Origin": "http://testserver"}) as websocket:
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
    monkeypatch.setattr(main_module, "transcribe_wav_bytes", lambda audio_bytes: "hello")

    with TestClient(main_module.app) as client:
        authenticate(client)
        response = client.post(
            "/api/transcribe",
            headers={"Origin": "http://testserver"},
            files={"file": ("clip.wav", b"RIFFdata", "audio/wav")},
        )

    assert response.status_code == 200
    assert response.json() == {"transcript": "hello"}


def test_transcribe_audio_endpoint_handles_disabled_empty_and_invalid_audio(
    main_module: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(main_module.app) as client:
        authenticate(client)
        monkeypatch.setattr(main_module.config, "enable_local_transcription", False)
        disabled = client.post(
            "/api/transcribe",
            headers={"Origin": "http://testserver"},
            files={"file": ("clip.wav", b"RIFFdata", "audio/wav")},
        )

        monkeypatch.setattr(main_module.config, "enable_local_transcription", True)
        empty = client.post(
            "/api/transcribe",
            headers={"Origin": "http://testserver"},
            files={"file": ("clip.wav", b"", "audio/wav")},
        )

        def raise_transcription_error(audio_bytes: bytes) -> str:
            raise main_module.TranscriptionError("bad wav")

        monkeypatch.setattr(main_module, "transcribe_wav_bytes", raise_transcription_error)
        invalid = client.post(
            "/api/transcribe",
            headers={"Origin": "http://testserver"},
            files={"file": ("clip.wav", b"RIFFdata", "audio/wav")},
        )

    assert disabled.status_code == 503
    assert empty.status_code == 400
    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "bad wav"


def test_transcribe_rejects_unauthenticated_unsupported_and_large_uploads(
    main_module: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module.config, "enable_local_transcription", True)
    monkeypatch.setattr(main_module.config, "web_upload_max_bytes", 8)

    with TestClient(main_module.app) as client:
        unauthenticated = client.post(
            "/api/transcribe",
            headers={"Origin": "http://testserver"},
            files={"file": ("clip.wav", b"RIFFdata", "audio/wav")},
        )
        authenticate(client)
        unsupported = client.post(
            "/api/transcribe",
            headers={"Origin": "http://testserver"},
            files={"file": ("clip.mp3", b"audio", "audio/mpeg")},
        )
        too_large = client.post(
            "/api/transcribe",
            headers={"Origin": "http://testserver"},
            files={"file": ("clip.wav", b"012345678", "audio/wav")},
        )

    assert unauthenticated.status_code == 401
    assert unsupported.status_code == 415
    assert too_large.status_code == 413


def test_transcribe_has_preparse_body_limit_and_bounded_workers(
    main_module: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module.config, "enable_local_transcription", True)
    monkeypatch.setattr(main_module.config, "web_upload_max_bytes", 64)
    monkeypatch.setattr(main_module.config, "web_transcription_timeout", 0.01)
    worker_release = threading.Event()

    def blocked_transcription(_audio_bytes: bytes) -> str:
        worker_release.wait(timeout=2)
        return "eventually complete"

    monkeypatch.setattr(main_module, "transcribe_wav_bytes", blocked_transcription)

    with TestClient(main_module.app) as client:
        oversized = client.post(
            "/api/transcribe",
            headers={"Content-Length": "70000", "Origin": "http://testserver"},
        )
        authenticate(client)
        timed_out = client.post(
            "/api/transcribe",
            headers={"Origin": "http://testserver"},
            files={"file": ("clip.wav", b"RIFFdata", "audio/wav")},
        )
        busy = client.post(
            "/api/transcribe",
            headers={"Origin": "http://testserver"},
            files={"file": ("clip.wav", b"RIFFdata", "audio/wav")},
        )

        worker_release.set()
        deadline = time.monotonic() + 2
        while main_module.runtime.active_transcriptions and time.monotonic() < deadline:
            time.sleep(0.01)

    assert oversized.status_code == 413
    assert timed_out.status_code == 504
    assert busy.status_code == 429
    assert main_module.runtime.active_transcriptions == 0


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
    monkeypatch.setattr(main_module.web_security, "require_request", lambda request, action: None)
    response = await main_module.video_stream(object())

    assert frame.startswith(b"--frame\r\nContent-Type: image/jpeg")
    assert response.media_type == "multipart/x-mixed-replace; boundary=frame"


@pytest.mark.asyncio
async def test_video_stream_rejects_unsupported_runtime_and_releases_capacity(
    main_module: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module.web_security, "require_request", lambda request, action: None)
    monkeypatch.setattr(main_module.config, "supports_native_desktop", lambda: False)

    with pytest.raises(main_module.HTTPException) as unavailable:
        await main_module.video_stream(object())
    assert unavailable.value.status_code == 503

    monkeypatch.setattr(main_module.config, "supports_native_desktop", lambda: True)
    monkeypatch.setattr(main_module.config, "web_stream_max_clients", 1)

    async def one_frame():
        yield b"frame"

    monkeypatch.setattr(main_module, "screen_generator", one_frame)
    response = await main_module.video_stream(object())
    iterator = response.body_iterator
    assert await iterator.__anext__() == b"frame"
    with pytest.raises(StopAsyncIteration):
        await iterator.__anext__()

    assert main_module.runtime.active_streams == 0


@pytest.mark.asyncio
async def test_web_runtime_cancels_workers_when_server_stops(
    main_module: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker_stopped = asyncio.Event()

    class FakeServer:
        should_exit = False

        async def serve(self) -> None:
            await asyncio.sleep(0)

    fake_server = FakeServer()

    async def worker(*_args: object) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            worker_stopped.set()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main_module.config, "validate_web", lambda: True)
    monkeypatch.setattr(main_module.uvicorn, "Config", lambda *args, **kwargs: object())
    monkeypatch.setattr(main_module.uvicorn, "Server", lambda _config: fake_server)
    monkeypatch.setattr(main_module, "agent_loop", worker)
    monkeypatch.setattr(main_module, "status_broadcaster", worker)

    await main_module.run_web_mode_async("127.0.0.1", 8000)

    assert fake_server.should_exit is True
    assert main_module.runtime.task_cancel_event.is_set() is True
    assert worker_stopped.is_set() is True
