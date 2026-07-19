"""Main entry point for DjenisAiAgent."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pyautogui

    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
import uvicorn
from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, field_validator

from src.config import VERSION, config
from src.orchestration.agent_loop import agent_loop, run_agent_loop
from src.perception.audio_transcription import TranscriptionError, transcribe_wav_bytes
from src.redaction import RedactingFormatter, safe_preview
from src.runtime_state import AgentState, create_runtime_state
from src.web_security import SESSION_COOKIE, web_security

IMAGE_RESAMPLING_LANCZOS = Image.Resampling.LANCZOS

# Application startup time for uptime calculation
_APP_START_TIME: float = time.time()

create_runtime_context = create_runtime_state
runtime = create_runtime_context()


async def enqueue_command(command: str) -> bool:
    """Enqueue a trimmed user command for agent processing."""
    cleaned = command.strip()
    if not cleaned:
        return False

    async with runtime.command_queue_lock:
        await runtime.command_queue.put(cleaned)
    logging.getLogger(__name__).info("Queued command (%d characters)", len(cleaned))
    return True


async def request_task_cancellation(reason: str | None = None) -> int:
    """Cancel the current task and clear queued commands.

    Args:
        reason: Optional message to broadcast alongside the cancellation.

    Returns:
        int: Number of queued commands that were discarded.
    """
    logger = logging.getLogger(__name__)
    runtime.task_cancel_event.set()
    if reason:
        await runtime.status_queue.put(reason)

    drained = 0
    async with runtime.command_queue_lock:
        while True:
            try:
                runtime.command_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                drained += 1
                runtime.command_queue.task_done()

    logger.info("Cancellation requested. Cleared %d queued commands.", drained)
    return drained


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events for the unified concurrent system.
    """
    logger = logging.getLogger(__name__)

    logger.info("Starting unified concurrent system: agent_loop + status_broadcaster")

    yield

    logger.info("Shutting down unified concurrent system")


async def status_broadcaster():
    """
    Background task that continuously broadcasts status messages from the agent to WebSocket clients.

    This function implements the critical link in the concurrent architecture:
        agent_loop -> status_queue -> status_broadcaster -> ConnectionManager -> WebSocket clients

    It runs indefinitely, consuming messages from the status_queue and broadcasting them
    to all connected WebSocket clients in real-time. This ensures that the web interface
    receives live updates about the agent's activity without blocking the agent or server.

    Architecture Role:
        This broadcaster is one of three concurrent tasks running together:
        1. FastAPI server (handles HTTP/WebSocket connections)
        2. agent_loop (processes commands from command_queue)
        3. status_broadcaster (this function - relays status to clients)

    The queue-based architecture ensures:
        - Non-blocking operation (agent never waits for broadcasts)
        - Decoupling (agent doesn't know about web clients)
        - Resilience (if broadcasting fails, agent continues)
        - Scalability (multiple clients can connect without affecting agent)
    """
    logger = logging.getLogger(__name__)
    logger.info("Status broadcaster started")

    try:
        while True:
            status_message = await runtime.status_queue.get()
            try:
                logger.debug("Broadcasting status: %s", safe_preview(status_message))

                new_state: AgentState | None = None
                if "Ready for next command" in status_message:
                    new_state = "idle"
                    logger.info("Agent state changing to 'idle' - ready for next command")
                elif (
                    "SUCCESS:" in status_message or "Task completed successfully" in status_message
                ):
                    new_state = "idle"
                    logger.info("Agent state changing to 'idle' - task completed successfully")
                elif "FAILED:" in status_message:
                    new_state = "idle"
                    logger.info("Agent state changing to 'idle' - task failed")
                elif "CANCELLED:" in status_message:
                    new_state = "idle"
                    logger.info("Agent state changing to 'idle' - task cancelled")

                if new_state:
                    await runtime.set_agent_state(new_state)
                    await manager.broadcast_json(
                        {
                            "type": "status",
                            "payload": {
                                "agent_state": new_state,
                                "message": status_message,
                            },
                        }
                    )
                else:
                    await manager.broadcast_json({"type": "log", "payload": status_message})
            except Exception as exc:
                # A failed client broadcast must not silently kill the control-plane worker.
                logger.error("Status broadcast failed: %s", safe_preview(exc), exc_info=True)
            finally:
                runtime.status_queue.task_done()
    except asyncio.CancelledError:
        logger.info("Status broadcaster cancelled, shutting down gracefully")
        raise


