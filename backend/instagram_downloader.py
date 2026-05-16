"""
Instagram reel downloader — isolated engine for ThugTools.
Order: yt-dlp (optional server cookies) → Instagram GraphQL → magic params → Cobalt.
"""
import json
import os
import re
import shutil
import subprocess
from html import unescape
from pathlib import Path
import certifi
import requests
from yt_dlp import YoutubeDL

from preview_utils import pick_preview_video_url

MIN_VIDEO_BYTES = 150 * 1024
IG_APP_ID = os.environ.get("X_IG_APP_ID", "936619743392459").strip() or "936619743392459"
IG_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
GRAPHQL_DOC_IDS = [
    os.environ.get("INSTAGRAM_GRAPHQL_DOC_ID", "").strip(),
    "10015901848480474",
    "8845758161913145",
    "23826011835252928",
]
GRAPHQL_DOC_IDS = [doc for doc in GRAPHQL_DOC_IDS if doc]


def parse_shortcode(url):
    match = re.search(r"instagram\.com/(?:p|reel|tv)/([^/?#]+)", url, re.I)
    return match.group(1) if match else None


def normalize_url(url):
    code = parse_shortcode(url)
    if not code:
        return re.sub(r"\?.*$", "", (url or "").strip())
    lowered = (url or "").lower()
    if "/reel/" in lowered:
        return f"https://www.instagram.com/reel/{code}/"
    if "/tv/" in lowered:
        return f"https://www.instagram.com/tv/{code}/"
    return f"https://www.instagram.com/p/{code}/"


def http_session():
    session = requests.Session()
    session.headers.update({"User-Agent": IG_UA, "Accept-Language": "en-US,en;q=0.9"})
    return session


def request_get(session, url, **kwargs):
    kwargs.setdefault("timeout", 35)
    try:
        return session.get(url, verify=certifi.where(), **kwargs)
    except requests.exceptions.SSLError:
        return session.get(url, verify=False, **kwargs)


def request_post(session, url, **kwargs):
    kwargs.setdefault("timeout", 35)
    try:
        return session.post(url, verify=certifi.where(), **kwargs)
    except requests.exceptions.SSLError:
        return session.post(url, verify=False, **kwargs)


def cookie_header_from_file(cookie_file):
    if not cookie_file or not Path(cookie_file).exists():
        return ""
    parts = []
    for line in Path(cookie_file).read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 7 and cols[5] and cols[6]:
            parts.append(f"{cols[5]}={cols[6]}")
    return "; ".join(parts)


def instagram_cookie_files(cookie_sources):
    files = []
    for source in cookie_sources or []:
        path = (source or {}).get("file") or ""
        if path and Path(path).exists():
            files.append(path)
    return files


def fetch_lsd_token(session):
    response = request_get(session, "https://www.instagram.com/")
    response.raise_for_status()
    html = response.text
    for pattern in (
        r'"LSD",\[\],\{"token":"([^"]+)"',
        r'"lsd":"([^"]+)"',
        r'name="lsd" value="([^"]+)"',
    ):
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return "AVqbxe3J_YA"


def walk_video_urls(obj, depth=0):
    if depth > 18:
        return
    if isinstance(obj, dict):
        for key in ("video_url", "playback_url", "playable_url"):
            value = obj.get(key)
            if isinstance(value, str) and value.startswith("http"):
                yield unescape(value.replace("\\u0026", "&").replace("\\/", "/"))
        versions = obj.get("video_versions")
        if isinstance(versions, list):
            for item in versions:
                url = item.get("url")
                if url:
                    yield unescape(url.replace("\\u0026", "&").replace("\\/", "/"))
        for value in obj.values():
            yield from walk_video_urls(value, depth + 1)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk_video_urls(value, depth + 1)


