"""Instagram reel resolver: public scrape, yt-dlp metadata, optional Cobalt."""
import json
import os
import re
from html import unescape
from urllib.parse import unquote

import certifi
import requests
from yt_dlp import YoutubeDL

IG_APP_ID = "936619743392459"
USER_AGENTS = [
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
]


def parse_shortcode(url):
    match = re.search(r"instagram\.com/(?:p|reel|tv)/([^/?#]+)", url, re.I)
    return match.group(1) if match else None


def normalize_url(url):
    code = parse_shortcode(url)
    if not code:
        return None
    lowered = url.lower()
    if "/reel/" in lowered:
        return f"https://www.instagram.com/reel/{code}/"
    if "/tv/" in lowered:
        return f"https://www.instagram.com/tv/{code}/"
    return f"https://www.instagram.com/p/{code}/"


def decode_cdn_url(value):
    text = unescape(value or "")
    text = text.replace("\\u0026", "&").replace("\\/", "/").replace("&amp;", "&")
    if "\\u" in text:
        try:
            text = text.encode("utf-8").decode("unicode_escape")
        except Exception:
            pass
    return text


def is_video_url(media_url):
    if not media_url or not media_url.startswith("http"):
        return False
    lowered = media_url.lower()
    blocked = (
        "rsrc.php",
        "static.cdninstagram",
        ".ico",
        ".woff",
        ".js",
        ".css",
        ".html",
        ".json",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".svg",
        ".heic",
    )
    if any(token in lowered for token in blocked):
        return False
    if "fbcdn.net" in lowered:
        return any(token in lowered for token in ("/o1/v/", "/v/t16/", "/v/t2/", "/m366/", ".mp4"))
    return ".mp4" in lowered