# Global FastAPI application instance with lifespan
app = FastAPI(
    title="DjenisAiAgent",
    description="AI-powered Windows automation agent",
    lifespan=lifespan,
)
WEB_STATIC_DIR = Path(__file__).parent / "web" / "static"
app.mount("/static", StaticFiles(directory=WEB_STATIC_DIR), name="static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Apply conservative browser defaults to the local operator console."""

    if request.method == "POST" and request.url.path == "/api/transcribe":
        # Multipart parsing happens before the endpoint body executes. Requiring a bounded
        # Content-Length prevents an oversized/chunked upload from filling the spool first.
        if request.headers.get("transfer-encoding"):
            response = JSONResponse(
                {"detail": "Chunked uploads are not accepted."}, status_code=411
            )
        else:
            raw_length = request.headers.get("content-length")
            try:
                content_length = int(raw_length) if raw_length is not None else -1
            except ValueError:
                content_length = -1
            request_limit = config.web_upload_max_bytes + 65_536
            if content_length < 0:
                response = JSONResponse(
                    {"detail": "A valid Content-Length header is required."}, status_code=411
                )
            elif content_length > request_limit:
                response = JSONResponse(
                    {"detail": "Request body exceeds the configured limit."}, status_code=413
                )
            else:
                response = await call_next(request)
    else:
        response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob:; "
        "connect-src 'self' ws: wss:; style-src 'self'; script-src 'self'",
    )
    return response


