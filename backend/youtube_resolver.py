"""YouTube metadata/download without account cookies — parallel APIs + oEmbed safety net."""
import os
import re
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, quote, urlparse

import certifi
import requests

# Multiple user agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
]

def get_random_user_agent():
    """Get a random user agent from the pool."""
    return random.choice(USER_AGENTS)

def get_random_headers():
    """Generate random headers to mimic different browsers."""
    return {
        "User-Agent": get_random_user_agent(),
        "Accept": random.choice([
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        ]),
        "Accept-Language": random.choice([
            "en-US,en;q=0.9",
            "en-US,en;q=0.9,hi;q=0.8",
            "en-GB,en;q=0.9",
            "en-IN,en;q=0.9,hi;q=0.8",
        ]),
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": random.choice(["1", "0"]),
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": random.choice(["document", "empty"]),
        "Sec-Fetch-Mode": random.choice(["navigate", "cors"]),
        "Sec-Fetch-Site": random.choice(["none", "same-origin", "cross-site"]),
        "Cache-Control": random.choice(["max-age=0", "no-cache"]),
    }

UA = USER_AGENTS[0]

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
    "https://inv.riverside.rocks",
    "https://invidious.snopyta.org",
    "https://invidious.kavin.rocks",
    "https://invidious.048596.xyz",
    "https://invidious.namazso.eu",
    "https://inv.bp.projectsegfau.lt",
    "https://invidious.projectsegfau.lt",
    "https://inv.mint.lgbt",
    "https://invidious.esmailelbob.xyz",
    "https://invidious.zee.li",
    "https://invidious.tiekoetter.com",
    "https://invidious.flokinet.is",
    "https://invidious.perennialte.ch",
    "https://invidious.namazso.eu",
    "https://invidious.himiko.cloud",
    "https://invidious.slipfox.xyz",
    "https://invidious.silkky.cloud",
    "https://invidious.tinfoil-hat.net",
    "https://invidious.garudalinux.org",
    "https://invidious.lunar.icu",
    "https://invidious.catgirl.life",
    "https://invidious.baczek.me",
    "https://invidious.weblibre.org",
    "https://invidious.blamefran.net",
    "https://invidious.nerdvpn.de",
    "https://invidious.jing.rocks",
    "https://invidious.dhusch.de",
    "https://invidious.privacyredirect.com",
    "https://invidious.private.coffee",
    "https://yt.artemislena.eu",
    "https://invidious.fdn.fr",
    "https://vid.puffyan.us",
    "https://inv.nadeko.net",
    "https://invidious.io",
]

STATIC_PIPED = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://api.piped.yt",
    "https://pipedapi.in.projectsegfau.lt",
    "https://pipedapi.leptons.xyz",
    "https://pipedapi.nosebs.ru",
    "https://pipedapi.garudalinux.org",
    "https://pipedapi.projectsegfau.lt",
    "https://pipedapi.mint.lgbt",
    "https://pipedapi.esmailelbob.xyz",
    "https://pipedapi.zee.li",
    "https://pipedapi.tiekoetter.com",
    "https://pipedapi.flokinet.is",
    "https://pipedapi.perennialte.ch",
    "https://pipedapi.namazso.eu",
    "https://pipedapi.himiko.cloud",
    "https://pipedapi.slipfox.xyz",
    "https://pipedapi.silkky.cloud",
    "https://pipedapi.tinfoil-hat.net",
    "https://pipedapi.catgirl.life",
    "https://pipedapi.baczek.me",
    "https://pipedapi.weblibre.org",
    "https://pipedapi.blamefran.net",
    "https://pipedapi.nerdvpn.de",
    "https://pipedapi.jing.rocks",
    "https://pipedapi.dhusch.de",
    "https://pipedapi.privacyredirect.com",
    "https://pipedapi.private.coffee",
]

_instance_cache = {"time": 0, "invidious": [], "piped": []}
INSTANCE_CACHE_TTL = 3600

# Circuit breaker - track failed instances
_failed_instances = {"invidious": {}, "piped": {}, "cobalt": {}}
_failed_instance_ttl = 300  # 5 minutes cooldown for failed instances

# Proxy rotation support
PROXY_LIST = []
if os.environ.get("PROXY_LIST"):
    PROXY_LIST = [p.strip() for p in os.environ.get("PROXY_LIST").split(",") if p.strip()]

def get_random_proxy():
    """Get a random proxy from the list if available."""
    if PROXY_LIST:
        return random.choice(PROXY_LIST)
    return None

def mark_instance_failed(instance_type, instance_url):
    """Mark an instance as failed temporarily."""
    _failed_instances[instance_type][instance_url] = time.time()

def mark_instance_success(instance_type, instance_url):
    """Clear failure state after a successful response."""
    _failed_instances[instance_type].pop(instance_url, None)

