"""YouTube metadata/download without account cookies — Invidious, Piped, Cobalt, then yt-dlp."""
import os
import re
from urllib.parse import parse_qs, urlparse

import certifi
import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

INVIDIOUS_INSTANCES = [
    item.strip().rstrip("/")
    for item in os.environ.get(
        "INVIDIOUS_API_URLS",
        "https://invidious.io,https://inv.nadeko.net,https://vid.puffyan.us,"
        "https://invidious.fdn.fr,https://yt.artemislena.eu,https://invidious.private.coffee",
    ).split(",")
    if item.strip()
]

PIPED_INSTANCES = [
    item.strip().rstrip("/")
    for item in os.environ.get(
        "PIPED_API_URLS",
        "https://pipedapi.kavin.rocks,https://pipedapi.adminforge.de,https://api.piped.yt",
    ).split(",")
    if item.strip()
]


def extract_video_id(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    if "youtu.be" in host:
        video_id = parsed.path.strip("/").split("/")[0]
        return video_id or None
    if "youtube.com" not in host:
        return None
    if parsed.path.startswith("/shorts/"):
        return parsed.path.split("/")[2] if len(parsed.path.split("/")) > 2 else None
    query = parse_qs(parsed.query)
    if query.get("v"):
        return query["v"][0]
    match = re.search(r"/(?:embed|v|live)/([^/?#]+)", parsed.path)
    return match.group(1) if match else None


def parse_quality_height(quality_label):
    if not quality_label:
        return 0
    match = re.search(r"(\d+)", str(quality_label))
    return int(match.group(1)) if match else 0


def _get_json(url):
    try:
        response = requests.get(
            url,
            timeout=28,
            verify=certifi.where(),
            headers={"User-Agent": UA, "Accept": "application/json"},
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        return None
    return None


def fetch_invidious(video_id):
    for base in INVIDIOUS_INSTANCES:
        data = _get_json(f"{base}/api/v1/videos/{video_id}")
        if data and (data.get("formatStreams") or data.get("adaptiveFormats")):
            data["_resolver"] = "invidious"
            data["_resolver_base"] = base
            return data
    return None


def fetch_piped(video_id):
    for base in PIPED_INSTANCES:
        data = _get_json(f"{base}/streams/{video_id}")
        if data and (data.get("videoStreams") or data.get("audioStreams")):
            data["_resolver"] = "piped"
            data["_resolver_base"] = base
            return data
    return None


def fetch_cobalt(url):
    base = os.environ.get("COBALT_API_URL", "").strip().rstrip("/")
    if not base:
        return None
    endpoint = base if base.endswith("/api/json") else f"{base}/api/json"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    api_key = os.environ.get("COBALT_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Api-Key {api_key}"
    payload = {"url": url, "downloadMode": "auto", "videoQuality": "1080"}
    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=90,
            verify=certifi.where(),
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None
    if data.get("status") == "redirect" and data.get("url"):
        return {
            "_resolver": "cobalt",
            "title": "YouTube video",
            "muxed_url": data["url"],
            "height": 1080,
        }
    if data.get("status") == "picker":
        for item in data.get("picker") or []:
            if item.get("type") == "video" and item.get("url"):
                return {
                    "_resolver": "cobalt",
                    "title": "YouTube video",
                    "muxed_url": item["url"],
                    "height": 1080,
                }
    return None


def invidious_to_formats(data):
    formats = []
    for index, stream in enumerate(data.get("formatStreams") or []):
        media_url = stream.get("url")
        if not media_url:
            continue
        height = parse_quality_height(stream.get("quality") or stream.get("resolution"))
        formats.append(
            {
                "format_id": f"inv-mux-{index}",
                "url": media_url,
                "ext": "mp4",
                "height": height or 720,
                "width": stream.get("size") or 0,
                "vcodec": "avc1",
                "acodec": "aac",
                "protocol": "https",
                "format_note": "invidious-muxed",
            }
        )
    for index, stream in enumerate(data.get("adaptiveFormats") or []):
        media_url = stream.get("url")
        if not media_url:
            continue
        media_type = (stream.get("type") or "").lower()
        is_audio = media_type.startswith("audio")
        height = 0 if is_audio else parse_quality_height(stream.get("quality") or stream.get("resolution"))
        formats.append(
            {
                "format_id": f"inv-adapt-{'a' if is_audio else 'v'}-{index}",
                "url": media_url,
                "ext": "m4a" if is_audio else "mp4",
                "height": height,
                "vcodec": "none" if is_audio else "avc1",
                "acodec": "aac" if is_audio else "none",
                "protocol": "https",
                "abr": stream.get("bitrate") or 0,
                "format_note": "invidious-adaptive",
            }
        )
    return formats


def piped_to_formats(data):
    formats = []
    for index, stream in enumerate(data.get("videoStreams") or []):
        media_url = stream.get("url")
        if not media_url:
            continue
        height = int(stream.get("height") or parse_quality_height(stream.get("quality")))
        video_only = bool(stream.get("videoOnly"))
        formats.append(
            {
                "format_id": f"piped-v-{index}",
                "url": media_url,
                "ext": "mp4",
                "height": height or 720,
                "width": stream.get("width") or 0,
                "vcodec": stream.get("codec") or "avc1",
                "acodec": "none" if video_only else "aac",
                "protocol": "https",
                "format_note": "piped-video",
            }
        )
    for index, stream in enumerate(data.get("audioStreams") or []):
        media_url = stream.get("url")
        if not media_url:
            continue
        formats.append(
            {
                "format_id": f"piped-a-{index}",
                "url": media_url,
                "ext": "m4a",
                "height": 0,
                "vcodec": "none",
                "acodec": "aac",
                "protocol": "https",
                "abr": stream.get("bitrate") or 0,
                "format_note": "piped-audio",
            }
        )
    return formats


def resolver_payload_to_info(payload, url, video_id):
    resolver = payload.get("_resolver")
    if resolver == "cobalt":
        muxed = payload.get("muxed_url")
        formats = []
        if muxed:
            formats.append(
                {
                    "format_id": "cobalt-mux",
                    "url": muxed,
                    "ext": "mp4",
                    "height": int(payload.get("height") or 1080),
                    "vcodec": "avc1",
                    "acodec": "aac",
                    "protocol": "https",
                }
            )
        return {
            "id": video_id,
            "title": payload.get("title") or "YouTube video",
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "duration": None,
            "formats": formats,
            "webpage_url": url,
            "extractor": "youtube_resolver:cobalt",
        }

    if resolver == "piped":
        formats = piped_to_formats(payload)
        thumb = payload.get("thumbnail") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        duration = int(payload.get("duration") or 0) or None
        height = 0
        for item in formats:
            if item.get("height") and item.get("height") > height:
                height = int(item["height"])
        return {
            "id": video_id,
            "title": payload.get("title") or "YouTube video",
            "thumbnail": thumb,
            "duration": duration,
            "formats": formats,
            "width": None,
            "height": height or 720,
            "webpage_url": url,
            "extractor": "youtube_resolver:piped",
        }

    formats = invidious_to_formats(payload)
    thumbs = payload.get("videoThumbnails") or []
    thumb = thumbs[-1].get("url") if thumbs else f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    duration = int(payload.get("lengthSeconds") or 0) or None
    height = 0
    for item in formats:
        if item.get("height") and item.get("height") > height:
            height = int(item["height"])
    return {
        "id": video_id,
        "title": payload.get("title") or "YouTube video",
        "thumbnail": thumb,
        "duration": duration,
        "formats": formats,
        "width": None,
        "height": height or 720,
        "webpage_url": url,
        "extractor": "youtube_resolver:invidious",
    }


def fetch_youtube_info(url):
    """Try external resolvers that do not need YouTube account cookies."""
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError("Invalid YouTube URL")

    errors = []
    for fetcher in (fetch_invidious, fetch_piped):
        try:
            payload = fetcher(video_id)
            if payload:
                info = resolver_payload_to_info(payload, url, video_id)
                if info.get("formats"):
                    return info
        except Exception as error:
            errors.append(str(error)[:120])

    try:
        cobalt = fetch_cobalt(url)
        if cobalt:
            info = resolver_payload_to_info(cobalt, url, video_id)
            if info.get("formats"):
                return info
    except Exception as error:
        errors.append(str(error)[:120])

    raise ValueError(errors[-1] if errors else "All YouTube fallback APIs are unreachable")
