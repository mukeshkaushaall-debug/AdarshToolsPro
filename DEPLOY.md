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

## Notes

- Use enough memory if possible. `rembg`/`onnxruntime`, PDF rendering, uploads, and video conversion can be memory-heavy.
- Uploaded/generated files are temporary and stored in `backend/uploads` and `backend/downloads`.
- FFmpeg is installed in Docker for video/audio conversion.
- The frontend calls backend APIs on the same domain in production.