def is_instance_failed(instance_type, instance_url):
    """Check if an instance is marked as failed."""
    failed_at = _failed_instances[instance_type].get(instance_url)
    if not failed_at:
        return False
    if time.time() - failed_at > _failed_instance_ttl:
        _failed_instances[instance_type].pop(instance_url, None)
        return False
    return True


def _request_json(url, method="GET", json_body=None, timeout=22):
  # Add random delay to avoid rate limiting
  time.sleep(random.uniform(0.1, 0.8))
  
  proxies = {}
  # Try random proxy from list first, then fall back to env proxy
  random_proxy = get_random_proxy()
  if random_proxy:
    proxies = {"http": random_proxy, "https": random_proxy}
  else:
    proxy = os.environ.get("YOUTUBE_PROXY", "").strip() or os.environ.get("HTTPS_PROXY", "").strip()
    if proxy:
      proxies = {"http": proxy, "https": proxy}
  
  # Use random headers for each request
  headers = get_random_headers()
  headers["Accept"] = "application/json"
  
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
      if ratio is not None and ratio < 0.3:  # Lowered threshold for more instances
        continue
      discovered.append(uri)
  merged = list(dict.fromkeys(discovered + STATIC_INVIDIOUS + _env_list("INVIDIOUS_API_URLS")))
  # Shuffle to randomize order
  random.shuffle(merged)
  _instance_cache["invidious"] = merged[:60]  # Increased from 40 to 60
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
  # Shuffle to randomize order
  random.shuffle(merged)
  _instance_cache["piped"] = merged[:50]  # Increased from 30 to 50
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
  if is_instance_failed("invidious", base):
    return None
  data = _request_json(f"{base.rstrip('/')}/api/v1/videos/{video_id}", timeout=20)
  if data and (data.get("formatStreams") or data.get("adaptiveFormats")):
    data["_resolver"] = "invidious"
    data["_resolver_base"] = base
    mark_instance_success("invidious", base)
    return data
  # Mark as failed if no data
  mark_instance_failed("invidious", base)
  return None


def _try_piped(base, video_id):
  if is_instance_failed("piped", base):
    return None
  data = _request_json(f"{base.rstrip('/')}/streams/{video_id}", timeout=20)
  if data and (data.get("videoStreams") or data.get("audioStreams")):
    data["_resolver"] = "piped"
    data["_resolver_base"] = base
    mark_instance_success("piped", base)
    return data
  # Mark as failed if no data
  mark_instance_failed("piped", base)
  return None


def _parallel_first(fetch_fn, bases, video_id, workers=32, overall_timeout=60):
  if not bases:
    return None
  bases = bases[:50]  # Increased from 30 to 50
  pool = ThreadPoolExecutor(max_workers=min(workers, len(bases)))
  futures = {pool.submit(fetch_fn, base, video_id): base for base in bases}
  try:
    for future in as_completed(futures, timeout=overall_timeout):
      try:
        result = future.result()
        if result:
          return result
      except Exception:
        continue
  except Exception:
    pass
  finally:
    for future in futures:
      future.cancel()
    pool.shutdown(wait=False, cancel_futures=True)
  return None


def fetch_invidious(video_id):
  return _parallel_first(_try_invidious, discover_invidious_instances(), video_id)


def fetch_piped(video_id):
  return _parallel_first(_try_piped, discover_piped_instances(), video_id)


