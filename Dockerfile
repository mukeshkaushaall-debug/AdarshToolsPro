FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    U2NET_HOME=/app/backend/models/rembg \
    REMBG_MODEL=u2netp \
    REMBG_MAX_SIDE=512 \
    OMP_NUM_THREADS=1 \
    PORT=5000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# PO token provider for cookieless YouTube (runs in start.sh)
RUN git clone --depth 1 --branch 1.3.1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /app/bgutil-pot \
    && cd /app/bgutil-pot/server \
    && npm ci \
    && npx tsc

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/backend/requirements.txt

RUN mkdir -p /app/backend/models/rembg \
    && python -c "from rembg import new_session; new_session('u2netp')"

COPY . /app

RUN mkdir -p /app/backend/uploads /app/backend/downloads

WORKDIR /app/backend

EXPOSE 5000

ENV BGUTIL_POT_BASE_URL=http://127.0.0.1:4416 \
    YOUTUBE_FORCE_COOKIELESS=1 \
    YOUTUBE_USE_COOKIES=0

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
