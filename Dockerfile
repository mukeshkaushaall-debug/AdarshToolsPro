FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    U2NET_HOME=/app/backend/models/rembg \
    REMBG_MODEL=u2net \
    OMP_NUM_THREADS=1 \
    PORT=5000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/backend/requirements.txt

RUN mkdir -p /app/backend/models/rembg \
    && python -c "from rembg import new_session; [new_session(model) for model in ('u2net', 'u2net_human_seg', 'isnet-general-use')]"

COPY . /app

RUN mkdir -p /app/backend/uploads /app/backend/downloads

WORKDIR /app/backend

EXPOSE 5000

CMD gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 300