def _session():
    session = requests.Session()
    session.headers.update(
        {
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return session


def fetch_html(url, user_agent=None):
    session = _session()
    headers = {"User-Agent": user_agent or USER_AGENTS[0]}
    try:
        session.get("https://www.instagram.com/", headers=headers, timeout=20, verify=certifi.where())
    except Exception:
        pass
    try:
        response = session.get(url, headers=headers, timeout=35, verify=certifi.where())
    except requests.exceptions.SSLError:
        response = session.get(url, headers=headers, timeout=35, verify=False)
    response.raise_for_status()
    return response.text


def fetch_ajax_json(shortcode, user_agent=None):
    headers = {
        "User-Agent": user_agent or USER_AGENTS[1],
        "X-IG-App-ID": IG_APP_ID,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
        "Referer": f"https://www.instagram.com/reel/{shortcode}/",
    }
    endpoints = [
        f"https://www.instagram.com/reel/{shortcode}/?__a=1&__d=dis",
        f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis",
    ]
    for endpoint in endpoints:
        try:
            response = requests.get(endpoint, headers=headers, timeout=25, verify=certifi.where())
        except requests.exceptions.SSLError:
            response = requests.get(endpoint, headers=headers, timeout=25, verify=False)
        if response.status_code != 200:
            continue
        try:
            return response.json()
        except json.JSONDecodeError:
            continue
    return None


def _walk_json(obj, depth=0):
    if depth > 16:
        return
    if isinstance(obj, dict):
        versions = obj.get("video_versions")
        if isinstance(versions, list):
            for item in versions:
                media_url = item.get("url")
                if media_url:
                    yield {
                        "url": decode_cdn_url(media_url),
                        "height": int(item.get("height") or 720),
                    }
        for key in ("playable_url", "playback_url", "video_url", "src", "contentUrl"):
            media_url = obj.get(key)
            if isinstance(media_url, str):
                media_url = decode_cdn_url(media_url)
                if is_video_url(media_url):
                    yield {"url": media_url, "height": int(obj.get("height") or 720)}
        for value in obj.values():
            yield from _walk_json(value, depth + 1)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_json(value, depth + 1)


def extract_candidates(html):
    found = []
    title = None

    title_match = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        html,
        re.I,
    )
    if title_match:
        title = unescape(title_match.group(1))

    for pattern in (
        r'<meta[^>]+property=["\']og:video(?::secure_url|:url)?["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:video(?::secure_url|:url)?',
    ):
        for match in re.finditer(pattern, html, re.I):
            media_url = decode_cdn_url(match.group(1))
            if is_video_url(media_url):
                found.append({"url": media_url, "height": 1080})

    for match in re.finditer(
        r"https://[^\"'\\\s]+(?:cdninstagram|fbcdn)[^\"'\\\s]+",
        html,
        re.I,
    ):
        media_url = decode_cdn_url(match.group(0))
        if is_video_url(media_url):
            found.append({"url": media_url, "height": 720})

    for match in re.finditer(r'"video_versions"\s*:\s*(\[[\s\S]*?\])\s*[,}]', html):
        try:
            versions = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        for item in versions:
            media_url = item.get("url")
            if media_url:
                found.append(
                    {
                        "url": decode_cdn_url(media_url),
                        "height": int(item.get("height") or 720),
                    }
                )

    for key in ("playable_url", "playback_url", "video_url"):
        for match in re.finditer(rf'"{key}"\s*:\s*"((?:\\.|[^"\\])*)"', html):
            media_url = decode_cdn_url(match.group(1))
            if is_video_url(media_url):
                found.append({"url": media_url, "height": 720})

    for match in re.finditer(
        r'<script[^>]+type=["\']application/json["\'][^>]*>([\s\S]*?)</script>',
        html,
        re.I,
    ):
        blob = match.group(1).strip()
        if "video_versions" not in blob and "playable_url" not in blob and "cdninstagram" not in blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        found.extend(_walk_json(data))

    seen = set()
    unique = []
    for item in found:
        media_url = item.get("url") or ""
        if media_url in seen or not is_video_url(media_url):
            continue
        seen.add(media_url)
        unique.append(item)

    unique.sort(key=lambda row: int(row.get("height") or 0), reverse=True)
    return unique, title


def resolve_via_ytdlp(url):
    code = parse_shortcode(url)
    if not code:
        raise ValueError("Invalid Instagram URL")

    targets = [
        normalize_url(url) or url,
        f"https://www.instagram.com/reel/{code}/embed/captioned/",
        f"https://www.instagram.com/p/{code}/embed/captioned/",
    ]
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "nocheckcertificate": True,
        "noplaylist": True,
        "ignoreconfig": True,
    }

    candidates = []
    title = "instagram_reel"
    for target in targets:
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target, download=False)
        except Exception:
            continue
        title = info.get("title") or title
        for fmt in info.get("formats") or []:
            media_url = fmt.get("url")
            if not media_url or not media_url.startswith("http"):
                continue
            vcodec = fmt.get("vcodec")
            acodec = fmt.get("acodec")
            if not vcodec or vcodec == "none":
                continue
            height = int(fmt.get("height") or 0)
            has_audio = acodec and acodec != "none"
            if height <= 0 and not has_audio:
                continue
            candidates.append(
                {
                    "url": media_url,
                    "height": height or (1080 if has_audio else 720),
                    "has_audio": has_audio,
                }
            )
        if info.get("url") and is_video_url(info.get("url")):
            candidates.append(
                {
                    "url": info["url"],
                    "height": int(info.get("height") or 720),
                    "has_audio": bool(info.get("acodec") and info.get("acodec") != "none"),
                }
            )
        if candidates:
            break

    seen = set()
    unique = []
    for item in sorted(candidates, key=lambda row: (row.get("has_audio", False), row.get("height", 0)), reverse=True):
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        unique.append(item)

    if not unique:
        raise ValueError("yt-dlp could not read Instagram media")
    return {
        "candidates": unique,
        "title": title,
        "webpage_url": normalize_url(url) or url,
    }


