# ============================================================
# Stage 1: Builder
# ============================================================

FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Build dependencies required for Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition first for better layer caching
COPY requirements.txt .

# Install dependencies into a separate directory
RUN python -m pip install \
    --prefix=/install \
    --no-cache-dir \
    -r requirements.txt


# ============================================================
# Stage 2: Production Runtime
# ============================================================

FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Runtime PostgreSQL library only
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /install /usr/local

# Copy application
COPY app.py .

# Copy Flask templates
COPY templates ./templates

# Create non-root application user
RUN groupadd --system appgroup \
    && useradd --system \
        --gid appgroup \
        --create-home \
        --home-dir /home/appuser \
        appuser \
    && chown -R appuser:appgroup /app

# Run application as non-root
USER appuser

EXPOSE 8080

# Production WSGI server
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]