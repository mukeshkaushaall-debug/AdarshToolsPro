"""Stable cookieless YouTube provider chain.

This module intentionally avoids public-instance scraping, browser sessions, and
cookies. Downloads are resolved through explicitly configured Cobalt-compatible
relays. Metadata uses YouTube oEmbed plus deterministic thumbnail URLs so
preview stays fast even when download providers are degraded.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urlparse

import certifi
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from media_infra import CircuitBreaker, TTLCache, env_int, retry_call


USER_AGENT = os.environ.get(
    "MEDIA_HTTP_USER_AGENT",
    "ThugTools/1.0 (+https://thugtools.xyz; public-media-processing)",
)
METADATA_CACHE = TTLCache(
    ttl_seconds=env_int("YOUTUBE_METADATA_CACHE_SECONDS", 15 * 60, minimum=60),
    max_items=env_int("YOUTUBE_METADATA_CACHE_ITEMS", 1024, minimum=64),
)
PROVIDER_CIRCUIT = CircuitBreaker(
    failure_threshold=env_int("YOUTUBE_PROVIDER_FAILURE_THRESHOLD", 3, minimum=1),
    cooldown_seconds=env_int("YOUTUBE_PROVIDER_COOLDOWN_SECONDS", 180, minimum=10),
)


def _session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retries,
        pool_connections=env_int("MEDIA_HTTP_POOL_CONNECTIONS", 16, minimum=2),
        pool_maxsize=env_int("MEDIA_HTTP_POOL_MAXSIZE", 32, minimum=4),
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    session.verify = certifi.where()
    return session


HTTP = _session()


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderResponse:
    provider: str
    base_url: str
    data: dict


def _env_list(name: str) -> list[str]:
    return [item.strip().rstrip("/") for item in os.environ.get(name, "").split(",") if item.strip()]


def extract_video_id(url: str) -> str | None:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().replace("www.", "")
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
        return video_id if _valid_video_id(video_id) else None
    if host not in {"youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"}:
        return None
    if parsed.path.startswith("/shorts/"):
        parts = parsed.path.split("/")
        video_id = parts[2] if len(parts) > 2 else ""
        return video_id if _valid_video_id(video_id) else None
    query = parse_qs(parsed.query)
    if query.get("v") and _valid_video_id(query["v"][0]):
        return query["v"][0]
    match = re.search(r"/(?:embed|v|live)/([^/?#]+)", parsed.path)
    if match and _valid_video_id(match.group(1)):
        return match.group(1)
    return None


def _valid_video_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{6,20}", value or ""))


def _canonical_url(url: str, video_id: str) -> str:
    if "/shorts/" in (url or ""):
        return f"https://www.youtube.com/shorts/{video_id}"
    return f"https://www.youtube.com/watch?v={video_id}"


def _quality(quality: str | int | None) -> str:
    value = str(quality or "1080").lower()
    if value == "best":
        return "max"
    match = re.search(r"\d+", value)
    if not match:
        return "1080"
    return str(max(144, min(4320, int(match.group(0)))))


def cobalt_bases() -> list[str]:
    bases = []
    bases.extend(_env_list("COBALT_API_URL"))
    bases.extend(_env_list("COBALT_API_URLS"))
    bases.extend(_env_list("MEDIA_PROVIDER_URLS"))
    return list(dict.fromkeys(base for base in bases if base.startswith(("http://", "https://"))))


def cobalt_auth_header() -> str:
    explicit = os.environ.get("COBALT_AUTHORIZATION", "").strip()
    if explicit:
        return explicit
    api_key = os.environ.get("COBALT_API_KEY", "").strip()
    return f"Api-Key {api_key}" if api_key else ""


def cobalt_endpoints(base: str) -> list[str]:
    base = base.rstrip("/")
    if base.endswith("/api/json"):
        return [base]
    return [f"{base}/api/json", base]


def cobalt_url_from_response(data: dict) -> str:
    status = data.get("status")
    if status in {"redirect", "tunnel"} and data.get("url"):
        return data["url"]
    if status == "picker":
        for item in data.get("picker") or []:
            if item.get("type") in {"video", "audio"} and item.get("url"):
                return item["url"]
    if status == "local-processing":
        tunnels = data.get("tunnel") or []
        if len(tunnels) == 1:
            item = tunnels[0]
            return item.get("url") if isinstance(item, dict) else item
    return ""


def _post_cobalt(endpoint: str, payload: dict, auth: str, timeout: int) -> dict:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    response = HTTP.post(endpoint, json=payload, headers=headers, timeout=timeout)
    if response.status_code in {401, 403, 429, 500, 502, 503, 504}:
        raise ProviderError(f"provider returned HTTP {response.status_code}")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ProviderError("provider returned invalid JSON")
    return data


def fetch_cobalt(url: str, quality: str | int | None = "1080") -> dict | None:
    bases = cobalt_bases()
    if not bases:
        return None
    timeout = env_int("COBALT_TIMEOUT_SECONDS", 75, minimum=10, maximum=180)
    auth = cobalt_auth_header()
    payload = {
        "url": url,
        "downloadMode": "auto",
        "filenameStyle": "basic",
        "videoQuality": _quality(quality),
        "youtubeVideoCodec": "h264",
        "youtubeVideoContainer": "mp4",
        "localProcessing": "disabled",
    }
    max_relays = env_int("COBALT_MAX_RELAYS_PER_REQUEST", 4, minimum=1, maximum=12)
    for base in bases[:max_relays]:
        if not PROVIDER_CIRCUIT.available(base):
            continue
        for endpoint in cobalt_endpoints(base):
            started = time.time()
            try:
                data = retry_call(
                    lambda endpoint=endpoint: _post_cobalt(endpoint, payload, auth, timeout),
                    attempts=2,
                    base_delay=0.5,
                    retryable=(ProviderError, requests.RequestException, ValueError),
                )
                media_url = cobalt_url_from_response(data)
                if media_url:
                    PROVIDER_CIRCUIT.success(base)
                    return {
                        "_resolver": "cobalt",
                        "_resolver_base": base,
                        "_provider_latency_ms": int((time.time() - started) * 1000),
                        "title": data.get("filename") or "YouTube video",
                        "muxed_url": media_url,
                        "height": 1080 if _quality(quality) == "max" else int(_quality(quality)),
                    }
            except Exception:
                continue
        PROVIDER_CIRCUIT.failure(base)
    return None


def fetch_oembed(url: str) -> dict | None:
    def call() -> dict | None:
        response = HTTP.get(
            f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json",
            timeout=env_int("YOUTUBE_OEMBED_TIMEOUT_SECONDS", 8, minimum=2, maximum=30),
        )
        if response.status_code != 200:
            return None
        data = response.json()
        return data if isinstance(data, dict) and data.get("title") else None

    try:
        return retry_call(call, attempts=2, retryable=(requests.RequestException, ValueError))
    except Exception:
        return None


def minimal_youtube_info(url: str, video_id: str) -> dict:
    cache_key = f"minimal:{video_id}"
    cached = METADATA_CACHE.get(cache_key)
    if cached:
        return dict(cached)
    canonical = _canonical_url(url, video_id)
    oembed = fetch_oembed(canonical)
    title = (oembed or {}).get("title") or "YouTube video"
    thumb = (oembed or {}).get("thumbnail_url") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    info = {
        "id": video_id,
        "title": title,
        "thumbnail": thumb,
        "duration": None,
        "formats": [],
        "width": None,
        "height": 720,
        "webpage_url": canonical,
        "extractor": "youtube_resolver:oembed",
        "_metadata_only": True,
    }
    METADATA_CACHE.set(cache_key, dict(info))
    return info


def resolver_payload_to_info(payload: dict, url: str, video_id: str) -> dict:
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
    base = minimal_youtube_info(url, video_id)
    base.update(
        {
            "formats": formats,
            "height": int(payload.get("height") or base.get("height") or 720),
            "extractor": "youtube_resolver:cobalt",
            "_resolver_base": payload.get("_resolver_base"),
            "_provider_latency_ms": payload.get("_provider_latency_ms"),
            "_metadata_only": False,
        }
    )
    if payload.get("title") and payload["title"] != "YouTube video":
        base["title"] = payload["title"]
    return base


def fetch_youtube_info(url: str, require_formats: bool = False, quality: str | int | None = "1080") -> dict:
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError("Invalid YouTube URL")
    canonical = _canonical_url(url, video_id)
    if not require_formats:
        return minimal_youtube_info(canonical, video_id)
    cache_key = f"formats:{video_id}:{_quality(quality)}"
    cached = METADATA_CACHE.get(cache_key)
    if cached:
        return dict(cached)
    payload = fetch_cobalt(canonical, quality)
    if payload:
        info = resolver_payload_to_info(payload, canonical, video_id)
        METADATA_CACHE.set(cache_key, dict(info))
        return info
    raise ValueError(
        "No stable YouTube provider is available. Configure COBALT_API_URL or COBALT_API_URLS with one or more self-hosted Cobalt relays."
    )


def resolver_status() -> dict:
    bases = cobalt_bases()
    return {
        "provider_chain": ["cobalt-relay", "oembed-metadata"],
        "cookies_required": False,
        "cookies_supported": False,
        "manual_browser_sessions": False,
        "public_instance_scraping": False,
        "cobalt_configured": bool(bases),
        "cobalt_relay_count": len(bases),
        "metadata_cache": True,
    }
