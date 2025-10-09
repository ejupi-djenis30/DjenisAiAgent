"""
Main entry point for DjenisAiAgent.

This module serves as the application entry point, supporting both:
1. CLI mode: Traditional command-line interface (existing functionality)
2. Web mode: FastAPI server with WebSocket support for real-time web interface

The architecture uses asyncio.Queue to decouple the web server from the agent's logic,
ensuring that long-running agent tasks do not block the server.
"""

import os
import sys
import json
import logging
import argparse
import asyncio
import io
from pathlib import Path
from threading import Event
from typing import List, TYPE_CHECKING
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import google.generativeai as genai
import pyautogui

from src.config import config
from src.orchestration.agent_loop import run_agent_loop, agent_loop

# FastAPI imports (only used in web mode)
if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI as FastAPIType, WebSocket as WebSocketType, WebSocketDisconnect as WebSocketDisconnectType
    from fastapi.responses import HTMLResponse as HTMLResponseType, StreamingResponse as StreamingResponseType
    import uvicorn as UvicornType

try:
    from fastapi import FastAPI as FastAPIRuntime, WebSocket as WebSocketRuntime, WebSocketDisconnect as WebSocketDisconnectRuntime
    from fastapi.responses import HTMLResponse as HTMLResponseRuntime, StreamingResponse as StreamingResponseRuntime
    import uvicorn as uvicorn_runtime
    FASTAPI_AVAILABLE = True
except ImportError as import_error:  # pragma: no cover - optional dependency
    FASTAPI_AVAILABLE = False
    raise ImportError(
        "FastAPI, uvicorn, and python-websockets must be installed to run the web server."
    ) from import_error

FastAPI = FastAPIRuntime
WebSocket = WebSocketRuntime
WebSocketDisconnect = WebSocketDisconnectRuntime
HTMLResponse = HTMLResponseRuntime
StreamingResponse = StreamingResponseRuntime
uvicorn = uvicorn_runtime

# Global asyncio queues for web mode communication
command_queue: asyncio.Queue = asyncio.Queue()
status_queue: asyncio.Queue = asyncio.Queue()
task_cancel_event: Event = Event()
command_queue_lock = asyncio.Lock()


async def enqueue_command(command: str) -> bool:
    """Enqueue a trimmed user command for agent processing."""
    cleaned = command.strip()
    if not cleaned:
        return False

    async with command_queue_lock:
        await command_queue.put(cleaned)
    logging.getLogger(__name__).info("Queued command: %s", cleaned)
    return True


async def request_task_cancellation(reason: str | None = None) -> int:
    """Cancel the current task and clear queued commands.

    Args:
        reason: Optional message to broadcast alongside the cancellation.

    Returns:
        int: Number of queued commands that were discarded.
    """
    logger = logging.getLogger(__name__)
    task_cancel_event.set()
    if reason:
        await status_queue.put(reason)

    drained = 0
    async with command_queue_lock:
        while True:
            try:
                command_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                drained += 1
                command_queue.task_done()

    logger.info("Cancellation requested. Cleared %d queued commands.", drained)
    return drained


