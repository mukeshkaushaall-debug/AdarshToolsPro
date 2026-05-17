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
_failed_instances = {"invidious": {}, "piped": {}}
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
    return data
  # Mark as failed if no data
  mark_instance_failed("piped", base)
  return None


def _parallel_first(fetch_fn, bases, video_id, workers=32, overall_timeout=60):
  if not bases:
    return None
  bases = bases[:50]  # Increased from 30 to 50
  with ThreadPoolExecutor(max_workers=min(workers, len(bases))) as pool:
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


def fetch_cobalt(url):
  # Add random delay
  time.sleep(random.uniform(0.2, 0.6))
  
  # Try multiple Cobalt instances if configured
  cobalt_bases = []
  base = os.environ.get("COBALT_API_URL", "").strip().rstrip("/")
  if base:
    cobalt_bases.append(base)
  
  # Add additional Cobalt instances from env
  additional = os.environ.get("COBALT_API_URLS", "").strip()
  if additional:
    cobalt_bases.extend([b.strip().rstrip("/") for b in additional.split(",") if b.strip()])
  
  # Default Cobalt instances
  if not cobalt_bases:
    cobalt_bases = [
      "https://cobalt-api.kwiatekmiki.pl",
      "https://cobalt-api.owo.si",
      "https://cobalt-api.hope.so",
    ]
  
  # Shuffle for randomization
  random.shuffle(cobalt_bases)
  
  for base in cobalt_bases[:5]:  # Try up to 5 instances
    endpoint = base if base.endswith("/api/json") else f"{base}/api/json"
    headers = get_random_headers()
    headers["Accept"] = "application/json"
    headers["Content-Type"] = "application/json"
    api_key = os.environ.get("COBALT_API_KEY", "").strip()
    if api_key:
      headers["Authorization"] = f"Api-Key {api_key}"
    
    proxies = {}
    random_proxy = get_random_proxy()
    if random_proxy:
      proxies = {"http": random_proxy, "https": random_proxy}
    else:
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
          continue
        continue
      except Exception:
        continue
    
    if data:
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


def fetch_youtube_info(url, require_formats=False):
  """Try many APIs in parallel; oEmbed thumbnail/title always available as last resort."""
  video_id = extract_video_id(url)
  if not video_id:
    raise ValueError("Invalid YouTube URL")

  best_partial = None
  with ThreadPoolExecutor(max_workers=3) as pool:
    futures = [
      pool.submit(fetch_invidious, video_id),
      pool.submit(fetch_piped, video_id),
      pool.submit(fetch_cobalt, url),
    ]
    try:
      for future in as_completed(futures, timeout=65):
        try:
          payload = future.result()
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
    except Exception:
      pass

  if best_partial:
    return best_partial

  if require_formats:
    raise ValueError(
      "External APIs are busy. Server will retry with built-in yt-dlp + PO token. Try again in 30 seconds."
    )
  return minimal_youtube_info(url, video_id)