@dataclass
class ManagedConnection:
    """Bind a WebSocket to the opaque session that authenticated it."""

    session_id: str
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ConnectionManager:
    """
    Manages WebSocket connections for real-time communication with web clients.

    This class handles:
    - Accepting new WebSocket connections
    - Removing disconnected clients
    - Broadcasting messages to all active clients
    """

    def __init__(self):
        """Initialize the connection manager with an empty list of active connections."""
        self.active_connections: dict[WebSocket, ManagedConnection] = {}

    async def _evict_invalid_connections(self) -> None:
        """Close sockets whose backing sessions have expired or been evicted."""

        expired = [
            connection
            for connection, managed in self.active_connections.items()
            if not web_security.session_is_valid(managed.session_id)
        ]
        for connection in expired:
            self.disconnect(connection)
            with suppress(Exception):
                await connection.close(code=4401, reason="Session expired")

    async def connect(self, websocket: WebSocket, session_id: str) -> bool:
        """
        Accept a new WebSocket connection and add it to the active connections list.

        Args:
            websocket: The WebSocket connection to accept and manage
        """
        await self._evict_invalid_connections()
        if len(self.active_connections) >= config.web_max_connections:
            await websocket.close(code=4429, reason="Connection limit reached")
            return False
        await websocket.accept()
        self.active_connections[websocket] = ManagedConnection(session_id=session_id)
        logging.getLogger(__name__).info(
            f"New WebSocket connection. Total active: {len(self.active_connections)}"
        )
        return True

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection from the active connections list.

        Args:
            websocket: The WebSocket connection to remove
        """
        if websocket in self.active_connections:
            self.active_connections.pop(websocket, None)
            logging.getLogger(__name__).info(
                f"WebSocket disconnected. Total active: {len(self.active_connections)}"
            )

    async def broadcast(self, message: str) -> None:
        """
        Send a message to all active WebSocket clients.

        Args:
            message: The message string to broadcast
        """
        await self.broadcast_json({"type": "log", "payload": message})

    async def send_json(self, websocket: WebSocket, data: dict[str, object]) -> bool:
        """Serialize writes per connection and evict expired or stalled clients."""

        managed = self.active_connections.get(websocket)
        if managed is None:
            return False
        if not web_security.session_is_valid(managed.session_id):
            self.disconnect(websocket)
            with suppress(Exception):
                await websocket.close(code=4401, reason="Session expired")
            return False
        try:
            async with managed.send_lock:
                await asyncio.wait_for(
                    websocket.send_json(data),
                    timeout=config.web_socket_send_timeout,
                )
            return True
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Failed to send to WebSocket client: %s", safe_preview(exc)
            )
            self.disconnect(websocket)
            return False

    async def broadcast_json(self, data: dict[str, object]) -> None:
        """
        Send a JSON message to all active WebSocket clients.

        Args:
            data: The dictionary to broadcast as JSON
        """
        await self._evict_invalid_connections()
        await asyncio.gather(
            *(self.send_json(connection, data) for connection in list(self.active_connections)),
            return_exceptions=True,
        )

    async def disconnect_session(self, session_id: str | None) -> None:
        """Close every live socket owned by a revoked browser session."""

        if not session_id:
            return
        matches = [
            connection
            for connection, managed in self.active_connections.items()
            if managed.session_id == session_id
        ]
        for connection in matches:
            self.disconnect(connection)
            with suppress(Exception):
                await connection.close(code=4401, reason="Session revoked")


# Global ConnectionManager instance
manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Pydantic models — WebSocket payload validation
# ---------------------------------------------------------------------------


class WebSocketMessage(BaseModel):
    """Schema for messages received over the WebSocket connection."""

    type: str = "command"
    payload: str = ""

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"command", "cancel", "delete_task"}
        normalized = v.strip().lower()
        if normalized not in allowed:
            raise ValueError(f"Unknown message type: {v!r}. Allowed: {sorted(allowed)}")
        return normalized

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: str) -> str:
        # Reject payloads that exceed a safe size to prevent memory abuse
        max_len = config.command_max_chars
        if len(v) > max_len:
            raise ValueError(f"Payload too large: {len(v)} chars (max {max_len})")
        return v.strip()


@app.get("/health")
async def health_check():
    """Liveness/readiness check endpoint used by Docker HEALTHCHECK and CI.

    Returns:
        JSON with status, version, uptime in seconds, and current agent state.
    """
    agent_state = await runtime.get_agent_state()
    return {
        "status": "ok",
        "version": VERSION,
        "uptime_seconds": round(time.time() - _APP_START_TIME, 1),
        "agent_state": agent_state,
    }


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the local operator console, separate from the public project site."""

    index_path = WEB_STATIC_DIR / "index.html"
    if not index_path.is_file():
        return HTMLResponse(content="<h1>Operator console not found</h1>", status_code=404)
    return FileResponse(index_path, headers={"Cache-Control": "no-store"})


@app.post("/api/session")
async def create_web_session(request: Request) -> JSONResponse:
    """Exchange the operator bearer token for an opaque, HttpOnly browser session."""

    session_id = web_security.login(request)
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=config.web_session_ttl,
        httponly=True,
        secure=config.web_session_cookie_secure,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/session")
async def inspect_web_session(request: Request) -> JSONResponse:
    """Confirm whether the current opaque browser session is still valid."""

    web_security.require_request(request, "session-status")
    return JSONResponse({"authenticated": True}, headers={"Cache-Control": "no-store"})


