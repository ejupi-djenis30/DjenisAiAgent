# =============================================================================
# Stage 1: builder — install dependencies into a virtual environment
# =============================================================================
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS builder

WORKDIR /build

COPY requirements-docker.lock ./

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements-docker.lock

# =============================================================================
# Stage 2: runtime — slim production image
# =============================================================================
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS runtime

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create non-root user
RUN groupadd --gid 1001 djenis && \
    useradd --uid 1001 --gid djenis --shell /bin/bash --create-home djenis

WORKDIR /app

# Copy application source
COPY --chown=djenis:djenis src/ ./src/
COPY --chown=djenis:djenis web/ ./web/
COPY --chown=djenis:djenis main.py ./

# Create directories for logs and models
RUN mkdir -p /app/logs /app/models && chown -R djenis:djenis /app

# Runtime environment — safe defaults for Docker (web mode only)
ENV DJENIS_LOG_LEVEL=INFO \
    DJENIS_STREAM_MAX_FPS=15 \
    DJENIS_MAX_LOOP_TURNS=50 \
    DJENIS_API_TIMEOUT=120 \
    DJENIS_RUNTIME_MODE=docker \
    DJENIS_PERMISSION_TIER=interact

EXPOSE 8000

USER djenis

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5).read()"

CMD ["python", "main.py", "--web", "--host", "0.0.0.0", "--port", "8000"]