def fetch_oembed(url):
  data = _request_json(f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json", timeout=15)
  if isinstance(data, dict) and data.get("title"):
    return data
  return None


def cobalt_quality(quality):
  value = str(quality or "1080").lower()
  if value == "best":
    return "max"
  match = re.search(r"\d+", value)
  if not match:
    return "1080"
  return str(max(144, min(4320, int(match.group(0)))))


def cobalt_bases():
  bases = []
  primary = os.environ.get("COBALT_API_URL", "").strip().rstrip("/")
  if primary:
    bases.append(primary)
  additional = os.environ.get("COBALT_API_URLS", "").strip()
  if additional:
    bases.extend([base.strip().rstrip("/") for base in additional.split(",") if base.strip()])
  return list(dict.fromkeys(bases))


def cobalt_auth_header():
  explicit = os.environ.get("COBALT_AUTHORIZATION", "").strip()
  if explicit:
    return explicit
  api_key = os.environ.get("COBALT_API_KEY", "").strip()
  if api_key:
    return f"Api-Key {api_key}"
  return ""


def cobalt_endpoints(base):
  base = base.rstrip("/")
  if base.endswith("/api/json"):
    return [base]
  return [base, f"{base}/api/json"]


def cobalt_url_from_response(data):
  status = data.get("status")
  if status in {"redirect", "tunnel"} and data.get("url"):
    return data["url"]
  if status == "picker":
    for item in data.get("picker") or []:
      if item.get("type") == "video" and item.get("url"):
        return item["url"]
  if status == "local-processing":
    tunnels = data.get("tunnel") or []
    if len(tunnels) == 1:
      item = tunnels[0]
      if isinstance(item, dict):
        return item.get("url") or ""
      return item
  return ""


def fetch_cobalt(url, quality="1080"):
  # Add random delay
  time.sleep(random.uniform(0.2, 0.6))

  bases = cobalt_bases()
  if not bases:
    return None

  # Shuffle for randomization
  random.shuffle(bases)

  for base in bases[:5]:  # Try up to 5 configured instances
    if is_instance_failed("cobalt", base):
      continue
    headers = get_random_headers()
    headers["Accept"] = "application/json"
    headers["Content-Type"] = "application/json"
    authorization = cobalt_auth_header()
    if authorization:
      headers["Authorization"] = authorization
    
    proxies = {}
    random_proxy = get_random_proxy()
    if random_proxy:
      proxies = {"http": random_proxy, "https": random_proxy}
    else:
      proxy = os.environ.get("YOUTUBE_PROXY", "").strip()
      if proxy:
        proxies = {"http": proxy, "https": proxy}
    
    payload = {
      "url": url,
      "downloadMode": "auto",
      "filenameStyle": "basic",
      "videoQuality": cobalt_quality(quality),
      "youtubeVideoCodec": "h264",
      "youtubeVideoContainer": "mp4",
      "localProcessing": "disabled",
    }
    for endpoint in cobalt_endpoints(base):
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
            continue
          continue
        except Exception:
          continue

      if data:
        media_url = cobalt_url_from_response(data)
        if media_url:
          mark_instance_success("cobalt", base)
          return {
            "_resolver": "cobalt",
            "title": "YouTube video",
            "muxed_url": media_url,
            "height": 1080 if cobalt_quality(quality) == "max" else int(cobalt_quality(quality)),
          }
    mark_instance_failed("cobalt", base)
  
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
    formats.append(
      {
        "format_id": f"inv-mux-{index}",
        "url": media_url,
        "ext": "mp4",
        "height": height or 720,
        "vcodec": "avc1",
        "acodec": "aac",
        "protocol": "https",
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


def requested_height_for_quality(quality):
  value = str(quality or "best").lower()
  if value == "best":
    return 0
  match = re.search(r"\d+", value)
  return max(144, min(4320, int(match.group(0)))) if match else 0


def info_formats_height(info):
  heights = [
    int(item.get("height") or 0)
    for item in info.get("formats") or []
    if int(item.get("height") or 0) > 0
  ]
  return max(heights or [int(info.get("height") or 0) or 0])


def info_audio_ready(info):
  formats = info.get("formats") or []
  has_muxed = any(
    item.get("vcodec") and item.get("vcodec") != "none" and item.get("acodec") and item.get("acodec") != "none"
    for item in formats
  )
  has_video = any(item.get("vcodec") and item.get("vcodec") != "none" for item in formats)
  has_audio = any(item.get("acodec") and item.get("acodec") != "none" for item in formats)
  return has_muxed or (has_video and has_audio)


def info_quality_score(info, quality):
  requested = requested_height_for_quality(quality)
  height = info_formats_height(info)
  resolver = str(info.get("extractor") or "")
  resolver_bonus = 30 if "cobalt" in resolver else 20 if "piped" in resolver else 10 if "invidious" in resolver else 0
  audio_bonus = 100 if info_audio_ready(info) else 0
  if requested:
    height_score = height if height <= requested else requested - (height - requested) * 0.2
  else:
    height_score = height
  return height_score + audio_bonus + resolver_bonus


def fetch_youtube_info(url, require_formats=False, quality="1080"):
  """Try many APIs in parallel; oEmbed thumbnail/title always available as last resort."""
  video_id = extract_video_id(url)
  if not video_id:
    raise ValueError("Invalid YouTube URL")

  best_info = None
  best_partial = None
  pool = ThreadPoolExecutor(max_workers=3)
  futures = [
    pool.submit(fetch_invidious, video_id),
    pool.submit(fetch_piped, video_id),
    pool.submit(fetch_cobalt, url, quality),
  ]
  try:
    for future in as_completed(futures, timeout=65):
      try:
        payload = future.result()
        if not payload:
          continue
        info = resolver_payload_to_info(payload, url, video_id)
        if info.get("formats"):
          if not best_info or info_quality_score(info, quality) > info_quality_score(best_info, quality):
            best_info = info
          continue
        if not require_formats and not best_partial:
          best_partial = info
      except Exception:
        continue
  except Exception:
    pass
  finally:
    for future in futures:
      future.cancel()
    pool.shutdown(wait=False, cancel_futures=True)

  if best_info:
    return best_info

  if best_partial:
    return best_partial

  if require_formats:
    raise ValueError(
      "No-cookie YouTube resolvers are busy. Try again, redeploy in a new region, or set COBALT_API_URL to your self-hosted Cobalt relay."
    )
  return minimal_youtube_info(url, video_id)