@app.delete("/api/session", status_code=204)
async def delete_web_session(request: Request) -> Response:
    """Revoke the current browser session."""

    web_security.require_request(request, "logout", require_origin_for_session=True)
    session_id = request.cookies.get(SESSION_COOKIE)
    web_security.revoke_session(session_id)
    await manager.disconnect_session(session_id)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time bidirectional communication with web clients.

    This endpoint:
    1. Accepts new WebSocket connections
    2. Listens for incoming commands from the client
    3. Places commands onto the command_queue for agent processing
    4. Handles client disconnections gracefully
    5. Supports cancel/delete_task commands

    Args:
        websocket: The WebSocket connection
    """
    session_id = await web_security.require_websocket(websocket)
    if not session_id:
        return

    if not await manager.connect(websocket, session_id):
        return
    logger = logging.getLogger(__name__)

    current_state = await runtime.get_agent_state()
    await manager.send_json(
        websocket,
        {
            "type": "status",
            "payload": {
                "agent_state": current_state,
                "message": f"Connected. Agent is {current_state}.",
            },
        },
    )

    try:
        while True:
            data = await websocket.receive_text()
            logger.info("Received WebSocket payload (%d characters)", len(data))
            if not web_security.session_is_valid(session_id):
                await websocket.close(code=4401, reason="Session expired")
                break
            if not web_security.allow_websocket_message(websocket):
                await manager.send_json(
                    websocket, {"type": "log", "payload": "Rate limit exceeded. Try again later."}
                )
                await websocket.close(code=4429, reason="Rate limit exceeded")
                break

            try:
                payload = json.loads(data)
                if not isinstance(payload, dict):
                    payload = {"type": "command", "payload": str(payload)}
            except json.JSONDecodeError:
                payload = {"type": "command", "payload": data}

            try:
                msg = WebSocketMessage.model_validate(payload)
            except Exception as validation_err:
                await manager.send_json(
                    websocket, {"type": "log", "payload": f"⚠️ Invalid message: {validation_err}"}
                )
                continue

            message_type = msg.type
            command_text = msg.payload

            if message_type == "command":
                if not command_text:
                    await manager.send_json(
                        websocket, {"type": "log", "payload": "⚠️ Empty command ignored."}
                    )
                elif not await runtime.reserve_command_slot():
                    await manager.send_json(
                        websocket,
                        {
                            "type": "log",
                            "payload": "⚠️ Agent is currently processing a task. Please wait or cancel.",
                        },
                    )
                else:
                    queued = await enqueue_command(command_text)
                    if queued:
                        await manager.broadcast_json(
                            {
                                "type": "status",
                                "payload": {
                                    "agent_state": "running",
                                    "message": "Processing the queued operator task.",
                                },
                            }
                        )
                        await manager.send_json(
                            websocket, {"type": "log", "payload": "Command queued."}
                        )
                    else:
                        await runtime.set_agent_state("idle")

            elif message_type in ("cancel", "delete_task"):
                cleared = await request_task_cancellation("🛑 User requested cancellation")
                await runtime.set_agent_state("cancelling")
                await manager.broadcast_json(
                    {
                        "type": "status",
                        "payload": {
                            "agent_state": "cancelling",
                            "message": "Cancelling task...",
                        },
                    }
                )
                await manager.send_json(
                    websocket,
                    {
                        "type": "log",
                        "payload": f"🛑 Cancellation requested. Cleared {cleared} queued command(s).",
                    },
                )

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        manager.disconnect(websocket)


@app.post("/api/transcribe")
async def transcribe_audio_endpoint(request: Request, file: UploadFile = File(...)):
    """Receive an audio clip (WAV) and return its local transcription."""

    web_security.require_request(request, "transcribe", require_origin_for_session=True)

    if not config.enable_local_transcription:
        raise HTTPException(
            status_code=503,
            detail=(
                "Local transcription is disabled. Set DJENIS_LOCAL_TRANSCRIPTION=true to enable it."
            ),
        )

    allowed_content_types = {"audio/wav", "audio/x-wav", "audio/wave", "application/octet-stream"}
    if file.content_type and file.content_type.casefold() not in allowed_content_types:
        raise HTTPException(status_code=415, detail="Only WAV audio is accepted.")

    audio_bytes = await file.read(config.web_upload_max_bytes + 1)
    if len(audio_bytes) > config.web_upload_max_bytes:
        raise HTTPException(status_code=413, detail="Audio payload exceeds the configured limit.")
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="The audio payload is empty.")

    if not runtime.reserve_transcription_slot(config.web_transcription_max_concurrency):
        raise HTTPException(
            status_code=429,
            detail="The transcription worker is busy. Try again after the current clip finishes.",
        )

    task = asyncio.create_task(asyncio.to_thread(transcribe_wav_bytes, audio_bytes))
    release_in_finally = True
    try:
        text = await asyncio.wait_for(
            asyncio.shield(task), timeout=config.web_transcription_timeout
        )
    except TimeoutError as exc:
        # Python worker threads cannot be killed safely. Keep the slot reserved until
        # the worker really exits so repeated timeouts cannot bypass the concurrency cap.
        release_in_finally = False
        task.add_done_callback(lambda _task: runtime.release_transcription_slot())
        raise HTTPException(status_code=504, detail="Audio transcription timed out.") from exc
    except asyncio.CancelledError:
        release_in_finally = False
        task.add_done_callback(lambda _task: runtime.release_transcription_slot())
        raise
    except TranscriptionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected failures
        logging.getLogger(__name__).error("Unexpected audio transcription error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal audio transcription error.") from exc
    finally:
        if release_in_finally:
            runtime.release_transcription_slot()

    return {"transcript": text}


async def screen_generator():
    """
    Asynchronous generator that continuously captures and yields screen frames.

    The capture and JPEG encoding work are both offloaded to worker threads via
    ``asyncio.to_thread`` to avoid blocking the event loop, keeping the FastAPI
    server responsive even under sustained streaming load.

    Yields:
        bytes: Formatted JPEG frame data in multipart format with appropriate headers

    Technical Details:
        - Frame Rate: ~10 FPS (controlled by 0.1s sleep)
        - Format: JPEG (good compression for real-time streaming)
        - Delivery: Multipart format with 'frame' boundary
        - Memory: Uses in-memory buffer to avoid disk I/O

    Performance Considerations:
        - Non-blocking: Uses async/await with thread offloading
        - Efficient: JPEG compression reduces bandwidth
        - Throttled: 10 FPS prevents CPU overload
        - Low latency: Direct screen capture without complex processing
    """
    logger = logging.getLogger(__name__)
    logger.info("Screen streaming generator started")

    try:
        target_sleep = max(0.001, 1.0 / max(1, config.stream_max_fps))

        while True:
            buffer = io.BytesIO()
            try:
                # Capture the current screen using pyautogui without blocking the loop
                if HAS_PYAUTOGUI:
                    screenshot = await asyncio.to_thread(pyautogui.screenshot)
                else:
                    # Fallback for Docker/Linux: return a blank screen with a message
                    screenshot = Image.new("RGB", (1280, 720), color=(30, 30, 30))
                    # You could draw some text here if you want, but a blank screen is enough to not crash

                if 0.0 < config.stream_resize_factor < 0.999:
                    width, height = screenshot.size
                    new_size = (
                        max(1, int(width * config.stream_resize_factor)),
                        max(1, int(height * config.stream_resize_factor)),
                    )
                    screenshot = await asyncio.to_thread(
                        screenshot.resize,
                        new_size,
                        IMAGE_RESAMPLING_LANCZOS,
                    )

                # Encode the screenshot to JPEG inside the worker thread
                await asyncio.to_thread(
                    screenshot.save,
                    buffer,
                    format="JPEG",
                    quality=config.stream_frame_quality,
                    optimize=True,
                )

                # Retrieve the JPEG byte sequence
                frame_bytes = buffer.getvalue()
            except Exception as capture_error:  # pragma: no cover - hardware dependent
                logger.error("Error capturing screen frame: %s", capture_error, exc_info=True)
                await asyncio.sleep(0.5)
                continue
            finally:
                buffer.close()

            # Yield the frame in multipart/x-mixed-replace format
            # This format allows the browser to continuously replace frames
            # Format: boundary + content type header + frame data + boundary
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")

            # Control frame rate: ~10 FPS (100ms delay)
            # This prevents overwhelming the CPU while providing smooth video
            await asyncio.sleep(target_sleep)

    except asyncio.CancelledError:
        logger.info("Screen streaming generator cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in screen generator: {e}", exc_info=True)
        raise


@app.get("/stream")
async def video_stream(request: Request):
    """
    FastAPI endpoint that streams live desktop video to the client.

    This endpoint provides a continuous video feed of the agent's desktop screen
    using the multipart/x-mixed-replace streaming technique. The stream can be
    displayed directly in an HTML <img> tag or video player.

    Returns:
        StreamingResponse: A streaming response containing the video feed

    Usage:
        In HTML: <img src="http://localhost:8000/stream" />
        In JavaScript: video.src = "http://localhost:8000/stream";

    Technical Details:
        - Protocol: HTTP with multipart/x-mixed-replace
        - Format: Continuous JPEG frames
        - Frame Rate: ~10 FPS
        - Latency: Very low (suitable for real-time monitoring)

    Benefits:
        - Simple to implement and consume
        - Works directly in <img> tags (no JavaScript required)
        - Low overhead compared to WebRTC or RTSP
        - Ideal for local network monitoring
        - No client-side decoding needed

    Example:
        ```html
        <img src="http://127.0.0.1:8000/stream"
             alt="Agent Screen"
             style="width: 100%; height: auto;" />
        ```
    """
    logger = logging.getLogger(__name__)
    web_security.require_request(request, "stream")
    if not config.supports_native_desktop():
        raise HTTPException(
            status_code=503,
            detail="Desktop capture is unavailable in this runtime.",
        )
    if not runtime.reserve_stream_slot(config.web_stream_max_clients):
        raise HTTPException(status_code=429, detail="Desktop stream capacity has been reached.")
    logger.info("Screen streaming endpoint accessed")

    async def guarded_screen_generator():
        try:
            async for frame in screen_generator():
                yield frame
        finally:
            runtime.release_stream_slot()

    return StreamingResponse(
        guarded_screen_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


def setup_logging():
    """Configure logging for the application."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        handlers=[handler],
        force=True,
    )


