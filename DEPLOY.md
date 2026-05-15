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
gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 300
```

The Docker image uses Python 3.11 for better compatibility with `rembg` and `onnxruntime`.

## Railway Settings

- Builder: Dockerfile
- Config file: `railway.toml`
- Healthcheck path: `/`
- Start command: leave empty unless Railway asks; the Dockerfile already has `CMD`.

## YouTube Reliability Variables

YouTube may block a server IP or expire a single cookie export quickly. For the YouTube downloader, add multiple fresh cookie profiles in Railway **Variables** so the backend can retry automatically:

- `YOUTUBE_COOKIES_TEXT_1`
- `YOUTUBE_COOKIES_TEXT_2`
- `YOUTUBE_COOKIES_TEXT_3`

Optional advanced variables:

- `YOUTUBE_VISITOR_DATA`
- `YOUTUBE_PO_TOKEN`
- `YOUTUBE_PO_TOKEN_2`
- `YOUTUBE_ALLOW_NO_COOKIES_FALLBACK=1`

After adding or refreshing variables, redeploy and open `/api/youtube/status`. Confirm `cookie_profile_count` is at least `2` and `yt_dlp_version` is current.

## Notes

- Use enough memory if possible. `rembg`/`onnxruntime`, PDF rendering, uploads, and video conversion can be memory-heavy.
- Uploaded/generated files are temporary and stored in `backend/uploads` and `backend/downloads`.
- FFmpeg is installed in Docker for video/audio conversion.
- The frontend calls backend APIs on the same domain in production.
