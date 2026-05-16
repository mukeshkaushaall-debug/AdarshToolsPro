"""Shared helpers for choosing preview streams with audio when available."""


def format_has_audio(item):
    return bool(item and item.get("acodec") and item.get("acodec") != "none")


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
