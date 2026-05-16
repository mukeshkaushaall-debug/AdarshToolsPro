"""YouTube metadata/download without account cookies — parallel APIs + oEmbed safety net."""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, quote, urlparse

import certifi
import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

STATIC_INVIDIOUS = [
    "https://invidious.io",
    "https://inv.nadeko.net",
    "https://vid.puffyan.us",
    "https://invidious.fdn.fr",
    "https://yt.artemislena.eu",
    "https://invidious.private.coffee",
    "https://invidious.privacyredirect.com",
    "https://invidious.dhusch.de",
    "https://invidious.jing.rocks",
    "https://invidious.nerdvpn.de",
    "https://yewtu.be",
    "https://invidious.f5.si",
]

STATIC_PIPED = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://api.piped.yt",
    "https://pipedapi.in.projectsegfau.lt",
    "https://pipedapi.leptons.xyz",
    "https://pipedapi.nosebs.ru",
]

_instance_cache = {"time": 0, "invidious": [], "piped": []}
INSTANCE_CACHE_TTL = 3600


def _request_json(url, method="GET", json_body=None, timeout=22):
  proxies = {}
  proxy = os.environ.get("YOUTUBE_PROXY", "").strip() or os.environ.get("HTTPS_PROXY", "").strip()
  if proxy:
    proxies = {"http": proxy, "https": proxy}
  headers = {"User-Agent": UA, "Accept": "application/json"}
  for verify in (certifi.where(), False):
    try:
      if method == "POST":
        response = requests.post(
          url,
          json=json_body,
          headers=headers,
          timeout=timeout,
          verify=verify,
          proxies=proxies or None,
        )
      else:
        response = requests.get(
          url,
          headers=headers,
          timeout=timeout,
          verify=verify,
          proxies=proxies or None,
        )
      if response.status_code == 200:
        return response.json()
    except requests.exceptions.SSLError:
      if verify is False:
        return None
      continue
    except Exception:
      return None
  return None


def extract_video_id(url):
  parsed = urlparse(url)
  host = parsed.netloc.lower().replace("www.", "")
  if "youtu.be" in host:
    video_id = parsed.path.strip("/").split("/")[0]
    return video_id or None
  if "youtube.com" not in host:
    return None
  if parsed.path.startswith("/shorts/"):
    parts = parsed.path.split("/")
    return parts[2] if len(parts) > 2 else None
  query = parse_qs(parsed.query)
  if query.get("v"):
    return query["v"][0]
  match = re.search(r"/(?:embed|v|live)/([^/?#]+)", parsed.path)
  return match.group(1) if match else None


def discover_invidious_instances():
  now = time.time()
  if _instance_cache["invidious"] and now - _instance_cache["time"] < INSTANCE_CACHE_TTL:
    return _instance_cache["invidious"]
  discovered = []
  payload = _request_json("https://api.invidious.io/instances.json?sort_by=health", timeout=18)
  if isinstance(payload, list):
    for item in payload:
      if not isinstance(item, dict):
        continue
      uri = (item.get("uri") or "").rstrip("/")
      if not uri.startswith("http"):
        continue
      health = item.get("health") or {}
      ratio = health.get("ratio")
      if ratio is not None and ratio < 0.4:
        continue
      discovered.append(uri)
  merged = list(dict.fromkeys(discovered + STATIC_INVIDIOUS + _env_list("INVIDIOUS_API_URLS")))
  _instance_cache["invidious"] = merged[:40]
  _instance_cache["time"] = now
  return _instance_cache["invidious"]


def discover_piped_instances():
  now = time.time()
  if _instance_cache["piped"] and now - _instance_cache["time"] < INSTANCE_CACHE_TTL:
    return _instance_cache["piped"]
  discovered = []
  payload = _request_json("https://piped-instances.kavin.rocks/", timeout=18)
  if isinstance(payload, list):
    for item in payload:
      if not isinstance(item, dict):
        continue
      api = (item.get("api") or item.get("api_url") or "").rstrip("/")
      if api.startswith("http"):
        discovered.append(api)
  merged = list(dict.fromkeys(discovered + STATIC_PIPED + _env_list("PIPED_API_URLS")))
  _instance_cache["piped"] = merged[:30]
  _instance_cache["time"] = now
  return _instance_cache["piped"]


