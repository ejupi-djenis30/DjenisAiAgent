# =============================================================================
# Stage 1: builder — install dependencies into a virtual environment
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt ./

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip wheel && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements-docker.txt

# =============================================================================
# Stage 2: runtime — slim production image
# =============================================================================
FROM python:3.12-slim AS runtime

# The agent talks to the separate remote Selenium service; no browser is bundled here.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "main.py", "--web", "--host", "0.0.0.0", "--port", "8000"]
