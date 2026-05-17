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

YouTube runs in forced cookieless mode by default. The backend first tries yt-dlp with PO-token support, then parallel Invidious/Piped resolver fallbacks, and finally a configured Cobalt relay. Public Cobalt APIs are not assumed; use your own relay from `cobalt-relay/`.

- `YOUTUBE_FORCE_COOKIELESS=1`
- `COBALT_API_URL=https://your-cobalt-relay.example/`
- `COBALT_API_URLS=https://backup-1.example/,https://backup-2.example/`

For strongest uptime, run 2-3 Cobalt relays in different regions/providers and list every relay in `COBALT_API_URLS`. The app rotates configured relays, cools down failed relays, and reuses fresh preview formats before asking YouTube to extract again.

Cookies are ignored unless you explicitly set `YOUTUBE_FORCE_COOKIELESS=0` and `YOUTUBE_USE_COOKIES=1`. If you choose to use cookies for content you are allowed to access, add multiple fresh cookie profiles in Railway **Variables** so the backend can retry automatically:

- `YOUTUBE_COOKIES_TEXT_1`
- `YOUTUBE_COOKIES_TEXT_2`
- `YOUTUBE_COOKIES_TEXT_3`

Optional advanced variables:

- `YOUTUBE_VISITOR_DATA`
- `YOUTUBE_PO_TOKEN`
- `YOUTUBE_PO_TOKEN_2`
- `YOUTUBE_ALLOW_NO_COOKIES_FALLBACK=1`

After adding or refreshing variables, redeploy and open `/api/youtube/status`. Confirm `cookie_profile_count` is at least `2` and `yt_dlp_version` is current.

## Instagram Reliability Variables

Instagram first tries cookieless public methods: yt-dlp public extraction, GraphQL, magic params, public page scraping, preview URL reuse, and optional Cobalt relay backups. For self-hosted relay fallback, use the same `COBALT_API_URL` / `COBALT_API_URLS` variables above.

Cookies remain optional. If you choose to use them for content you are allowed to access, the backend can rotate multiple Instagram cookie profiles:

- `INSTAGRAM_COOKIES_TEXT_1`
- `INSTAGRAM_COOKIES_TEXT_2`
- `INSTAGRAM_COOKIES_TEXT_3`

Optional:

- `INSTAGRAM_ALLOW_NO_COOKIES_FALLBACK=1`

After adding or refreshing variables, redeploy and open `/api/instagram/status`. Confirm `cookie_profile_count` is at least `2`. For best reliability, paste the link, wait for the preview to load, then click download so the backend can reuse the preview session.

## Notes

- Use enough memory if possible. `rembg`/`onnxruntime`, PDF rendering, uploads, and video conversion can be memory-heavy.
- Uploaded/generated files are temporary and stored in `backend/uploads` and `backend/downloads`.
- FFmpeg is installed in Docker for video/audio conversion.
- The frontend calls backend APIs on the same domain in production.
