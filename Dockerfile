# =============================================================================
# STAGE 1: Builder — compiles/installs all Python deps into a flat target dir
# =============================================================================
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# --target installs everything flat into one directory, independent of
# Python's version-specific site-packages path — this is what lets us copy
# it straight into distroless without caring which exact 3.11.x it ships.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --target=/app/deps -r requirements.txt

# =============================================================================
# STAGE 2: Runtime — distroless, no shell, no package manager, non-root
# =============================================================================
FROM gcr.io/distroless/python3-debian12:nonroot

WORKDIR /app

# Installed dependencies from the builder stage
COPY --from=builder /app/deps /app/deps

# Application source
COPY --chown=nonroot:nonroot app ./app
COPY --chown=nonroot:nonroot alembic ./alembic
COPY --chown=nonroot:nonroot alembic.ini ./alembic.ini

ENV PYTHONPATH=/app/deps
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# No shell in distroless, so no `sh -c` form — exec form only.
ENTRYPOINT ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