def resolve_graphql(shortcode, cookie_header=""):
    session = http_session()
    lsd = fetch_lsd_token(session)
    variables = json.dumps({"shortcode": shortcode})
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-IG-App-ID": IG_APP_ID,
        "X-FB-LSD": lsd,
        "X-ASBD-ID": "129477",
        "Origin": "https://www.instagram.com",
        "Referer": f"https://www.instagram.com/reel/{shortcode}/",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header

    candidates = []
    title = "instagram_reel"
    for doc_id in GRAPHQL_DOC_IDS:
        data = {"variables": variables, "doc_id": doc_id, "lsd": lsd}
        response = request_post(session, "https://www.instagram.com/api/graphql", data=data, headers=headers)
        if response.status_code != 200:
            continue
        try:
            payload = response.json()
        except json.JSONDecodeError:
            continue
        media = payload.get("data", {}).get("xdt_shortcode_media")
        if isinstance(media, dict):
            caption = media.get("edge_media_to_caption", {}).get("edges") or []
            if caption:
                title = (caption[0].get("node") or {}).get("text") or title
            elif media.get("title"):
                title = media.get("title")
        for media_url in walk_video_urls(payload):
            if "fbcdn" in media_url or "cdninstagram" in media_url:
                candidates.append(media_url)
        if candidates:
            break

    if not candidates:
        raise ValueError("GraphQL did not return a video URL")
    return {"url": candidates[0], "title": title[:200]}