def _env_list(name):
  return [item.strip().rstrip("/") for item in os.environ.get(name, "").split(",") if item.strip()]


def parse_quality_height(quality_label):
  if not quality_label:
    return 0
  match = re.search(r"(\d+)", str(quality_label))
  return int(match.group(1)) if match else 0


def _try_invidious(base, video_id):
  data = _request_json(f"{base.rstrip('/')}/api/v1/videos/{video_id}", timeout=20)
  if data and (data.get("formatStreams") or data.get("adaptiveFormats")):
    data["_resolver"] = "invidious"
    data["_resolver_base"] = base
    return data
  return None


def _try_piped(base, video_id):
  data = _request_json(f"{base.rstrip('/')}/streams/{video_id}", timeout=20)
  if data and (data.get("videoStreams") or data.get("audioStreams")):
    data["_resolver"] = "piped"
    data["_resolver_base"] = base
    return data
  return None


def _payload_quality_score(payload):
  if not payload:
    return (0, 0, 0)
  max_height = 0
  stream_count = 0
  for stream in payload.get("formatStreams") or []:
    stream_count += 1
    max_height = max(max_height, parse_quality_height(stream.get("quality") or stream.get("resolution")))
  for stream in payload.get("adaptiveFormats") or []:
    media_type = (stream.get("type") or "").lower()
    if media_type.startswith("audio"):
      stream_count += 1
      continue
    stream_count += 1
    max_height = max(max_height, parse_quality_height(stream.get("quality") or stream.get("resolution")))
  for stream in payload.get("videoStreams") or []:
    stream_count += 1
    max_height = max(max_height, int(stream.get("height") or 0) or parse_quality_height(stream.get("quality")))
  for stream in payload.get("audioStreams") or []:
    stream_count += 1
  return (max_height, stream_count, 1 if payload.get("_resolver") == "piped" else 0)


def _parallel_best(fetch_fn, bases, video_id, workers=16, overall_timeout=45):
  if not bases:
    return None
  bases = bases[:30]
  best = None
  best_score = (-1, -1, -1)
  with ThreadPoolExecutor(max_workers=min(workers, len(bases))) as pool:
    futures = {pool.submit(fetch_fn, base, video_id): base for base in bases}
    try:
      for future in as_completed(futures, timeout=overall_timeout):
        try:
          result = future.result()
        except Exception:
          continue
        if not result:
          continue
        score = _payload_quality_score(result)
        if score > best_score:
          best = result
          best_score = score
    except Exception:
      pass
  return best


def fetch_invidious(video_id):
  return _parallel_best(_try_invidious, discover_invidious_instances(), video_id)


def fetch_piped(video_id):
  return _parallel_best(_try_piped, discover_piped_instances(), video_id)