def run_cli_mode(args):
    """
    Run the agent in traditional CLI mode.

    Args:
        args: Parsed command-line arguments
    """
    logger = logging.getLogger(__name__)

    try:
        # API Key Configuration and Validation
        gemini_api_key = os.getenv("GEMINI_API_KEY")

        if not gemini_api_key or gemini_api_key == "YOUR_API_KEY_HERE":
            raise ValueError("GEMINI_API_KEY is not configured. Add your Gemini API key to .env.")

        logger.info("Gemini API key detected successfully")

        # Validate additional configuration
        config.validate()
        logger.info("Configuration validated successfully")
        logger.info(f"Using model: {config.gemini_model_name}")
        logger.info(f"Max loop turns: {config.max_loop_turns}")

        # Single command mode or interactive loop
        if args.command and not args.interactive:
            user_command = args.command
            logger.info("Command provided via CLI (%d characters)", len(user_command))

            # Run the main agent loop
            logger.info("Starting agent loop with a %d-character command", len(user_command))
            result = run_agent_loop(user_command)

            logger.info("Agent loop completed: %s", safe_preview(result))
            print(f"\n{'=' * 80}")
            print(f"  Final result: {result}")
            print(f"{'=' * 80}\n")

        else:
            # Interactive mode: Continuous command loop
            print("DjenisAiAgent Initialized. Ready for your commands.")
            print("Enter 'exit' or 'quit' to terminate the program.\n")

            # Continuous user interaction loop
            while True:
                try:
                    # Prompt user for command
                    user_command = input("Please enter your command (or 'exit' to quit): ").strip()

                    # Check for exit commands (case-insensitive)
                    if user_command.lower() in ["exit", "quit"]:
                        print("\n👋 Goodbye. DjenisAiAgent is shutting down.\n")
                        logger.info("User requested exit")
                        break

                    # Skip empty commands
                    if not user_command:
                        print("⚠️  Empty command. Enter a valid instruction.\n")
                        continue

                    # Execute the command
                    logger.info(
                        "Starting agent loop with a %d-character command", len(user_command)
                    )
                    result = run_agent_loop(user_command)

                    logger.info("Agent loop completed: %s", safe_preview(result))
                    print(f"\n{'=' * 80}")
                    print(f"  Result: {result}")
                    print(f"{'=' * 80}\n")

                except KeyboardInterrupt:
                    print("\n\n⚠️  Interrupted. Enter 'exit' to shut down cleanly.\n")
                    continue

                except Exception as e:
                    logger.error(f"Error during command execution: {e}", exc_info=True)
                    print(f"\n❌ Execution error: {e}\n")
                    print("Try another instruction or enter 'exit' to quit.\n")
                    continue

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print(f"\n❌ Configuration error: {e}\n")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Agent interrupted by user")
        print("\n\n⚠️  Agent interrupted by the operator.\n")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\n❌ Unexpected error: {e}\n")
        sys.exit(1)


