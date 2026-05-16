"""Shared helpers for choosing preview streams with audio when available."""


def format_number(value, default=0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def format_has_audio(item):
    return bool(item and item.get("acodec") and item.get("acodec") != "none")


def is_direct_http_format(item):
    media_url = item.get("url") or ""
    if not media_url.startswith("http"):
        return False
    protocol = (item.get("protocol") or "https").lower()
    return not protocol or "http" in protocol


def video_format_score(item):
    return (
        format_number(item.get("height")),
        format_number(item.get("fps")),
        format_number(item.get("tbr")),
        format_number(item.get("vbr")),
        format_number(item.get("filesize") or item.get("filesize_approx")),
    )


def audio_format_score(item):
    return (
        format_number(item.get("abr")),
        format_number(item.get("tbr")),
        format_number(item.get("filesize") or item.get("filesize_approx")),
    )


def pick_preview_stream_pair(info, max_height=720):
    """Pick video (+ separate audio) streams suitable for a muxed preview."""
    formats = info.get("formats") or []
    videos = [
        item
        for item in formats
        if item.get("url")
        and item.get("vcodec")
        and item.get("vcodec") != "none"
        and format_number(item.get("height")) > 0
        and is_direct_http_format(item)
    ]
    audios = [
        item
        for item in formats
        if item.get("url")
        and format_has_audio(item)
        and (not item.get("vcodec") or item.get("vcodec") == "none")
        and is_direct_http_format(item)
    ]
    progressive = [item for item in videos if format_has_audio(item)]

    def pool_at_height(items):
        if not items:
            return []
        if max_height:
            limited = [item for item in items if format_number(item.get("height")) <= max_height]
            return limited or items
        return items

    progressive_pool = pool_at_height(progressive)
    if progressive_pool:
        return max(progressive_pool, key=video_format_score), None

    video_pool = pool_at_height(videos)
    if not video_pool:
        return None, None
    video = max(video_pool, key=video_format_score)
    if format_has_audio(video):
        return video, None
    audio = max(audios, key=audio_format_score, default=None) if audios else None
    return video, audio


def pick_preview_video_url(formats):
    """Prefer muxed (video+audio) streams for in-page preview."""
    candidates = []
    for item in formats or []:
        preview_url = item.get("url")
        if not preview_url:
            continue
        vcodec = item.get("vcodec")
        if not vcodec or vcodec == "none":
            continue
        protocol = item.get("protocol") or ""
        if protocol and not any(part in protocol for part in ("http", "https")):
            continue
        ext = (item.get("ext") or "").lower()
        if ext not in {"mp4", "webm", "m4v", ""}:
            continue
        height = int(item.get("height") or 0)
        has_audio = format_has_audio(item)
        # Prefer audio, then closest to 720p for faster preview, then higher quality.
        candidates.append((0 if has_audio else 1, abs(height - 720) if height else 9999, -height, preview_url))
    candidates.sort()
    return candidates[0][-1] if candidates else ""