def scrape_instagram_candidates(url):
    normalized = normalize_url(url)
    if not normalized:
        raise ValueError("Invalid Instagram URL")

    code = parse_shortcode(normalized)
    pages = [
        normalized,
        f"https://www.instagram.com/reel/{code}/embed/captioned/",
        f"https://www.instagram.com/p/{code}/embed/captioned/",
    ]

    merged = []
    title = None
    errors = []

    ajax = fetch_ajax_json(code)
    if ajax:
        merged.extend(list(_walk_json(ajax)))

    for user_agent in USER_AGENTS:
        for page in pages:
            try:
                html = fetch_html(page, user_agent=user_agent)
                candidates, page_title = extract_candidates(html)
                if page_title:
                    title = page_title
                merged.extend(candidates)
            except Exception as error:
                errors.append(str(error))

    seen = set()
    unique = []
    for item in merged:
        media_url = item.get("url") if isinstance(item, dict) else item
        if isinstance(item, dict):
            media_url = item.get("url")
            height = int(item.get("height") or 720)
        else:
            media_url = item
            height = 720
        if not media_url or media_url in seen or not is_video_url(media_url):
            continue
        seen.add(media_url)
        unique.append({"url": media_url, "height": height})

    unique.sort(key=lambda row: int(row.get("height") or 0), reverse=True)
    if not unique:
        raise ValueError(errors[-1] if errors else "No downloadable video found")

    return {"candidates": unique, "title": title or "instagram_reel", "webpage_url": normalized}


def fetch_via_cobalt(url, api_base=None):
    base = (api_base or os.environ.get("COBALT_API_URL", "")).strip().rstrip("/")
    if not base:
        raise ValueError("Cobalt API URL is not configured")

    endpoint = base if base.endswith("/api/json") else f"{base}/api/json"
    payload = {"url": url, "downloadMode": "auto", "videoQuality": "1080"}
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    api_key = os.environ.get("COBALT_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Api-Key {api_key}"

    try:
        response = requests.post(
            endpoint, json=payload, headers=headers, timeout=90, verify=certifi.where()
        )
    except requests.exceptions.SSLError:
        response = requests.post(
            endpoint, json=payload, headers=headers, timeout=90, verify=False
        )
    response.raise_for_status()
    data = response.json()

    if data.get("status") == "redirect" and data.get("url"):
        return {
            "candidates": [{"url": data["url"], "height": 1080}],
            "title": "instagram_reel",
            "webpage_url": normalize_url(url) or url,
        }

    if data.get("status") == "picker":
        videos = [
            item
            for item in data.get("picker") or []
            if item.get("type") == "video" and item.get("url")
        ]
        if videos:
            return {
                "candidates": [{"url": videos[0]["url"], "height": 1080}],
                "title": "instagram_reel",
                "webpage_url": normalize_url(url) or url,
            }

    error = data.get("error") or {}
    if isinstance(error, dict):
        raise ValueError(error.get("code") or "Cobalt could not process this URL")
    raise ValueError("Cobalt could not process this URL")


def resolve_instagram_media(url):
    errors = []
    for resolver in (resolve_via_ytdlp, scrape_instagram_candidates):
        try:
            return resolver(url)
        except Exception as error:
            errors.append(str(error))

    cobalt = os.environ.get("COBALT_API_URL", "").strip()
    if cobalt:
        try:
            return fetch_via_cobalt(url, cobalt)
        except Exception as error:
            errors.append(str(error))

    raise ValueError(errors[-1] if errors else "No downloadable video found")


def filter_by_quality(candidates, quality):
    quality_value = str(quality or "best").lower()
    height = re.sub(r"[^0-9]", "", quality_value)
    if quality_value == "best" or not height:
        return candidates
    max_height = max(144, min(4320, int(height)))
    filtered = [item for item in candidates if int(item.get("height") or 0) <= max_height]
    return filtered or candidates