def fetch_oembed(url):
  data = _request_json(f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json", timeout=15)
  if isinstance(data, dict) and data.get("title"):
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
  proxies = {}
  proxy = os.environ.get("YOUTUBE_PROXY", "").strip()
  if proxy:
    proxies = {"http": proxy, "https": proxy}
  payload = {"url": url, "downloadMode": "auto", "videoQuality": "1080"}
  data = None
  for verify in (certifi.where(), False):
    try:
      response = requests.post(
        endpoint,
        json=payload,
        headers=headers,
        timeout=90,
        verify=verify,
        proxies=proxies or None,
      )
      response.raise_for_status()
      data = response.json()
      break
    except requests.exceptions.SSLError:
      if verify is False:
        return None
      continue
    except Exception:
      return None
  if not data:
    return None
  if data.get("status") == "redirect" and data.get("url"):
    return {"_resolver": "cobalt", "title": "YouTube video", "muxed_url": data["url"], "height": 1080}
  if data.get("status") == "picker":
    for item in data.get("picker") or []:
      if item.get("type") == "video" and item.get("url"):
        return {"_resolver": "cobalt", "title": "YouTube video", "muxed_url": item["url"], "height": 1080}
  return None


def minimal_youtube_info(url, video_id):
  oembed = fetch_oembed(url)
  title = (oembed or {}).get("title") or "YouTube video"
  thumb = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
  if oembed and oembed.get("thumbnail_url"):
    thumb = oembed["thumbnail_url"]
  return {
    "id": video_id,
    "title": title,
    "thumbnail": thumb,
    "duration": None,
    "formats": [],
    "width": None,
    "height": 720,
    "webpage_url": url,
    "extractor": "youtube_resolver:oembed",
    "_ytdlp_only": True,
  }


def invidious_to_formats(data):
  formats = []
  for index, stream in enumerate(data.get("formatStreams") or []):
    media_url = stream.get("url")
    if not media_url:
      continue
    height = parse_quality_height(stream.get("quality") or stream.get("resolution"))
    bitrate = stream.get("bitrate") or stream.get("qualityLabel") or 0
    formats.append(
      {
        "format_id": f"inv-mux-{index}",
        "url": media_url,
        "ext": "mp4",
        "height": height or 720,
        "vcodec": "avc1",
        "acodec": "aac",
        "protocol": "https",
        "tbr": bitrate if isinstance(bitrate, (int, float)) else 0,
        "filesize": stream.get("size") or stream.get("clen"),
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
        "tbr": stream.get("bitrate") or 0,
        "filesize": stream.get("size") or stream.get("clen"),
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
        "vcodec": stream.get("codec") or "avc1",
        "acodec": "none" if video_only else "aac",
        "protocol": "https",
        "tbr": stream.get("bitrate") or 0,
        "filesize": stream.get("contentLength") or stream.get("size"),
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
    return {
      "id": video_id,
      "title": payload.get("title") or "YouTube video",
      "thumbnail": thumb,
      "duration": int(payload.get("duration") or 0) or None,
      "formats": formats,
      "height": max([int(f.get("height") or 0) for f in formats] + [720]),
      "webpage_url": url,
      "extractor": "youtube_resolver:piped",
    }

  formats = invidious_to_formats(payload)
  thumbs = payload.get("videoThumbnails") or []
  thumb = thumbs[-1].get("url") if thumbs else f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
  return {
    "id": video_id,
    "title": payload.get("title") or "YouTube video",
    "thumbnail": thumb,
    "duration": int(payload.get("lengthSeconds") or 0) or None,
    "formats": formats,
    "height": max([int(f.get("height") or 0) for f in formats] + [720]),
    "webpage_url": url,
    "extractor": "youtube_resolver:invidious",
  }


def fetch_youtube_info(url, require_formats=False):
  """Try many APIs in parallel; oEmbed thumbnail/title always available as last resort."""
  video_id = extract_video_id(url)
  if not video_id:
    raise ValueError("Invalid YouTube URL")

  best_partial = None
  with ThreadPoolExecutor(max_workers=3) as pool:
    inv_future = pool.submit(fetch_invidious, video_id)
    pip_future = pool.submit(fetch_piped, video_id)
    cob_future = pool.submit(fetch_cobalt, url)
    for future in (inv_future, pip_future, cob_future):
      try:
        payload = future.result(timeout=50)
        if payload:
          info = resolver_payload_to_info(payload, url, video_id)
          if info.get("formats"):
            return info
          if not require_formats:
            return info
          if not best_partial:
            best_partial = info
      except Exception:
        continue

  if best_partial:
    return best_partial

  if require_formats:
    raise ValueError(
      "External APIs are busy. Server will retry with built-in yt-dlp + PO token. Try again in 30 seconds."
    )
  return minimal_youtube_info(url, video_id)
