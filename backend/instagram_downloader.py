"""
Instagram reel downloader — isolated from YouTube / yt-dlp cookie logic.
Uses Instagram-only yt-dlp options + optional server cookies (env, no user setup).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

from yt_dlp import YoutubeDL

MIN_VIDEO_BYTES = 150 * 1024
IG_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


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
    return path.stat().st_size >= 400 * 1024 and is_valid_mp4(path, 100 * 1024)


def instagram_cookie_files(cookie_sources):
    files = []
    for source in cookie_sources or []:
        path = (source or {}).get("file") or ""
        if path and Path(path).exists():
            files.append(path)
    return files


def ytdlp_instagram_opts(outtmpl, format_selector, cookie_file=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreconfig": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "retries": 8,
        "fragment_retries": 8,
        "socket_timeout": 40,
        "outtmpl": outtmpl,
        "restrictfilenames": True,
        "format": format_selector,
        "http_headers": {
            "User-Agent": IG_UA,
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    if cookie_file:
        opts["cookiefile"] = cookie_file
    if shutil.which("ffmpeg"):
        opts["merge_output_format"] = "mp4"
        opts["prefer_ffmpeg"] = True
        opts["postprocessor_args"] = {"ffmpeg_o": ["-hide_banner", "-loglevel", "error"]}
    return opts


def format_chain(quality):
    has_ffmpeg = bool(shutil.which("ffmpeg"))
    q = str(quality or "best").lower()
    height = re.sub(r"[^0-9]", "", q)
    if has_ffmpeg:
        if height and q != "best":
            h = str(max(144, min(4320, int(height))))
            return [
                f"best[height<={h}][ext=mp4]/best[height<={h}]/best[ext=mp4]/best",
                "bv*+ba/b",
                "best",
            ]
        return ["best[ext=mp4]/best", "bv*+ba/b", "best"]
    return ["best[ext=mp4]/best", "best"]


def try_urls_for(url):
    clean = normalize_url(url)
    code = parse_shortcode(clean)
    urls = [clean]
    if code:
        urls.append(f"https://www.instagram.com/reel/{code}/")
        urls.append(f"https://www.instagram.com/reel/{code}/embed/captioned/")
    seen = set()
    ordered = []
    for item in urls:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def download_instagram(url, quality, download_dir, make_id, secure_filename, public_download_url, cookie_sources=None):
    download_dir = Path(download_dir)
    clean = normalize_url(url)
    if not parse_shortcode(clean):
        raise ValueError("Invalid Instagram URL")

    prefix = make_id()
    outtmpl = str(download_dir / f"{prefix}_%(title).80s.%(ext)s")
    cookie_files = instagram_cookie_files(cookie_sources)
    cookie_attempts = cookie_files + [None]

    errors = []
    for cookie_file in cookie_attempts:
        for try_url in try_urls_for(clean):
            for fmt in format_chain(quality):
                opts = ytdlp_instagram_opts(outtmpl, fmt, cookie_file)
                try:
                    with YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(try_url, download=True)
                except Exception as error:
                    errors.append(str(error)[:160])
                    continue

                files = [p for p in download_dir.glob(f"{prefix}_*") if p.is_file()]
                if not files:
                    errors.append("Download finished but file missing")
                    continue

                file_path = max(files, key=lambda p: p.stat().st_mtime)
                if acceptable_output(file_path):
                    title = secure_filename((info.get("title") or "instagram_reel")[:80]) or "instagram_reel"
                    return {
                        "success": True,
                        "title": info.get("title") or "Instagram reel",
                        "filename": file_path.name,
                        "file_size": file_path.stat().st_size,
                        "download_url": public_download_url(file_path.name),
                        "download_label": "Download video",
                        "note": "Downloaded with audio (Instagram media engine).",
                        "video_height": info.get("height"),
                    }
                delete_path(file_path)

    raise ValueError(errors[-1] if errors else "No downloadable video found")


def probe_instagram(url, cookie_sources=None):
    clean = normalize_url(url)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "nocheckcertificate": True,
        "ignoreconfig": True,
    }
    cookie_files = instagram_cookie_files(cookie_sources)
    if cookie_files:
        opts["cookiefile"] = cookie_files[0]

    last_error = None
    for try_url in try_urls_for(clean):
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(try_url, download=False)
            preview = info.get("url") or ""
            if not preview:
                for fmt in reversed(info.get("formats") or []):
                    if fmt.get("url") and fmt.get("vcodec") not in (None, "none"):
                        preview = fmt["url"]
                        break
            if preview:
                return {
                    "title": info.get("title") or "Instagram reel",
                    "preview_video_url": preview,
                    "height": info.get("height") or 720,
                    "webpage_url": clean,
                }
        except Exception as error:
            last_error = error
    raise ValueError(str(last_error) if last_error else "No preview")


def delete_path(path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
