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

## Instagram Reliability Variables

Instagram frequently allows preview metadata but asks the server to log in during the download request. The backend now reuses the short-lived preview media URL when possible and can rotate multiple Instagram cookie profiles:

- `INSTAGRAM_COOKIES_TEXT_1`
- `INSTAGRAM_COOKIES_TEXT_2`
- `INSTAGRAM_COOKIES_TEXT_3`

Optional:

- `INSTAGRAM_ALLOW_NO_COOKIES_FALLBACK=1`

After adding or refreshing variables, redeploy and open `/api/instagram/status`. Confirm `cookie_profile_count` is at least `2`. For best reliability, paste the link, wait for the preview to load, then click download so the backend can reuse the preview session.

## Step 4 — Bulletproof env setup (Railway Variables)

Open Railway → your service → **Variables**. Add these in order (redeploy after each batch if you want to test incrementally).

### Batch A — YouTube (recommended first)

| Variable | What to paste | Required? |
|----------|----------------|-----------|
| `YOUTUBE_PO_TOKEN` | PO token from your bgutil / token provider | Strongly recommended |
| `POT_PROVIDER_BASE_URL` | e.g. `http://127.0.0.1:4416` if you run bgutil beside the app | If using bgutil |
| `YOUTUBE_VISITOR_DATA` | `VISITOR_INFO1_LIVE…` from a fresh YouTube tab (optional) | Optional |
| `YOUTUBE_USE_COOKIES` | `1` only if you also add cookie profiles below | Optional |
| `YOUTUBE_COOKIES_TEXT_1` | Netscape cookies export (full `youtube.com` session) | Optional |
| `YOUTUBE_COOKIES_TEXT_2` | Second rotated profile | Optional |
| `YOUTUBE_COOKIES_TEXT_3` | Third rotated profile | Optional |
| `YOUTUBE_ALLOW_NO_COOKIES_FALLBACK` | `1` — keep Invidious/Piped when cookies fail | Recommended |

**How to get YouTube cookies:** Chrome → logged into YouTube → extension “Get cookies.txt LOCALLY” → export → paste entire file into `YOUTUBE_COOKIES_TEXT_1`. Repeat with 2–3 accounts or fresh exports weekly.

**Verify:** `https://YOUR-DOMAIN/api/youtube/status` → `cookie_profile_count` ≥ 2 if using cookies; `yt_dlp_version` present.

### Batch B — Instagram

| Variable | What to paste | Required? |
|----------|----------------|-----------|
| `INSTAGRAM_COOKIES_TEXT_1` | Netscape cookies for `instagram.com` (logged in) | Recommended |
| `INSTAGRAM_COOKIES_TEXT_2` | Second profile | Recommended |
| `INSTAGRAM_COOKIES_TEXT_3` | Third profile | Optional |
| `INSTAGRAM_ALLOW_NO_COOKIES_FALLBACK` | `1` — scrape/GraphQL when cookies expire | Recommended |

**Verify:** `https://YOUR-DOMAIN/api/instagram/status` → `cookie_profile_count` ≥ 2.

**User tip:** Paste reel URL → wait for preview → then Download (reuses preview session).

### Batch C — Shared fallback (both platforms)

| Variable | Example | Notes |
|----------|---------|--------|
| `COBALT_API_URL` | `https://your-cobalt-instance.com` | Last resort downloader |
| `COBALT_API_KEY` | API key if your Cobalt needs it | Optional |
| `YOUTUBE_PROXY` or `HTTPS_PROXY` | `http://user:pass@host:port` | If Railway IP is blocked |
| `INVIDIOUS_API_URLS` | `https://inv.nadeko.net,https://yewtu.be` | Extra Invidious mirrors |
| `PIPED_API_URLS` | `https://pipedapi.kavin.rocks` | Extra Piped mirrors |
| `SITE_URL` | `https://thugtools.xyz` | Canonical URLs / SEO |

### Quick test after redeploy

1. **Long YouTube** (`watch?v=…`) → preview box **wide 16:9**
2. **Shorts** (`youtube.com/shorts/…`) → preview box **tall 9:16**
3. **Instagram reel** → preview loads, download works
4. Check status endpoints above if anything fails

## Notes

- Use enough memory if possible. `rembg`/`onnxruntime`, PDF rendering, uploads, and video conversion can be memory-heavy.
- Uploaded/generated files are temporary and stored in `backend/uploads` and `backend/downloads`.
- FFmpeg is installed in Docker for video/audio conversion.
- The frontend calls backend APIs on the same domain in production.
