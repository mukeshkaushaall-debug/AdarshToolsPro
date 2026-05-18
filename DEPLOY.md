# ThugTools Railway Deploy Guide

## Recommended: Railway with Docker

1. Push this `AdarshToolsPro` folder to GitHub.
2. Open Railway and create a **New Project**.
3. Choose **Deploy from GitHub repo**.
4. Select your repo.
5. If Railway asks for root directory, set it to `AdarshToolsPro`.
6. Railway will detect the root `Dockerfile` and build with Docker.
7. After deploy, go to **Settings > Networking** and click **Generate Domain**.
8. Open the Railway domain and test the tools.

Railway will use the root `Dockerfile`, install FFmpeg and Python dependencies, then run:

```sh
gunicorn app:app --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-1} --threads ${GUNICORN_THREADS:-6}
```

The Docker image uses Python 3.11 for better compatibility with `rembg` and `onnxruntime`.

## Railway Settings

- Builder: Dockerfile
- Config file: `railway.toml`
- Healthcheck path: `/`
- Start command: leave empty unless Railway asks; the Dockerfile already has `CMD`.

## YouTube Reliability Variables

YouTube runs in forced cookieless mode. The backend no longer uses YouTube cookies, manual browser sessions, or public Invidious/Piped scraping. Metadata uses oEmbed/thumbnail cache; downloads use only configured Cobalt-compatible relays.

- `YOUTUBE_FORCE_COOKIELESS=1`
- `COBALT_API_URL=https://your-cobalt-relay.example/`
- `COBALT_API_URLS=https://backup-1.example/,https://backup-2.example/`

For strongest uptime, run 2-3 Cobalt relays in different regions/providers and list every relay in `COBALT_API_URLS`. The app retries configured relays, cools down failed relays, rate-limits abusive clients, and keeps metadata cached so preview traffic stays cheap.

Optional stability/security variables:

- `API_KEYS=key-one,key-two` to require `X-API-Key` for `/api/*` calls.
- `API_RATE_LIMIT_PER_MINUTE=90`
- `INFO_RATE_LIMIT_PER_MINUTE=45`
- `DOWNLOAD_RATE_LIMIT_PER_MINUTE=12`
- `MEDIA_MAX_CONCURRENT_DOWNLOADS=3`
- `MEDIA_MAX_CONCURRENT_INFO=8`
- `MEDIA_QUEUE_WAIT_SECONDS=8`
- `COBALT_TIMEOUT_SECONDS=75`
- `COBALT_MAX_RELAYS_PER_REQUEST=4`

After setting variables, redeploy and open `/api/youtube/status`. Confirm `public_instance_scraping=false`, `cookies_supported=false`, and `cobalt_configured=true`.

## Instagram Reliability Variables

Instagram is also configured for public, cookieless media only. For best reliability, paste the link, wait for the preview to load, then click download so the backend can reuse the preview result when possible. Open `/api/instagram/status` and confirm `cookies_supported=false`.

## Notes

- Use enough memory if possible. `rembg`/`onnxruntime`, PDF rendering, uploads, and video conversion can be memory-heavy.
- Uploaded/generated files are temporary and stored in `backend/uploads` and `backend/downloads`.
- FFmpeg is installed in Docker for video/audio conversion.
- The frontend calls backend APIs on the same domain in production.