@asynccontextmanager
async def lifespan(app: "FastAPI"):  # type: ignore
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events for the unified concurrent system.
    """
    logger = logging.getLogger(__name__)
    
    # Startup
    logger.info("Starting unified concurrent system: agent_loop + status_broadcaster")
    
    # Note: We don't start background tasks here anymore
    # They will be started in the main() function using asyncio.gather()
    
    yield
    
    # Shutdown
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
            # Wait for a status message from the agent
            # This is a blocking call that suspends until a message is available
            status_message = await status_queue.get()
            
            logger.debug(f"Broadcasting status: {status_message[:100]}")
            
            # Broadcast to all connected WebSocket clients
            # The ConnectionManager handles iterating through clients
            # and deals with disconnected clients gracefully
            await manager.broadcast(status_message)
            
            # Mark the task as done for queue management
            status_queue.task_done()
            
    except asyncio.CancelledError:
        logger.info("Status broadcaster cancelled, shutting down gracefully")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in status broadcaster: {e}", exc_info=True)
        # Don't re-raise; keep the broadcaster running if possible


# Global FastAPI application instance with lifespan
app = FastAPI(
    title="DjenisAiAgent",
    description="AI-powered Windows automation agent",
    lifespan=lifespan if FASTAPI_AVAILABLE else None  # type: ignore
)


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
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """
        Accept a new WebSocket connection and add it to the active connections list.
        
        Args:
            websocket: The WebSocket connection to accept and manage
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logging.getLogger(__name__).info(f"New WebSocket connection. Total active: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection from the active connections list.
        
        Args:
            websocket: The WebSocket connection to remove
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logging.getLogger(__name__).info(f"WebSocket disconnected. Total active: {len(self.active_connections)}")
    
    async def broadcast(self, message: str):
        """
        Send a message to all active WebSocket clients.
        
        Args:
            message: The message string to broadcast
        """
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logging.getLogger(__name__).error(f"Error broadcasting to client: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


# Global ConnectionManager instance
manager = ConnectionManager()


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """
    Serve the main frontend HTML page.
    
    Returns:
        HTMLResponse: The content of index.html
    """
    try:
        index_path = Path(__file__).parent / "index.html"
        with open(index_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Error: index.html not found</h1>",
            status_code=404
        )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time bidirectional communication with web clients.
    
    This endpoint:
    1. Accepts new WebSocket connections
    2. Listens for incoming commands from the client
    3. Places commands onto the command_queue for agent processing
    4. Handles client disconnections gracefully
    
    Args:
        websocket: The WebSocket connection
    """
    await manager.connect(websocket)
    logger = logging.getLogger(__name__)
    
    try:
        while True:
            # Listen for incoming messages from the client
            data = await websocket.receive_text()
            logger.info("Received WebSocket payload: %s", data)

            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                payload = data

            ack_message: str

            if isinstance(payload, dict):
                message_type = str(payload.get("type", "command")).lower()

                if message_type == "command":
                    command_text = str(payload.get("payload", "")).strip()
                    if not command_text:
                        ack_message = "⚠️ Empty command ignored."
                    else:
                        queued = await enqueue_command(command_text)
                        if queued:
                            await status_queue.put(f"📝 Nuovo comando: {command_text}")
                            ack_message = f"✅ Command queued: {command_text}"
                        else:
                            ack_message = "⚠️ Empty command ignored."

                elif message_type == "delete_task":
                    cleared = await request_task_cancellation("🛑 Cancellazione task richiesta dall'utente")
                    ack_message = f"🛑 Cancellation requested. Cleared {cleared} queued command(s)."

                else:
                    ack_message = f"⚠️ Unsupported message type: {message_type}"

            else:
                command_text = str(payload).strip()
                if await enqueue_command(command_text):
                    await status_queue.put(f"📝 Nuovo comando: {command_text}")
                    ack_message = f"✅ Command queued: {command_text}"
                else:
                    ack_message = "⚠️ Empty command ignored."

            await websocket.send_text(ack_message)
            
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(websocket)


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
        while True:
            buffer = io.BytesIO()
            try:
                # Capture the current screen using pyautogui without blocking the loop
                screenshot = await asyncio.to_thread(pyautogui.screenshot)

                # Encode the screenshot to JPEG inside the worker thread
                await asyncio.to_thread(
                    screenshot.save,
                    buffer,
                    format="JPEG",
                    quality=85,
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
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
            )

            # Control frame rate: ~10 FPS (100ms delay)
            # This prevents overwhelming the CPU while providing smooth video
            await asyncio.sleep(0.1)
            
    except asyncio.CancelledError:
        logger.info("Screen streaming generator cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in screen generator: {e}", exc_info=True)
        raise


@app.get("/stream")
async def video_stream():
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
    logger.info("Screen streaming endpoint accessed")
    
    return StreamingResponse(
        screen_generator(),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
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
            raise ValueError(
                "La variabile d'ambiente GEMINI_API_KEY non è impostata. "
                "Configura il file .env con la tua chiave API di Gemini."
            )
        
        # Configure the Gemini SDK with the API key
        genai.configure(api_key=gemini_api_key)  # type: ignore[attr-defined]
        logger.info("Gemini API configured successfully")
        
        # Validate additional configuration
        config.validate()
        logger.info("Configuration validated successfully")
        logger.info(f"Using model: {config.gemini_model_name}")
        logger.info(f"Max loop turns: {config.max_loop_turns}")
        
        # Single command mode or interactive loop
        if args.command and not args.interactive:
            user_command = args.command
            logger.info(f"Command provided via CLI: {user_command}")
            
            # Run the main agent loop
            logger.info(f"Starting agent loop with command: {user_command}")
            result = run_agent_loop(user_command)
            
            logger.info(f"Agent loop completed with result: {result}")
            print(f"\n{'='*80}")
            print(f"  Risultato finale: {result}")
            print(f"{'='*80}\n")
            
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
                    if user_command.lower() in ['exit', 'quit']:
                        print("\n👋 Arrivederci! Chiusura di DjenisAiAgent.\n")
                        logger.info("User requested exit")
                        break
                    
                    # Skip empty commands
                    if not user_command:
                        print("⚠️  Comando vuoto. Inserisci un comando valido.\n")
                        continue
                    
                    # Execute the command
                    logger.info(f"Starting agent loop with command: {user_command}")
                    result = run_agent_loop(user_command)
                    
                    logger.info(f"Agent loop completed with result: {result}")
                    print(f"\n{'='*80}")
                    print(f"  Risultato: {result}")
                    print(f"{'='*80}\n")
                    
                except KeyboardInterrupt:
                    print("\n\n⚠️  Interruzione rilevata. Usa 'exit' per uscire in modo pulito.\n")
                    continue
                    
                except Exception as e:
                    logger.error(f"Error during command execution: {e}", exc_info=True)
                    print(f"\n❌ Errore durante l'esecuzione: {e}\n")
                    print("Puoi provare un altro comando o digitare 'exit' per uscire.\n")
                    continue
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print(f"\n❌ Errore di configurazione: {e}\n")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Agent interrupted by user")
        print("\n\n⚠️  Agente interrotto dall'utente.\n")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\n❌ Errore imprevisto: {e}\n")
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
        raise ValueError(
            "La variabile d'ambiente GEMINI_API_KEY non è impostata. "
            "Configura il file .env con la tua chiave API di Gemini."
        )
    
    genai.configure(api_key=gemini_api_key)  # type: ignore[attr-defined]
    config.validate()
    logger.info("Gemini API configured for web mode")
    logger.info(f"Using model: {config.gemini_model_name}")
    logger.info(f"Max loop turns: {config.max_loop_turns}")
    
    # Configure Uvicorn server programmatically
    # Using Config + Server pattern instead of uvicorn.run() for better control
    config_obj = uvicorn.Config(  # type: ignore
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
    server = uvicorn.Server(config_obj)  # type: ignore
    
    logger.info(f"Starting unified concurrent system on http://{host}:{port}")
    logger.info("Components: FastAPI server + agent_loop + status_broadcaster")
    
    try:
        # Run all three components concurrently
        # This is the key to Step 10: everything runs together without blocking
        await asyncio.gather(
            server.serve(),  # FastAPI/Uvicorn server
            agent_loop(command_queue, status_queue, task_cancel_event),  # Agent ReAct loop
            status_broadcaster(),  # Status message broadcaster
            return_exceptions=False  # Propagate exceptions
        )
    except KeyboardInterrupt:
        logger.info("Web mode interrupted by user (Ctrl+C)")
        raise
    except Exception as e:
        logger.error(f"Error in concurrent execution: {e}", exc_info=True)
        raise


def run_web_mode(args):
    """
    Run the agent in web server mode with FastAPI and WebSocket support.
    
    This is a synchronous wrapper that launches the asynchronous web mode.
    
    Args:
        args: Parsed command-line arguments
    """
    logger = logging.getLogger(__name__)
    
    if not FASTAPI_AVAILABLE:
        logger.error("FastAPI is not installed. Install with: pip install fastapi uvicorn websockets")
        print("\n❌ FastAPI non è installato. Esegui: pip install fastapi uvicorn websockets\n")
        sys.exit(1)
    
    logger.info("Starting DjenisAiAgent in web mode")
    print("\n" + "="*80)
    print("  🤖 DjenisAiAgent - Web Server Mode (Step 10: Unified Concurrent System)")
    print("="*80)
    print(f"\n  Server will start on http://{args.host}:{args.port}")
    print(f"  WebSocket endpoint: ws://{args.host}:{args.port}/ws")
    print(f"  Stream endpoint: http://{args.host}:{args.port}/stream")
    print("\n  Concurrent Components:")
    print("    1. FastAPI/Uvicorn server (HTTP + WebSocket)")
    print("    2. Agent loop (command processing)")
    print("    3. Status broadcaster (real-time updates)")
    print("\n  Press CTRL+C to stop the server\n")
    print("="*80 + "\n")
    
    # Run the async web mode using asyncio.run()
    try:
        asyncio.run(run_web_mode_async(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Web mode stopped by user")
        print("\n\n⚠️  Web server stopped by user.\n")
    except Exception as e:
        logger.error(f"Web mode error: {e}", exc_info=True)
        print(f"\n❌ Errore in modalità web: {e}\n")
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
        help="Natural language command to execute (CLI mode only)"
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Run in headless mode (no interactive UI)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Force interactive mode with continuous command loop (CLI mode)"
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Run in web server mode with FastAPI and WebSocket support"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host address for web server mode (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for web server mode (default: 8000)"
    )
    
    args = parser.parse_args()
    
    logger.info("DjenisAiAgent starting...")
    print("\n" + "="*80)
    print("  🤖 DjenisAiAgent - AI-Powered Windows Automation")
    print("="*80 + "\n")
    
    try:
        # Route to appropriate mode based on arguments
        if args.web:
            run_web_mode(args)
        else:
            run_cli_mode(args)
            
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        print("\n\n⚠️  Applicazione interrotta dall'utente.\n")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}", exc_info=True)
        print(f"\n❌ Errore imprevisto: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
