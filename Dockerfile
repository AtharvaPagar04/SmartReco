# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements.txt ./

RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip \
    && /opt/venv/bin/python -m pip install -r requirements.txt


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY config ./config
COPY requirements.txt ./
COPY README.md ./

RUN addgroup --system smartreco \
    && adduser --system --ingroup smartreco smartreco \
    && chmod +x scripts/start_production.sh \
    && chown -R smartreco:smartreco /app

USER smartreco

EXPOSE 8000

CMD ["sh", "scripts/start_production.sh"]