async def process_commands_from_queue():
    """
    DEPRECATED: This function has been replaced by the agent_loop() function.

    The new architecture uses agent_loop() from src.orchestration.agent_loop
    which is started as a concurrent task in main().

    This stub remains for backwards compatibility but should not be called.
    """
    logger = logging.getLogger(__name__)
    logger.warning("process_commands_from_queue() is deprecated. Use agent_loop() instead.")
    pass


async def run_web_mode_async(host: str, port: int):
    """
    Run the agent in web server mode with FastAPI and WebSocket support (async version).

    This is the core of Step 10: Final Integration and Concurrent Execution.

    Architecture:
        This function creates and runs three concurrent tasks using asyncio.gather():
        1. FastAPI/Uvicorn server: Handles HTTP and WebSocket connections
        2. agent_loop: Consumes commands from command_queue and executes them
        3. status_broadcaster: Relays status updates to all WebSocket clients

    Flow:
        WebSocket client sends command
          ↓
        WebSocket endpoint puts command in command_queue
          ↓
        agent_loop pulls command from queue
          ↓
        agent_loop executes ReAct cycle
          ↓
        agent_loop puts status updates in status_queue
          ↓
        status_broadcaster pulls from status_queue
          ↓
        status_broadcaster broadcasts to all WebSocket clients

    Args:
        host: Host address for the web server (e.g., "0.0.0.0" for all interfaces)
        port: Port number for the web server (e.g., 8000)

    This function runs indefinitely until interrupted (Ctrl+C) or an error occurs.
    """
    logger = logging.getLogger(__name__)

    # Configure Gemini API for web mode
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key or gemini_api_key == "YOUR_API_KEY_HERE":
        raise ValueError("GEMINI_API_KEY is not configured. Add your Gemini API key to .env.")

    config.validate_web()
    logger.info("Gemini API key detected for web mode")
    logger.info(f"Using model: {config.gemini_model_name}")
    logger.info(f"Max loop turns: {config.max_loop_turns}")

    # Configure Uvicorn server programmatically
    # Using Config + Server pattern instead of uvicorn.run() for better control
    config_obj = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )
    server = uvicorn.Server(config_obj)

    logger.info(f"Starting unified concurrent system on http://{host}:{port}")
    logger.info("Components: FastAPI server + agent_loop + status_broadcaster")

    server_task = asyncio.create_task(server.serve(), name="uvicorn-server")
    agent_task = asyncio.create_task(
        agent_loop(runtime.command_queue, runtime.status_queue, runtime.task_cancel_event),
        name="agent-loop",
    )
    broadcaster_task = asyncio.create_task(status_broadcaster(), name="status-broadcaster")
    background_tasks = {agent_task, broadcaster_task}

    try:
        done, _pending = await asyncio.wait(
            {server_task, *background_tasks}, return_when=asyncio.FIRST_COMPLETED
        )
        if server_task not in done:
            failed_task = next(iter(done))
            failure = failed_task.exception()
            server.should_exit = True
            if failure is not None:
                raise failure
            raise RuntimeError(f"Critical worker '{failed_task.get_name()}' exited unexpectedly")

        server_failure = server_task.exception()
        if server_failure is not None:
            raise server_failure
    except KeyboardInterrupt:
        logger.info("Web mode interrupted by user (Ctrl+C)")
        raise
    except Exception as e:
        logger.error("Error in concurrent execution: %s", safe_preview(e), exc_info=True)
        raise
    finally:
        runtime.task_cancel_event.set()
        server.should_exit = True
        for task in {server_task, *background_tasks}:
            if not task.done():
                task.cancel()
        await asyncio.gather(server_task, *background_tasks, return_exceptions=True)
        try:
            from src.action.browser_tools import browser_close_connection

            await asyncio.to_thread(browser_close_connection)
        except Exception as exc:  # pragma: no cover - optional Selenium shutdown
            logger.warning("Browser cleanup failed: %s", safe_preview(exc))


