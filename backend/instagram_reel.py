"""Cookie-free Instagram reel/post video resolver (public scrape + optional Cobalt API)."""
import json
import os
import re
from html import unescape
from urllib.parse import urlparse

import certifi
import requests

IG_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


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
    text = text.replace("\\u0026", "&").replace("\\/", "/")
    if "\\u" in text:
        try:
            text = text.encode("utf-8").decode("unicode_escape")
        except Exception:
            pass
    return text


def fetch_html(url):
    headers = {
        "User-Agent": IG_MOBILE_UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        response = requests.get(url, headers=headers, timeout=30, verify=certifi.where())
    except requests.exceptions.SSLError:
        response = requests.get(url, headers=headers, timeout=30, verify=False)
    response.raise_for_status()
    return response.text


def _walk_json(obj, depth=0):
    if depth > 14:
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
        for key in ("playable_url", "playback_url", "video_url"):
            media_url = obj.get(key)
            if isinstance(media_url, str) and media_url.startswith("http"):
                yield {"url": decode_cdn_url(media_url), "height": 720}
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

    for match in re.finditer(
        r'<meta[^>]+property=["\']og:video(?::url)?["\'][^>]+content=["\']([^"\']+)',
        html,
        re.I,
    ):
        found.append({"url": decode_cdn_url(match.group(1)), "height": 1080})

    for match in re.finditer(r'"video_versions"\s*:\s*(\[[^\]]+\])', html):
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
        for match in re.finditer(rf'"{key}"\s*:\s*"([^"]+)"', html):
            found.append({"url": decode_cdn_url(match.group(1)), "height": 720})

    for match in re.finditer(
        r'<script[^>]+type=["\']application/json["\'][^>]*>([^<]+)</script>',
        html,
        re.I,
    ):
        blob = match.group(1).strip()
        if "video_versions" not in blob and "playable_url" not in blob:
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
        if not media_url.startswith("http") or media_url in seen:
            continue
        if "cdninstagram" not in media_url and "fbcdn" not in media_url and ".mp4" not in media_url.lower():
            continue
        seen.add(media_url)
        unique.append(item)

    unique.sort(key=lambda row: int(row.get("height") or 0), reverse=True)
    return unique, title


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
    for page in pages:
        try:
            html = fetch_html(page)
            candidates, page_title = extract_candidates(html)
            if page_title:
                title = page_title
            merged.extend(candidates)
            if candidates:
                break
        except Exception as error:
            errors.append(str(error))

    seen = set()
    unique = []
    for item in merged:
        media_url = item["url"]
        if media_url in seen:
            continue
        seen.add(media_url)
        unique.append(item)

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
            endpoint,
            json=payload,
            headers=headers,
            timeout=90,
            verify=certifi.where(),
        )
    except requests.exceptions.SSLError:
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=90,
            verify=False,
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
    try:
        return scrape_instagram_candidates(url)
    except Exception:
        cobalt = os.environ.get("COBALT_API_URL", "").strip()
        if cobalt:
            return fetch_via_cobalt(url, cobalt)
        raise


def filter_by_quality(candidates, quality):
    quality_value = str(quality or "best").lower()
    height = re.sub(r"[^0-9]", "", quality_value)
    if quality_value == "best" or not height:
        return candidates
    max_height = max(144, min(4320, int(height)))
    filtered = [item for item in candidates if int(item.get("height") or 0) <= max_height]
    return filtered or candidates