def resolve_magic_params(shortcode, cookie_header=""):
    session = http_session()
    headers = {
        "X-IG-App-ID": IG_APP_ID,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://www.instagram.com/reel/{shortcode}/",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    for path in (f"reel/{shortcode}", f"p/{shortcode}"):
        api_url = f"https://www.instagram.com/{path}/?__a=1&__d=dis"
        response = request_get(session, api_url, headers=headers)
        if response.status_code != 200:
            continue
        try:
            payload = response.json()
        except json.JSONDecodeError:
            continue
        items = payload.get("items") or []
        if not items:
            continue
        item = items[0]
        title = (item.get("caption") or {}).get("text") or "instagram_reel"
        urls = list(walk_video_urls(item))
        if urls:
            return {"url": urls[0], "title": title[:200]}
    raise ValueError("Magic params API did not return video")


def resolve_cobalt(url):
    base = os.environ.get("COBALT_API_URL", "").strip().rstrip("/")
    if not base:
        raise ValueError("Cobalt not configured")
    endpoint = base if base.endswith("/api/json") else f"{base}/api/json"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    api_key = os.environ.get("COBALT_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Api-Key {api_key}"
    session = http_session()
    response = request_post(
        session,
        endpoint,
        json={"url": normalize_url(url), "downloadMode": "auto", "videoQuality": "1080"},
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status") == "redirect" and data.get("url"):
        return {"url": data["url"], "title": "instagram_reel"}
    if data.get("status") == "picker":
        for item in data.get("picker") or []:
            if item.get("type") == "video" and item.get("url"):
                return {"url": item["url"], "title": "instagram_reel"}
    raise ValueError("Cobalt could not process URL")


def is_rate_or_login_error(message):
    lowered = (message or "").lower()
    return any(
        token in lowered
        for token in (
            "rate-limit",
            "rate limit",
            "login required",
            "not available",
            "cookies",
            "authenticate",
            "empty media",
        )
    )


def ffprobe_path():
    found = shutil.which("ffprobe")
    if found:
        return found
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    sibling = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    return str(sibling) if sibling.exists() else None


def is_valid_mp4(path, min_bytes=MIN_VIDEO_BYTES):
    if not path.exists() or path.stat().st_size < min_bytes:
        return False
    try:
        head = path.open("rb").read(12)
    except OSError:
        return False
    return len(head) >= 8 and head[4:8] == b"ftyp"


def has_audio(path):
    if not is_valid_mp4(path, min_bytes=50 * 1024):
        return False
    probe = ffprobe_path()
    if not probe:
        return path.stat().st_size >= MIN_VIDEO_BYTES
    cmd = [
        probe,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        return path.stat().st_size >= MIN_VIDEO_BYTES
    if result.returncode != 0:
        return path.stat().st_size >= MIN_VIDEO_BYTES
    return bool((result.stdout or "").strip())


def acceptable_output(path):
    if not is_valid_mp4(path):
        return False
    if has_audio(path):
        return True
    return path.stat().st_size >= 400 * 1024


def download_cdn_file(media_url, path, referer):
    session = http_session()
    headers = {
        "User-Agent": IG_UA,
        "Referer": referer,
        "Accept": "*/*",
    }
    response = request_get(session, media_url, headers=headers, stream=True)
    response.raise_for_status()
    with path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=256 * 1024):
            if chunk:
                handle.write(chunk)
    return path.exists() and path.stat().st_size >= MIN_VIDEO_BYTES


def ytdlp_instagram_opts(outtmpl, format_selector, cookie_file=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreconfig": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "retries": 6,
        "fragment_retries": 6,
        "socket_timeout": 45,
        "outtmpl": outtmpl,
        "restrictfilenames": True,
        "format": format_selector,
        "http_headers": {"User-Agent": IG_UA, "Accept-Language": "en-US,en;q=0.9"},
    }
    if cookie_file:
        opts["cookiefile"] = cookie_file
    if shutil.which("ffmpeg"):
        opts["merge_output_format"] = "mp4"
        opts["prefer_ffmpeg"] = True
    return opts


def format_chain(quality):
    has_ffmpeg = bool(shutil.which("ffmpeg"))
    q = str(quality or "best").lower()
    height = re.sub(r"[^0-9]", "", q)
    if has_ffmpeg:
        if height and q != "best":
            h = str(max(144, min(4320, int(height))))
            return [
                f"bv*[height<={h}]+ba/b[height<={h}][acodec!=none]/b[height<={h}]",
                f"best[height<={h}][ext=mp4]/best[height<={h}][acodec!=none]",
            ]
        return ["bv*+ba/b[ext=mp4]/best[ext=mp4]/best", "best"]
    if height and q != "best":
        h = str(max(144, min(4320, int(height))))
        return [f"best[height<={h}][acodec!=none][ext=mp4]/best[height<={h}][ext=mp4]"]
    return ["best[ext=mp4]/best"]


def try_urls_for(url):
    clean = normalize_url(url)
    code = parse_shortcode(clean)
    urls = [clean]
    if code:
        urls.append(f"https://www.instagram.com/reel/{code}/")
    seen = set()
    ordered = []
    for item in urls:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def try_ytdlp(url, quality, download_dir, prefix, cookie_file=None):
    outtmpl = str(download_dir / f"{prefix}_%(title).80s.%(ext)s")
    errors = []
    for try_url in try_urls_for(url):
        for fmt in format_chain(quality):
            try:
                with YoutubeDL(ytdlp_instagram_opts(outtmpl, fmt, cookie_file)) as ydl:
                    info = ydl.extract_info(try_url, download=True)
            except Exception as error:
                errors.append(str(error)[:180])
                continue
            files = [p for p in download_dir.glob(f"{prefix}_*") if p.is_file()]
            if not files:
                continue
            file_path = max(files, key=lambda p: p.stat().st_mtime)
            if acceptable_output(file_path):
                return file_path, info
            delete_path(file_path)
    raise ValueError(errors[-1] if errors else "yt-dlp failed")


def try_direct_api(shortcode, cookie_header, referer, download_dir, prefix, secure_filename):
    errors = []
    resolvers = [resolve_graphql, resolve_magic_params]
    for resolver in resolvers:
        try:
            meta = resolver(shortcode, cookie_header)
        except Exception as error:
            errors.append(str(error)[:120])
            continue
        title = secure_filename((meta.get("title") or "instagram_reel")[:80]) or "instagram_reel"
        path = download_dir / f"{prefix}_{title}.mp4"
        try:
            if download_cdn_file(meta["url"], path, referer) and acceptable_output(path):
                return path, meta.get("title") or "Instagram reel"
        except Exception as error:
            errors.append(str(error)[:120])
            delete_path(path)
    raise ValueError(errors[-1] if errors else "Direct API failed")


def delete_path(path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def download_instagram(url, quality, download_dir, make_id, secure_filename, public_download_url, cookie_sources=None):
    download_dir = Path(download_dir)
    clean = normalize_url(url)
    shortcode = parse_shortcode(clean)
    if not shortcode:
        raise ValueError("Invalid Instagram URL")

    prefix = make_id()
    referer = clean
    cookie_files = instagram_cookie_files(cookie_sources)
    cookie_attempts = cookie_files + [None]
    errors = []

    for cookie_file in cookie_attempts:
        try:
            file_path, info = try_ytdlp(clean, quality, download_dir, prefix, cookie_file)
            return {
                "success": True,
                "title": info.get("title") or "Instagram reel",
                "filename": file_path.name,
                "file_size": file_path.stat().st_size,
                "download_url": public_download_url(file_path.name),
                "download_label": "Download video",
                "note": "Downloaded with audio.",
                "video_height": info.get("height"),
            }
        except Exception as error:
            errors.append(str(error)[:180])
            if cookie_file is None or not is_rate_or_login_error(str(error)):
                pass

    cookie_header = cookie_header_from_file(cookie_files[0]) if cookie_files else ""
    try:
        file_path, title = try_direct_api(shortcode, cookie_header, referer, download_dir, prefix, secure_filename)
        return {
            "success": True,
            "title": title,
            "filename": file_path.name,
            "file_size": file_path.stat().st_size,
            "download_url": public_download_url(file_path.name),
            "download_label": "Download video",
            "note": "Downloaded via Instagram media API (works when server is rate-limited).",
            "video_height": None,
        }
    except Exception as error:
        errors.append(str(error)[:180])

    if os.environ.get("COBALT_API_URL", "").strip():
        try:
            meta = resolve_cobalt(clean)
            title = secure_filename((meta.get("title") or "instagram_reel")[:80]) or "instagram_reel"
            path = download_dir / f"{prefix}_{title}.mp4"
            if download_cdn_file(meta["url"], path, referer) and acceptable_output(path):
                return {
                    "success": True,
                    "title": meta.get("title") or "Instagram reel",
                    "filename": path.name,
                    "file_size": path.stat().st_size,
                    "download_url": public_download_url(path.name),
                    "download_label": "Download video",
                    "note": "Downloaded via Cobalt relay.",
                    "video_height": None,
                }
            delete_path(path)
        except Exception as error:
            errors.append(str(error)[:180])

    if is_rate_or_login_error(errors[-1] if errors else ""):
        raise ValueError(
            "Instagram is busy on this server. Wait 1–2 minutes and try again, or use Best quality."
        )
    raise ValueError(errors[-1] if errors else "Could not download this Instagram reel")


def probe_instagram(url, cookie_sources=None):
    clean = normalize_url(url)
    shortcode = parse_shortcode(clean)
    if not shortcode:
        raise ValueError("Invalid URL")
    cookie_files = instagram_cookie_files(cookie_sources)
    cookie_header = cookie_header_from_file(cookie_files[0]) if cookie_files else ""

    for cookie_file in cookie_files + [None]:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "ignoreconfig": True,
        }
        if cookie_file:
            opts["cookiefile"] = cookie_file
        for try_url in try_urls_for(clean):
            try:
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(try_url, download=False)
                preview = pick_preview_video_url(info.get("formats") or [])
                if not preview:
                    preview = info.get("url") or ""
                if preview:
                    return {
                        "title": info.get("title") or "Instagram reel",
                        "preview_video_url": preview,
                        "height": info.get("height") or 720,
                        "webpage_url": clean,
                        "info": info,
                    }
            except Exception:
                continue

    try:
        meta = resolve_graphql(shortcode, cookie_header)
        return {
            "title": meta.get("title") or "Instagram reel",
            "preview_video_url": meta["url"],
            "height": 720,
            "webpage_url": clean,
        }
    except Exception:
        pass

    raise ValueError("No preview")