def run_web_mode(args):
    """
    Run the agent in web server mode with FastAPI and WebSocket support.

    This is a synchronous wrapper that launches the asynchronous web mode.

    Args:
        args: Parsed command-line arguments
    """
    logger = logging.getLogger(__name__)

    logger.info("Starting DjenisAiAgent in web mode")
    print("\n" + "=" * 80)
    print("  🤖 DjenisAiAgent - Web Server Mode (Step 10: Unified Concurrent System)")
    print("=" * 80)
    print(f"\n  Server will start on http://{args.host}:{args.port}")
    print(f"  WebSocket endpoint: ws://{args.host}:{args.port}/ws")
    print(f"  Stream endpoint: http://{args.host}:{args.port}/stream")
    print("\n  Concurrent Components:")
    print("    1. FastAPI/Uvicorn server (HTTP + WebSocket)")
    print("    2. Agent loop (command processing)")
    print("    3. Status broadcaster (real-time updates)")
    print("\n  Press CTRL+C to stop the server\n")
    print("=" * 80 + "\n")

    # Run the async web mode using asyncio.run()
    try:
        asyncio.run(run_web_mode_async(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Web mode stopped by user")
        print("\n\n⚠️  Web server stopped by user.\n")
    except Exception as e:
        logger.error(f"Web mode error: {e}", exc_info=True)
        print(f"\n❌ Web mode error: {e}\n")
        sys.exit(1)


def main():
    """
    Main application entry point.

    This function handles:
    1. Environment variable loading from .env
    2. Command-line argument parsing
    3. Routing to either CLI mode or web server mode
    """
    # Step 1: Load environment variables from .env file
    load_dotenv()

    setup_logging()
    logger = logging.getLogger(__name__)

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="DjenisAiAgent - AI-powered Windows automation agent"
    )
    parser.add_argument(
        "command",
        type=str,
        nargs="?",
        default=None,
        help="Natural language command to execute (CLI mode only)",
    )
    parser.add_argument(
        "--no-ui", action="store_true", help="Run in headless mode (no interactive UI)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Force interactive mode with continuous command loop (CLI mode)",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Run in web server mode with FastAPI and WebSocket support",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=config.web_host,
        help="Host address for web server mode (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port for web server mode (default: 8000)"
    )

    args = parser.parse_args()

    logger.info("DjenisAiAgent starting...")
    print("\n" + "=" * 80)
    print("  🤖 DjenisAiAgent - AI-Powered Windows Automation")
    print("=" * 80 + "\n")

    try:
        # Route to appropriate mode based on arguments
        if args.web:
            run_web_mode(args)
        else:
            run_cli_mode(args)

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        print("\n\nApplication interrupted by the user.\n")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}", exc_info=True)
        print(f"\n❌ Unexpected error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
