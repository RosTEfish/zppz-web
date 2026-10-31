FROM rust:1-bookworm AS chart-validate
WORKDIR /src
COPY tools/zppz-chart-validate /src
RUN cargo build --release

FROM python:3.12-slim

ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ZPPZ_CHART_VALIDATE_BIN=/usr/local/bin/zppz-chart-validate

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends unar \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r /app/requirements.txt

COPY --from=chart-validate /src/target/release/zppz-chart-validate /usr/local/bin/zppz-chart-validate
COPY backend /app/backend
COPY bg /app/bg
COPY banlist /app/banlist
COPY ruleDetail /app/ruleDetail

# API and workers run as uid/gid 1000. /app and /data are owned by that user so
# a new volume mounted at /data is writable. A volume created earlier by a root
# container stays root-owned until it is chowned once (see the Docker Compose
# section of the README).
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --home-dir /home/app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chmod 755 /usr/local/bin/zppz-chart-validate \
    && chown -R app:app /app /data /home/app

ENV HOME=/home/app
WORKDIR /app/backend
USER app
CMD ["sh", "-c", "python -m app.prepare && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1} --no-proxy-headers"]
