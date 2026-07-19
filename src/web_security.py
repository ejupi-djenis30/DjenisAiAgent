"""Authentication, origin checks, sessions, and lightweight request limiting."""

from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from threading import Lock
from urllib.parse import urlparse

from fastapi import HTTPException, Request, WebSocket, status

from src.config import config

SESSION_COOKIE = "djenis_session"


class SlidingWindowRateLimiter:
    """Small in-memory limiter suitable for the single-process local control plane."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, *, now: float | None = None) -> bool:
        timestamp = time.monotonic() if now is None else now
        cutoff = timestamp - 60.0
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(timestamp)
            return True

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class WebSecurity:
    """Own opaque browser sessions without exposing the operator token to JavaScript."""

    def __init__(self) -> None:
        self._sessions: dict[str, float] = {}
        self._lock = Lock()
        self.rate_limiter = SlidingWindowRateLimiter()

    @staticmethod
    def _client_key(client_host: str | None, action: str) -> str:
        return f"{client_host or 'unknown'}:{action}"

    @staticmethod
    def _extract_bearer(value: str | None) -> str:
        if not value:
            return ""
        scheme, _, token = value.partition(" ")
        return token.strip() if scheme.casefold() == "bearer" else ""

    @staticmethod
    def origin_allowed(origin: str | None, host: str | None) -> bool:
        if not origin:
            return True
        if origin in config.web_allowed_origins:
            return True

        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not host:
            return False
        return parsed.netloc.casefold() == host.casefold()

    def verify_operator_token(self, presented_token: str) -> bool:
        configured = config.web_auth_token
        return bool(
            configured and presented_token and secrets.compare_digest(configured, presented_token)
        )

    def create_session(self) -> str:
        session_id = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[session_id] = time.monotonic() + config.web_session_ttl
        return session_id

    def revoke_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(session_id, None)

    def session_is_valid(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        now = time.monotonic()
        with self._lock:
            expires_at = self._sessions.get(session_id)
            if expires_at is None:
                return False
            if expires_at <= now:
                self._sessions.pop(session_id, None)
                return False
            return True

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
        self.rate_limiter.clear()

    def require_origin(self, origin: str | None, host: str | None) -> None:
        if not self.origin_allowed(origin, host):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin denied")

    def require_rate_limit(
        self,
        client_host: str | None,
        action: str,
        *,
        login: bool = False,
    ) -> None:
        limit = (
            config.web_login_rate_limit_per_minute if login else config.web_rate_limit_per_minute
        )
        if not self.rate_limiter.allow(self._client_key(client_host, action), limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )

    def require_request(self, request: Request, action: str) -> None:
        self.require_origin(request.headers.get("origin"), request.headers.get("host"))
        self.require_rate_limit(request.client.host if request.client else None, action)
        bearer = self._extract_bearer(request.headers.get("authorization"))
        if self.verify_operator_token(bearer):
            return
        if self.session_is_valid(request.cookies.get(SESSION_COOKIE)):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    def login(self, request: Request) -> str:
        """Validate an operator bearer token and return a new opaque session id."""

        self.require_origin(request.headers.get("origin"), request.headers.get("host"))
        self.require_rate_limit(
            request.client.host if request.client else None,
            "login",
            login=True,
        )
        bearer = self._extract_bearer(request.headers.get("authorization"))
        if not self.verify_operator_token(bearer):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid operator token",
            )
        return self.create_session()

    def allow_websocket_message(self, websocket: WebSocket) -> bool:
        client_host = websocket.client.host if websocket.client else None
        return self.rate_limiter.allow(
            self._client_key(client_host, "websocket-message"),
            config.web_rate_limit_per_minute,
        )

    async def require_websocket(self, websocket: WebSocket) -> bool:
        origin = websocket.headers.get("origin")
        if not origin or not self.origin_allowed(origin, websocket.headers.get("host")):
            await websocket.close(code=4403, reason="Origin denied")
            return False

        client_host = websocket.client.host if websocket.client else None
        if not self.rate_limiter.allow(
            self._client_key(client_host, "websocket-connect"),
            config.web_rate_limit_per_minute,
        ):
            await websocket.close(code=4429, reason="Rate limit exceeded")
            return False

        if not self.session_is_valid(websocket.cookies.get(SESSION_COOKIE)):
            await websocket.close(code=4401, reason="Authentication required")
            return False
        return True


web_security = WebSecurity()
