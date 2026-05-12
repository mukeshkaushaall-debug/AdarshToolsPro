import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import importlib
import importlib.util
import io
import zipfile
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
import certifi
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "uploads"
DOWNLOAD_DIR = BASE_DIR / "downloads"
VENDOR_DIR = BASE_DIR / "vendor"

if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

try:
    from rembg import remove as remove_background
except Exception:
    remove_background = None

try:
    qrcode = importlib.import_module("qrcode")
except Exception:
    qrcode = None

_pymupdf_error = ""
try:
    vendor_path = str(VENDOR_DIR)
    removed_vendor_path = False
    if vendor_path in sys.path:
        sys.path.remove(vendor_path)
        removed_vendor_path = True
    pymupdf = importlib.import_module("pymupdf")
    if not hasattr(pymupdf, "open"):
        raise ImportError(f"loaded pymupdf has no open(): {getattr(pymupdf, '__file__', None)}")
except Exception as error:
    _pymupdf_error = str(error)
    try:
        pymupdf_init = VENDOR_DIR / "pymupdf" / "__init__.py"
        if not pymupdf_init.exists():
            raise ImportError("local vendor/pymupdf is missing")
        spec = importlib.util.spec_from_file_location("pymupdf", pymupdf_init, submodule_search_locations=[str(pymupdf_init.parent)])
        pymupdf = importlib.util.module_from_spec(spec)
        sys.modules["pymupdf"] = pymupdf
        spec.loader.exec_module(pymupdf)
    except Exception as fallback_error:
        try:
            pymupdf = importlib.import_module("fitz")
        except Exception as fitz_error:
            _pymupdf_error = f"{_pymupdf_error}; {fallback_error}; {fitz_error}"
            pymupdf = None
finally:
    if VENDOR_DIR.exists() and str(VENDOR_DIR) not in sys.path:
        sys.path.insert(0, str(VENDOR_DIR))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp"}
ALLOWED_PDF_EXT = {"pdf"}
ALLOWED_VIDEO_EXT = {"mp4", "mov", "mkv", "webm", "avi", "m4v"}
MAX_CONTENT_LENGTH = 250 * 1024 * 1024
UPLOAD_TTL_SECONDS = 10 * 60
DOWNLOAD_TTL_SECONDS = 10 * 60
DELETE_AFTER_DOWNLOAD_SECONDS = 30
MAX_UPSCALE_PIXELS = 120_000_000
CLEANUP_INTERVAL_SECONDS = 60
_last_cleanup_at = 0
FONT_DIR = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
CORS(app)


class ApiError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class QuietYtdlpLogger:
    def debug(self, _message):
        pass

    def warning(self, _message):
        pass

    def error(self, _message):
        pass


@app.errorhandler(ApiError)
def handle_api_error(error):
    return jsonify({"success": False, "error": error.message}), error.status_code


@app.errorhandler(413)
def handle_too_large(_):
    return jsonify({"success": False, "error": "File is too large. Max upload size is 250 MB."}), 413


@app.errorhandler(DownloadError)
def handle_download_error(error):
    return jsonify({"success": False, "error": simplify_download_error(str(error))}), 400


@app.errorhandler(HTTPException)
def handle_http_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": error.description}), error.code
    return error


@app.errorhandler(Exception)
def handle_unexpected(error):
    app.logger.exception(error)
    return jsonify({"success": False, "error": f"Server error: {str(error)[:180]}"}), 500


def make_id():
    return uuid.uuid4().hex


def public_download_url(filename):
    return f"/download/{filename}"


def delete_quietly(path):
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass


def delete_later(path, delay=8):
    timer = threading.Timer(delay, delete_quietly, args=[path])
    timer.daemon = True
    timer.start()


def cleanup_old_files(folder, max_age_seconds=3600):
    now = __import__("time").time()
    for path in Path(folder).glob("*"):
        try:
            if path.is_file() and now - path.stat().st_mtime > max_age_seconds:
                path.unlink()
        except Exception:
            pass


def cleanup_temp_storage():
    global _last_cleanup_at
    now = time.time()
    if now - _last_cleanup_at < CLEANUP_INTERVAL_SECONDS:
        return
    _last_cleanup_at = now
    cleanup_old_files(UPLOAD_DIR, UPLOAD_TTL_SECONDS)
    cleanup_old_files(DOWNLOAD_DIR, DOWNLOAD_TTL_SECONDS)


def simplify_download_error(message):
    msg = re.sub(r"\s+", " ", message or "").strip()
    lowered = msg.lower()
    if "sign in to confirm" in lowered or "login" in lowered or "private" in lowered:
        return "This video needs login or is private. Try a public link."
    if "certificate_verify_failed" in lowered or "certificate verify failed" in lowered or "ssl" in lowered:
        return "SSL certificate problem fixed in backend. Restart server and try again. If it repeats, check system date/time or internet SSL filter."
    if "ffmpeg" in lowered:
        return "FFmpeg is required for HD merge or MP3. Install it with: winget install Gyan.FFmpeg"
    if "unsupported url" in lowered:
        return "This site/link is not supported. Try a public YouTube, Instagram, or Pinterest URL."
    if "copyright" in lowered or "unavailable" in lowered:
        return "This media is unavailable from the source site."
    if "requested format is not available" in lowered:
        return "Requested quality is not available. Try 720p or 480p."
    return msg.replace("ERROR:", "").strip()[:220] or "Could not download this media. Try another public link."


def ytdlp_base_opts():
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": QuietYtdlpLogger(),
        "noplaylist": True,
        "cachedir": False,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "nocheckcertificate": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }


def extract_info_safe(url, download=False, extra_opts=None):
    opts = {**ytdlp_base_opts(), **(extra_opts or {})}
    try:
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=download), ydl
    except Exception as error:
        raise ApiError(simplify_download_error(str(error)), 400) from error


def fetch_url_bytes(url, timeout=20):
    try:
        response = requests.get(url, timeout=timeout, verify=certifi.where())
    except requests.exceptions.SSLError:
        response = requests.get(url, timeout=timeout, verify=False)
    response.raise_for_status()
    return response.content


def fetch_url_text(url, timeout=20):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        response = requests.get(url, timeout=timeout, verify=certifi.where(), headers=headers)
    except requests.exceptions.SSLError:
        response = requests.get(url, timeout=timeout, verify=False, headers=headers)
    response.raise_for_status()
    return response.text


def extract_meta_value(html, *names):
    for name in names:
        patterns = [
            rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(name)}["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(name)}["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return unescape(match.group(1).strip())
    return ""


def social_preview_fallback(url, reason=""):
    parsed = urlparse(url)
    host = parsed.netloc.replace("www.", "")
    title = f"{host.title()} media preview"
    thumbnail = ""
    embed_url = ""
    shortcode_match = re.search(r"/(?:p|reel|tv)/([^/?#]+)/?", parsed.path)
    if "instagram" in host and shortcode_match:
        media_type = "reel" if "/reel/" in parsed.path else "p"
        embed_url = f"https://www.instagram.com/{media_type}/{shortcode_match.group(1)}/embed"
    try:
        html = fetch_url_text(url)
        title = extract_meta_value(html, "og:title", "twitter:title") or title
        thumbnail = extract_meta_value(html, "og:image", "twitter:image") or ""
    except Exception:
        pass
    return {
        "success": True,
        "title": title,
        "uploader": host or "Public source",
        "duration": None,
        "duration_text": "",
        "thumbnail": thumbnail,
        "width": None,
        "height": None,
        "aspect_ratio": 1.0 if "instagram" in host else 16 / 9,
        "webpage_url": url,
        "embed_url": embed_url,
        "preview_note": "Instagram preview is shown through an embed when direct thumbnail metadata is blocked." if embed_url else (reason or "Limited preview. The site may require login or block metadata."),
    }


def clean_url(value):
    value = (value or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ApiError("Please enter a valid public URL.")
    return value


def safe_file_from_upload(file_storage, kind="image"):
    if not file_storage or not file_storage.filename:
        raise ApiError("Please upload a file.")
    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if kind == "image" and ext not in ALLOWED_IMAGE_EXT:
        raise ApiError("Only JPG, PNG, and WEBP images are supported.")
    if kind == "pdf" and ext not in ALLOWED_PDF_EXT:
        raise ApiError("Only PDF files are supported.")
    if kind == "video" and ext not in ALLOWED_VIDEO_EXT:
        raise ApiError("Only MP4, MOV, MKV, WEBM, AVI, and M4V videos are supported.")
    saved_name = f"{make_id()}_{filename}"
    target = UPLOAD_DIR / saved_name
    file_storage.save(target)
    return target


def image_response(path, label="Download image"):
    return {
        "success": True,
        "filename": path.name,
        "download_url": public_download_url(path.name),
        "download_label": label,
    }


def file_response(path, label="Download"):
    return {
        "success": True,
        "filename": path.name,
        "download_url": public_download_url(path.name),
        "download_label": label,
    }


def safe_download_path(filename):
    requested = Path(unquote(filename)).name
    file_path = (DOWNLOAD_DIR / requested).resolve()
    if DOWNLOAD_DIR.resolve() not in file_path.parents or not file_path.exists():
        raise ApiError("File not found or expired.", 404)
    return file_path


def media_info(url):
    info, _ = extract_info_safe(url, download=False, extra_opts={"skip_download": True})
    thumbnail = info.get("thumbnail")
    if not thumbnail and info.get("thumbnails"):
        thumbnail = info["thumbnails"][-1].get("url")
    preview_video_url = pick_preview_video_url(info.get("formats") or [])
    duration = info.get("duration")
    width = info.get("width")
    height = info.get("height")
    aspect_ratio = round(width / height, 4) if width and height else 16 / 9
    return {
        "success": True,
        "title": info.get("title") or "Media preview",
        "uploader": info.get("uploader") or info.get("channel") or "Public source",
        "duration": duration,
        "duration_text": f"{duration // 60}:{duration % 60:02d}" if isinstance(duration, int) else "",
        "thumbnail": thumbnail,
        "preview_video_url": preview_video_url,
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "webpage_url": info.get("webpage_url") or url,
    }


def pick_preview_video_url(formats):
    candidates = []
    for item in formats:
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
        height = item.get("height") or 9999
        filesize = item.get("filesize") or item.get("filesize_approx") or 0
        acodec = item.get("acodec")
        candidates.append((height > 540, height, not acodec or acodec == "none", filesize, preview_url))
    candidates.sort()
    return candidates[0][-1] if candidates else ""


def postprocess_cutout(path, feather=2, background="transparent"):
    with Image.open(path) as img:
        rgba = img.convert("RGBA")
        if feather > 0:
            alpha = rgba.getchannel("A").filter(ImageFilter.GaussianBlur(feather))
            rgba.putalpha(alpha)
        if background != "transparent":
            colors = {
                "white": (255, 255, 255, 255),
                "black": (10, 13, 20, 255),
                "blue": (37, 99, 235, 255),
            }
            canvas = Image.new("RGBA", rgba.size, colors.get(background, (255, 255, 255, 255)))
            canvas.alpha_composite(rgba)
            rgba = canvas
        rgba.save(path, "PNG", optimize=True)


def remove_background_fallback(source, out, feather=2, background="transparent"):
    with Image.open(source) as img:
        rgba = img.convert("RGBA")
        rgb = rgba.convert("RGB")
        small = rgb.resize((1, 1), Image.Resampling.BOX)
        bg = Image.new("RGB", rgb.size, small.getpixel((0, 0)))
        diff = ImageChops.difference(rgb, bg).convert("L")
        mask = diff.point(lambda p: 255 if p > 24 else 0)
        mask = ImageOps.expand(mask, border=8, fill=0).filter(ImageFilter.GaussianBlur(5)).crop((8, 8, 8 + rgb.width, 8 + rgb.height))
        mask = mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(2))
        rgba.putalpha(mask)
        rgba.save(out, "PNG", optimize=True)
    postprocess_cutout(out, feather=feather, background=background)


def require_ffmpeg():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ApiError("FFmpeg is required for this tool. Install it with: winget install Gyan.FFmpeg", 500)
    return ffmpeg


def clamp_int(value, default, minimum, maximum):
    try:
        number = int(float(value))
    except Exception:
        number = default
    return max(minimum, min(maximum, number))


def parse_hex_color(value, default="#111827"):
    value = (value or default).strip()
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value)
    if not match:
        match = re.fullmatch(r"#?([0-9a-fA-F]{3})", value)
        if match:
            parts = [part * 2 for part in match.group(1)]
            return tuple(int(part, 16) for part in parts)
        value = default.strip("#")
    else:
        value = match.group(1)
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def load_watermark_font(font_key, font_size):
    font_files = {
        "arial": "arial.ttf",
        "arial-bold": "arialbd.ttf",
        "georgia": "georgia.ttf",
        "times": "times.ttf",
        "verdana": "verdana.ttf",
        "trebuchet": "trebuc.ttf",
    }
    candidates = [FONT_DIR / font_files.get(font_key, "arial.ttf"), FONT_DIR / "arial.ttf"]
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), font_size)
        except Exception:
            pass
    return ImageFont.load_default()


def load_invoice_font(size, bold=False):
    candidates = [
        FONT_DIR / ("arialbd.ttf" if bold else "arial.ttf"),
        FONT_DIR / ("segoeuib.ttf" if bold else "segoeui.ttf"),
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size)
        except Exception:
            pass
    return ImageFont.load_default()


def money(value):
    try:
        return f"Rs {float(value):,.2f}"
    except Exception:
        return "Rs 0.00"


def parse_invoice_items(raw_items):
    rows = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            description = (item.get("description") or "").strip()[:90]
            if not description:
                continue
            qty = float(item.get("qty") or 1)
            rate = float(item.get("rate") or 0)
            amount = float(item.get("amount") or 0) or max(0, qty) * max(0, rate)
            rows.append({"description": description, "qty": max(0, qty), "rate": max(0, rate), "amount": max(0, amount)})
        if not rows:
            raise ApiError("Add at least one invoice item.")
        return rows[:120]
    for line in (raw_items or "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if not parts or not parts[0]:
            continue
        description = parts[0][:90]
        qty = float(parts[1]) if len(parts) > 1 and parts[1] else 1
        rate = float(parts[2]) if len(parts) > 2 and parts[2] else 0
        rows.append({"description": description, "qty": max(0, qty), "rate": max(0, rate), "amount": max(0, qty) * max(0, rate)})
    if not rows:
        raise ApiError("Add at least one invoice item: Item name, quantity, price.")
    return rows[:120]


def draw_wrapped(draw, text, xy, font, fill, width, line_gap=6, max_lines=4):
    x, y = xy
    words = str(text or "").split()
    lines = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    for line in lines[:max_lines]:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + line_gap
    return y


def create_invoice_pdf(data):
    business = (data.get("business") or "Your Business").strip()[:70]
    tagline = (data.get("tagline") or "").strip()[:80]
    phone = (data.get("phone") or "").strip()[:40]
    client = (data.get("client") or "Client").strip()[:70]
    village = (data.get("village") or "").strip()[:60]
    invoice_no = (data.get("invoice_no") or "001").strip()[:40]
    invoice_date = (data.get("date") or time.strftime("%Y-%m-%d")).strip()[:20]
    business_address = (data.get("business_address") or "").strip()[:260]
    client_address = (data.get("client_address") or "").strip()[:260]
    notes = (data.get("notes") or "").strip()[:260]
    items = parse_invoice_items(data.get("items"))
    tax_percent = max(0, min(100, float(data.get("tax") or 0)))
    discount = max(0, float(data.get("discount") or 0))
    paid = max(0, float(data.get("paid") or 0))

    width, height = 1240, 1754
    ink = (17, 24, 39)
    muted = (82, 94, 115)
    line = (226, 232, 240)
    header = (15, 23, 42)
    accent = (37, 99, 235)
    surface = (248, 250, 252)
    font_h1 = load_invoice_font(64, True)
    font_h2 = load_invoice_font(29, True)
    font_h3 = load_invoice_font(24, True)
    font_body = load_invoice_font(22)
    font_bold = load_invoice_font(22, True)
    font_small = load_invoice_font(18)
    left, right = 86, width - 86
    table_left, table_right = 108, width - 108
    col = [table_left, table_left + 78, table_left + 610, table_left + 720, table_left + 905, table_right]
    rows_per_page = 18
    pages = []
    subtotal = sum(item["amount"] for item in items)
    tax = subtotal * tax_percent / 100
    total = max(0, subtotal + tax - discount)
    due = max(0, total - paid)

    def text_right(draw, xy, text, font, fill=ink):
        x, y = xy
        draw.text((x - draw.textlength(str(text), font=font), y), str(text), font=font, fill=fill)

    def centered(draw, text, box, font, fill=ink):
        bbox = draw.textbbox((0, 0), str(text), font=font)
        x = box[0] + (box[2] - box[0] - (bbox[2] - bbox[0])) / 2
        y = box[1] + (box[3] - box[1] - (bbox[3] - bbox[1])) / 2
        draw.text((x, y), str(text), font=font, fill=fill)

    def rounded_box(draw, box, radius=8, outline=line, fill=None, width_px=2):
        draw.rounded_rectangle(box, radius=radius, outline=outline, fill=fill, width=width_px)

    chunks = [items[index:index + rows_per_page] for index in range(0, len(items), rows_per_page)] or [[]]
    for page_no, chunk in enumerate(chunks, start=1):
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, width, 202), fill=surface)
        draw.rectangle((0, 0, 18, height), fill=accent)
        draw.text((left, 70), "INVOICE", font=font_h1, fill=ink)
        draw.text((width - 360, 72), invoice_no, font=font_h2, fill=accent)
        draw.text((width - 360, 116), invoice_date, font=font_body, fill=muted)
        if len(chunks) > 1:
            draw.text((width - 360, 154), f"Page {page_no} of {len(chunks)}", font=font_small, fill=muted)

        info_y = 262
        rounded_box(draw, (left, info_y, left + 510, info_y + 166), fill=(255, 255, 255), width_px=2)
        rounded_box(draw, (left + 548, info_y, right, info_y + 166), fill=(255, 255, 255), width_px=2)
        business_next_y = draw_wrapped(draw, business.upper(), (left + 22, info_y + 18), font_h3, ink, 455, line_gap=4, max_lines=2)
        if tagline:
            draw.text((left + 22, max(info_y + 58, business_next_y + 4)), tagline.upper(), font=font_bold, fill=muted)
        contact = " | ".join(part for part in [phone, business_address.replace("\n", ", ")] if part)
        draw_wrapped(draw, contact, (left + 22, info_y + 108), font_small, muted, 455, max_lines=2)
        draw.text((left + 570, info_y + 22), "BILL TO", font=font_small, fill=muted)
        draw_wrapped(draw, client.upper(), (left + 570, info_y + 56), font_h3, ink, 440, line_gap=4, max_lines=2)
        client_line = " | ".join(part for part in [village, client_address.replace("\n", ", ")] if part)
        draw_wrapped(draw, client_line, (left + 570, info_y + 92), font_small, muted, 455, max_lines=3)

        table_y = 548
        header_h = 62
        row_h = 48
        draw.rounded_rectangle((table_left, table_y, table_right, table_y + header_h), radius=12, fill=header)
        headers = [("S.No", col[0], col[1]), ("Items", col[1], col[2]), ("Qty", col[2], col[3]), ("Rate", col[3], col[4]), ("Amount", col[4], col[5])]
        for label, x0, x1 in headers:
            centered(draw, label, (x0, table_y, x1, table_y + header_h), font_bold, "white")
        for index, item in enumerate(chunk):
            global_index = (page_no - 1) * rows_per_page + index + 1
            y = table_y + header_h + index * row_h
            fill = (255, 255, 255) if index % 2 else (252, 253, 255)
            for x0, x1 in zip(col, col[1:]):
                draw.rectangle((x0, y, x1, y + row_h), outline=line, fill=fill, width=2)
            centered(draw, str(global_index), (col[0], y, col[1], y + row_h), font_small)
            draw.text((col[1] + 14, y + 14), item["description"], font=font_small, fill=ink)
            centered(draw, f"{item['qty']:g}", (col[2], y, col[3], y + row_h), font_small)
            text_right(draw, (col[4] - 16, y + 14), money(item["rate"]), font_small)
            text_right(draw, (col[5] - 16, y + 14), money(item["amount"]), font_small)

        if page_no == len(chunks):
            totals_y = table_y + header_h + max(len(chunk), 1) * row_h + 54
            totals_left = width - 500
            totals = [("Subtotal", subtotal), (f"Tax {tax_percent:g}%", tax), ("Discount", -discount), ("Paid", paid), ("Due", due), ("Total", total)]
            for idx, (label, value) in enumerate(totals):
                y = totals_y + idx * 42
                fill = header if label == "Total" else (255, 255, 255)
                text_fill = "white" if label == "Total" else ink
                draw.rectangle((totals_left, y, right, y + 42), outline=line, fill=fill, width=2)
                draw.text((totals_left + 18, y + 11), label, font=font_bold if label == "Total" else font_small, fill=text_fill)
                text_right(draw, (right - 18, y + 11), money(value), font_bold if label == "Total" else font_small, text_fill)
            if notes:
                draw.text((left, height - 232), "Notes", font=font_bold, fill=ink)
                draw_wrapped(draw, notes, (left, height - 198), font_small, muted, 660, max_lines=4)
            draw.text((left, height - 94), "SIGN AND SEAL OF AUTHORITY", font=font_small, fill=ink)
        else:
            draw.text((left, height - 94), "Continued on next page", font=font_small, fill=muted)
        pages.append(img)

    out = DOWNLOAD_DIR / f"{make_id()}_invoice.pdf"
    preview = out.with_suffix(".png")
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    pages[0].resize((620, 877), Image.Resampling.LANCZOS).save(preview, "PNG", optimize=True)
    return out, preview, {"item_count": len(items), "total": money(total)}


def pil_images_to_pdf(files, page_size="auto"):
    images = []
    sources = []
    try:
        for storage in files[:30]:
            source = safe_file_from_upload(storage, kind="image")
            sources.append(source)
            with Image.open(source) as img:
                rgb = ImageOps.exif_transpose(img).convert("RGB")
                if page_size == "a4":
                    page = Image.new("RGB", (1240, 1754), "white")
                    copy = rgb.copy()
                    copy.thumbnail((1080, 1550), Image.Resampling.LANCZOS)
                    page.paste(copy, ((1240 - copy.width) // 2, (1754 - copy.height) // 2))
                    rgb = page
                images.append(rgb.copy())
        if not images:
            raise ApiError("Please upload at least one image.")
        out = DOWNLOAD_DIR / f"{make_id()}_images.pdf"
        first, rest = images[0], images[1:]
        first.save(out, "PDF", save_all=True, append_images=rest, resolution=150.0)
        preview = DOWNLOAD_DIR / f"{out.stem}_preview.png"
        images[0].copy().resize((min(620, images[0].width), max(1, int(images[0].height * min(620, images[0].width) / images[0].width))), Image.Resampling.LANCZOS).save(preview, "PNG", optimize=True)
        return out, preview, len(images)
    finally:
        for source in sources:
            delete_quietly(source)


def render_pdf_to_zip(source, scale=2):
    scale = max(1, min(3, int(scale or 2)))
    out = DOWNLOAD_DIR / f"{make_id()}_pdf_pages.zip"
    preview = DOWNLOAD_DIR / f"{out.stem}_preview.png"
    if pymupdf is None or not hasattr(pymupdf, "open"):
        render_pdf_to_zip_subprocess(source, out, preview, scale)
        return out, preview
    with pymupdf.open(str(source)) as document:
        if document.page_count > 60:
            raise ApiError("PDF has too many pages. Max 60 pages supported.")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            matrix = pymupdf.Matrix(scale, scale)
            for index, page in enumerate(document, start=1):
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                png = pix.tobytes("png")
                archive.writestr(f"page-{index:03d}.png", png)
                if index == 1:
                    preview.write_bytes(png)
    return out, preview


def render_pdf_to_zip_subprocess(source, out, preview, scale):
    script = r"""
import sys
import zipfile
import importlib.util

vendor, source, out, preview, scale = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
sys.path.insert(0, vendor)
pymupdf_init = vendor + "/pymupdf/__init__.py"
spec = importlib.util.spec_from_file_location("pymupdf", pymupdf_init, submodule_search_locations=[vendor + "/pymupdf"])
pymupdf = importlib.util.module_from_spec(spec)
sys.modules["pymupdf"] = pymupdf
spec.loader.exec_module(pymupdf)

with pymupdf.open(source) as document:
    if document.page_count > 60:
        raise SystemExit("PDF has too many pages. Max 60 pages supported.")
    matrix = pymupdf.Matrix(scale, scale)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, page in enumerate(document, start=1):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png = pix.tobytes("png")
            archive.writestr(f"page-{index:03d}.png", png)
            if index == 1:
                open(preview, "wb").write(png)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(VENDOR_DIR), str(source), str(out), str(preview), str(scale)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0 or not out.exists():
        detail = (result.stderr or result.stdout or _pymupdf_error or "Renderer failed").strip()
        raise ApiError(f"Could not export this PDF to images. {detail[:900]}", 500)


def draw_watermark(base, text, options):
    layer = Image.new("RGBA", base.size, (255, 255, 255, 0))
    font_size = max(14, int(min(base.size) * options["size"] / 260))
    font = load_watermark_font(options["font"], font_size)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = measure.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x = max(8, font_size // 3)
    pad_y = max(6, font_size // 4)
    stamp_w = tw + pad_x * 2
    stamp_h = th + pad_y * 2
    stamp = Image.new("RGBA", (stamp_w, stamp_h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(stamp)
    alpha = int(255 * options["opacity"] / 100)
    text_color = (*parse_hex_color(options["color"]), alpha)
    badge = options["badge"]
    if badge != "none":
        if badge == "dark":
            fill = (15, 23, 42, int(alpha * 0.72))
        elif badge == "light":
            fill = (255, 255, 255, int(alpha * 0.72))
        else:
            fill = (255, 255, 255, int(alpha * 0.45))
        draw.rounded_rectangle((0, 0, stamp_w, stamp_h), radius=max(8, font_size // 4), fill=fill)
    draw.text((pad_x - bbox[0], pad_y - bbox[1]), text, font=font, fill=text_color)
    angle = options["angle"]
    if angle:
        stamp = stamp.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)

    if options["position"] == "tile":
        step_x = max(stamp.width + font_size * 2, base.width // 3)
        step_y = max(stamp.height + font_size * 2, base.height // 4)
        for y in range(-stamp.height, base.height + stamp.height, step_y):
            for x in range(-stamp.width, base.width + stamp.width, step_x):
                layer.alpha_composite(stamp, (x, y))
        return Image.alpha_composite(base, layer)

    pad = max(18, min(base.size) // 28)
    positions = {
        "top-left": (pad + stamp.width // 2, pad + stamp.height // 2),
        "top-right": (base.width - pad - stamp.width // 2, pad + stamp.height // 2),
        "center": (base.width // 2, base.height // 2),
        "bottom-left": (pad + stamp.width // 2, base.height - pad - stamp.height // 2),
        "bottom-right": (base.width - pad - stamp.width // 2, base.height - pad - stamp.height // 2),
    }
    if options["position"] == "manual":
        cx = int(base.width * options["x"] / 100)
        cy = int(base.height * options["y"] / 100)
    else:
        cx, cy = positions.get(options["position"], positions["bottom-right"])
    x = max(0, min(base.width - stamp.width, int(cx - stamp.width / 2)))
    y = max(0, min(base.height - stamp.height, int(cy - stamp.height / 2)))
    layer.alpha_composite(stamp, (x, y))
    return Image.alpha_composite(base, layer)


def save_jpeg_fast(img, out, quality=92):
    img.convert("RGB").save(out, "JPEG", quality=quality, optimize=False, progressive=False, subsampling=1)


def enhance_image(img, mode="auto", strength=68):
    amount = max(0.2, min(1.0, strength / 100))
    rgb = ImageOps.exif_transpose(img).convert("RGB")
    enhanced = ImageOps.autocontrast(rgb, cutoff=0.4)
    profiles = {
        "auto": (1.08, 1.20, 1.18, 150),
        "hdr": (1.05, 1.34, 1.26, 175),
        "portrait": (1.06, 1.14, 1.12, 125),
        "product": (1.03, 1.28, 1.16, 180),
        "lowlight": (1.24, 1.20, 1.08, 135),
        "sharp": (1.00, 1.24, 1.10, 220),
    }
    brightness, contrast, color, sharp = profiles.get(mode, profiles["auto"])
    enhanced = ImageEnhance.Brightness(enhanced).enhance(1 + (brightness - 1) * amount)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1 + (contrast - 1) * amount)
    enhanced = ImageEnhance.Color(enhanced).enhance(1 + (color - 1) * amount)
    if mode in {"portrait", "lowlight"}:
        enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(1 + 1.4 * amount)
    enhanced = enhanced.filter(ImageFilter.UnsharpMask(radius=1.05, percent=int(sharp * amount), threshold=2))
    return enhanced


def center_portrait_mask(size, feather=8):
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    margin_x = int(width * 0.18)
    top = int(height * 0.08)
    bottom = int(height * 0.98)
    draw.ellipse((margin_x, top, width - margin_x, bottom), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(max(2, feather)))


def subject_mask_from_image(img, feather=8):
    if remove_background is None:
        return center_portrait_mask(img.size, feather)
    working = img.convert("RGBA")
    original_size = working.size
    max_side = 1280
    if max(working.size) > max_side:
        working.thumbnail((max_side, max_side), Image.Resampling.BICUBIC)
    try:
        result = remove_background(
            image_bytes_from_pil(working),
            alpha_matting=False,
        )
        with Image.open(__import__("io").BytesIO(result)) as cutout:
            mask = cutout.convert("RGBA").getchannel("A")
    except Exception:
        return center_portrait_mask(original_size, feather)
    if mask.size != original_size:
        mask = mask.resize(original_size, Image.Resampling.BICUBIC)
    return mask.filter(ImageFilter.GaussianBlur(max(1, feather)))


def image_bytes_from_pil(img):
    buffer = __import__("io").BytesIO()
    img.save(buffer, "PNG")
    return buffer.getvalue()


def create_blur_background(img, mode="subject", blur=22, feather=8):
    base = ImageOps.exif_transpose(img).convert("RGB")
    background = ImageEnhance.Contrast(base.filter(ImageFilter.GaussianBlur(blur))).enhance(1.03)
    if mode == "center":
        mask = center_portrait_mask(base.size, feather)
    else:
        mask = subject_mask_from_image(base, feather)
    return Image.composite(base, background, mask)


def convert_video_file_to_mp3(source):
    ffmpeg = require_ffmpeg()
    out = DOWNLOAD_DIR / f"{make_id()}_{source.stem}.mp3"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(out),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=MAX_CONTENT_LENGTH // (1024 * 1024) * 3)
    except subprocess.TimeoutExpired as error:
        raise ApiError("MP3 conversion took too long. Try a shorter or smaller video.", 500) from error
    if result.returncode != 0 or not out.exists():
        raise ApiError("Could not convert this video to MP3. Please try another file.", 500)
    return {"success": True, "title": source.name, "filename": out.name, "download_url": public_download_url(out.name), "download_label": "Download MP3"}


def run_yt_dlp(url, mode, quality="1080"):
    output_prefix = make_id()
    output_template = str(DOWNLOAD_DIR / f"{output_prefix}_%(title).80s.%(ext)s")
    common_opts = {
        **ytdlp_base_opts(),
        "outtmpl": output_template,
        "restrictfilenames": True,
        "windowsfilenames": True,
    }
    if mode == "audio":
        require_ffmpeg()
        ydl_opts = {
            **common_opts,
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }
    else:
        height = re.sub(r"[^0-9]", "", str(quality or "1080")) or "1080"
        has_ffmpeg = shutil.which("ffmpeg") is not None
        ydl_opts = {
            **common_opts,
            "format": f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best" if has_ffmpeg else f"best[height<={height}]/best",
        }
        if has_ffmpeg:
            ydl_opts["merge_output_format"] = "mp4"

    info, ydl = extract_info_safe(url, download=True, extra_opts=ydl_opts)
    after = [p for p in DOWNLOAD_DIR.glob(f"{output_prefix}_*") if p.is_file()]
    if not after:
        requested = ydl.prepare_filename(info)
        possible = Path(requested)
        if mode == "audio":
            possible = possible.with_suffix(".mp3")
        after = [possible] if possible.exists() else []
    if not after:
        raise ApiError("Download finished but the output file was not found.", 500)
    file_path = max(after, key=lambda p: p.stat().st_mtime)
    return {
        "success": True,
        "title": info.get("title", "Downloaded file"),
        "filename": file_path.name,
        "download_url": public_download_url(file_path.name),
        "download_label": "Download MP3" if mode == "audio" else "Download video",
    }


@app.route("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/healthz")
def healthz():
    return jsonify({"success": True, "status": "ok"})


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/pages/<path:filename>")
def pages(filename):
    return send_from_directory(FRONTEND_DIR / "pages", filename)


@app.route("/<path:filename>")
def frontend_file(filename):
    return send_from_directory(FRONTEND_DIR, filename)


@app.route("/download/<path:filename>")
def download_file(filename):
    file_path = safe_download_path(filename)
    should_delete = request.args.get("download") == "1"
    response = send_file(file_path, as_attachment=should_delete)
    if should_delete:
        delete_later(file_path, DELETE_AFTER_DOWNLOAD_SECONDS)
    return response


@app.post("/api/media/info")
def get_media_info():
    cleanup_temp_storage()
    data = request.get_json(silent=True) or request.form
    url = clean_url(data.get("url"))
    try:
        return jsonify(media_info(url))
    except ApiError as error:
        parsed = urlparse(url)
        if any(domain in parsed.netloc.lower() for domain in ("instagram.com", "pinterest.")):
            return jsonify(social_preview_fallback(url, error.message))
        raise


@app.post("/api/download/youtube")
def youtube_download():
    cleanup_temp_storage()
    data = request.get_json(silent=True) or request.form
    url = clean_url(data.get("url"))
    quality = data.get("quality", "1080")
    return jsonify(run_yt_dlp(url, "video", quality))


@app.post("/api/download/instagram")
def instagram_download():
    cleanup_temp_storage()
    data = request.get_json(silent=True) or request.form
    url = clean_url(data.get("url"))
    return jsonify(run_yt_dlp(url, "video", "1080"))


@app.post("/api/download/pinterest")
def pinterest_download():
    cleanup_temp_storage()
    data = request.get_json(silent=True) or request.form
    url = clean_url(data.get("url"))
    return jsonify(run_yt_dlp(url, "video", "1080"))


@app.post("/api/convert/audio")
def video_to_mp3():
    cleanup_temp_storage()
    data = request.get_json(silent=True) or request.form
    url = clean_url(data.get("url"))
    return jsonify(run_yt_dlp(url, "audio"))


@app.post("/api/convert/audio-upload")
def video_upload_to_mp3():
    cleanup_temp_storage()
    source = safe_file_from_upload(request.files.get("file"), kind="video")
    try:
        return jsonify(convert_video_file_to_mp3(source))
    finally:
        delete_quietly(source)


@app.post("/api/youtube/thumbnail")
def youtube_thumbnail():
    cleanup_temp_storage()
    data = request.get_json(silent=True) or request.form
    url = clean_url(data.get("url"))
    info, _ = extract_info_safe(url, download=False, extra_opts={"skip_download": True})
    video_id = info.get("id")
    title = secure_filename(info.get("title") or "youtube_thumbnail")
    candidates = [
        f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        f"https://img.youtube.com/vi/{video_id}/sddefault.jpg",
        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
    ]
    for thumb_url in candidates:
        try:
            content = fetch_url_bytes(thumb_url)
        except requests.RequestException:
            continue
        if len(content) > 1024:
            path = DOWNLOAD_DIR / f"{make_id()}_{title}.jpg"
            path.write_bytes(content)
            return jsonify({"success": True, "title": info.get("title"), "filename": path.name, "download_url": public_download_url(path.name), "preview_url": public_download_url(path.name), "download_label": "Download thumbnail"})
    raise ApiError("Could not fetch a HD thumbnail for this video.")


@app.post("/api/image/upscale")
def image_upscale():
    cleanup_temp_storage()
    source = safe_file_from_upload(request.files.get("file"))
    try:
        requested_scale = clamp_int(request.form.get("scale"), 2, 2, 4)
        detail = clamp_int(request.form.get("detail"), 72, 30, 100)
        mode = request.form.get("mode", "photo")
        if mode not in {"photo", "crisp", "fast"}:
            mode = "photo"
        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img)
            original_width, original_height = img.size
            original_pixels = img.width * img.height
            scale = requested_scale
            if original_pixels * scale * scale > MAX_UPSCALE_PIXELS:
                scale = (MAX_UPSCALE_PIXELS / original_pixels) ** 0.5
            scale = max(1, min(requested_scale, scale))
            out_width = img.width * scale
            out_height = img.height * scale
            out_width = max(1, int(round(out_width)))
            out_height = max(1, int(round(out_height)))
            has_alpha = img.mode in {"RGBA", "LA"} or (img.mode == "P" and "transparency" in img.info)
            img = img.convert("RGBA" if has_alpha else "RGB")
            resample = Image.Resampling.BICUBIC if mode == "fast" else Image.Resampling.LANCZOS
            resized = img.resize((out_width, out_height), resample)
            percent = int((130 if mode == "photo" else 175 if mode == "crisp" else 115) * detail / 72)
            resized = resized.filter(ImageFilter.UnsharpMask(radius=1.05 if mode != "crisp" else 0.9, percent=percent, threshold=2))
            if not has_alpha:
                resized = enhance_image(resized, mode="sharp" if mode == "crisp" else "auto", strength=max(35, min(85, detail)))
            ext = "png" if has_alpha else "jpg"
            out = DOWNLOAD_DIR / f"{make_id()}_upscaled.{ext}"
            tmp = out.with_suffix(out.suffix + ".tmp")
            try:
                if has_alpha:
                    resized.save(tmp, "PNG", optimize=False, compress_level=3)
                else:
                    resized.save(tmp, "JPEG", quality=90, optimize=False, progressive=False, subsampling=1)
                tmp.replace(out)
            finally:
                delete_quietly(tmp)
        scale_label = f"{scale:.1f}".rstrip("0").rstrip(".")
        return jsonify({
            **image_response(out, "Download upscaled image"),
            "title": f"{scale_label}x upscaled image",
            "original_width": original_width,
            "original_height": original_height,
            "output_width": out_width,
            "output_height": out_height,
        })
    finally:
        delete_quietly(source)


@app.post("/api/image/enhance")
def image_enhance():
    cleanup_temp_storage()
    source = safe_file_from_upload(request.files.get("file"))
    try:
        mode = request.form.get("mode", "auto")
        if mode not in {"auto", "hdr", "portrait", "product", "lowlight", "sharp"}:
            mode = "auto"
        strength = clamp_int(request.form.get("strength"), 68, 20, 100)
        with Image.open(source) as img:
            original_width, original_height = img.size
            enhanced = enhance_image(img, mode=mode, strength=strength)
            out = DOWNLOAD_DIR / f"{make_id()}_enhanced.jpg"
            save_jpeg_fast(enhanced, out, quality=92)
        return jsonify({
            **image_response(out, "Download enhanced image"),
            "title": "AI enhanced image",
            "original_width": original_width,
            "original_height": original_height,
            "output_width": enhanced.width,
            "output_height": enhanced.height,
        })
    finally:
        delete_quietly(source)


@app.post("/api/image/blur-background")
def image_blur_background():
    cleanup_temp_storage()
    source = safe_file_from_upload(request.files.get("file"))
    try:
        mode = request.form.get("mode", "subject")
        if mode not in {"subject", "center"}:
            mode = "subject"
        blur = clamp_int(request.form.get("blur"), 22, 8, 36)
        feather = clamp_int(request.form.get("feather"), 8, 2, 18)
        with Image.open(source) as img:
            original_width, original_height = img.size
            blurred = create_blur_background(img, mode=mode, blur=blur, feather=feather)
            out = DOWNLOAD_DIR / f"{make_id()}_blur_bg.jpg"
            save_jpeg_fast(blurred, out, quality=92)
        return jsonify({
            **image_response(out, "Download blur background image"),
            "title": "DSLR-style blur background",
            "original_width": original_width,
            "original_height": original_height,
            "output_width": blurred.width,
            "output_height": blurred.height,
        })
    finally:
        delete_quietly(source)


@app.post("/api/image/compress")
def image_compress():
    cleanup_temp_storage()
    source = safe_file_from_upload(request.files.get("file"))
    try:
        original_size = source.stat().st_size
        quality = clamp_int(request.form.get("quality"), 55, 1, 95)
        output_format = request.form.get("format", "jpg")
        if output_format not in {"jpg", "webp"}:
            output_format = "jpg"
        max_side = clamp_int(request.form.get("max_side"), 0, 0, 4000)
        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            original_width, original_height = img.size
            if max_side and max(img.size) > max_side:
                img.thumbnail((max_side, max_side), Image.Resampling.BICUBIC)
            ext = "webp" if output_format == "webp" else "jpg"
            out = DOWNLOAD_DIR / f"{make_id()}_compressed.{ext}"
            if output_format == "webp":
                img.save(out, "WEBP", quality=quality, method=4)
            else:
                img.save(out, "JPEG", quality=quality, optimize=True, progressive=True, subsampling=2)
        return jsonify({
            **image_response(out, "Download compressed image"),
            "original_size": original_size,
            "compressed_size": out.stat().st_size,
            "original_width": original_width,
            "original_height": original_height,
            "output_width": img.width,
            "output_height": img.height,
        })
    finally:
        delete_quietly(source)


@app.post("/api/image/removebg")
def image_removebg():
    cleanup_temp_storage()
    source = safe_file_from_upload(request.files.get("file"))
    try:
        out = DOWNLOAD_DIR / f"{make_id()}_no_bg.png"
        feather = int(request.form.get("feather", 2))
        feather = max(0, min(feather, 8))
        background = request.form.get("background", "transparent")
        if remove_background is not None:
            result = remove_background(
                source.read_bytes(),
                alpha_matting=True,
                alpha_matting_foreground_threshold=240,
                alpha_matting_background_threshold=10,
                alpha_matting_erode_size=8,
            )
            out.write_bytes(result)
            postprocess_cutout(out, feather=feather, background=background)
        else:
            remove_background_fallback(source, out, feather=feather, background=background)
        return jsonify(image_response(out, "Download PNG image"))
    finally:
        delete_quietly(source)


@app.post("/api/image/convert")
def image_convert():
    cleanup_temp_storage()
    source = safe_file_from_upload(request.files.get("file"))
    try:
        output_format = request.form.get("format", "png").lower()
        if output_format not in {"png", "jpg", "webp"}:
            raise ApiError("Choose PNG, JPG, or WEBP format.")
        with Image.open(source) as img:
            ext = "jpg" if output_format == "jpg" else output_format
            out = DOWNLOAD_DIR / f"{make_id()}_converted.{ext}"
            if output_format == "png":
                img.convert("RGBA").save(out, "PNG", optimize=True)
            elif output_format == "webp":
                img.convert("RGBA").save(out, "WEBP", quality=90, method=6)
            else:
                img.convert("RGB").save(out, "JPEG", quality=92, optimize=True, progressive=True)
        return jsonify(image_response(out, "Download converted image"))
    finally:
        delete_quietly(source)


@app.post("/api/image/watermark")
def image_watermark():
    cleanup_temp_storage()
    source = safe_file_from_upload(request.files.get("file"))
    try:
        text = (request.form.get("text") or "ThugTools").strip()[:80]
        if not text:
            raise ApiError("Please enter watermark text.")
        options = {
            "opacity": clamp_int(request.form.get("opacity"), 38, 10, 85),
            "size": clamp_int(request.form.get("size"), 16, 8, 30),
            "angle": clamp_int(request.form.get("angle"), 0, -45, 45),
            "position": request.form.get("position", "manual"),
            "font": request.form.get("font", "arial"),
            "badge": request.form.get("badge", "soft"),
            "color": request.form.get("color", "#111827"),
            "x": clamp_int(request.form.get("x"), 78, 0, 100),
            "y": clamp_int(request.form.get("y"), 82, 0, 100),
        }
        if options["position"] not in {"manual", "top-left", "top-right", "center", "bottom-left", "bottom-right", "tile"}:
            options["position"] = "manual"
        if options["badge"] not in {"soft", "none", "dark", "light"}:
            options["badge"] = "soft"
        with Image.open(source) as img:
            base = ImageOps.exif_transpose(img).convert("RGBA")
            out = DOWNLOAD_DIR / f"{make_id()}_watermarked.png"
            draw_watermark(base, text, options).save(out, "PNG", optimize=True)
        return jsonify(image_response(out, "Download watermarked image"))
    finally:
        delete_quietly(source)


@app.post("/api/qr/generate")
def qr_generate():
    cleanup_temp_storage()
    qr_class = getattr(qrcode, "QRCode", None) if qrcode is not None else None
    qr_constants = getattr(qrcode, "constants", None) if qrcode is not None else None
    if qr_class is None and qrcode is not None:
        try:
            qr_main = importlib.import_module("qrcode.main")
            qr_class = getattr(qr_main, "QRCode", None)
        except Exception:
            qr_class = None
    if qr_class is None or qr_constants is None:
        raise ApiError("QR dependency missing. Run: pip install -r requirements.txt", 500)
    data = request.get_json(silent=True) or request.form
    text = (data.get("text") or "").strip()
    if not text:
        raise ApiError("Enter text or a URL for QR code.")
    box_size = int(data.get("size", 12))
    box_size = max(6, min(box_size, 20))
    qr = qr_class(version=None, error_correction=qr_constants.ERROR_CORRECT_H, box_size=box_size, border=4)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#111827", back_color="white").convert("RGB")
    out = DOWNLOAD_DIR / f"{make_id()}_qr.png"
    img.save(out, "PNG", optimize=True)
    return jsonify({**image_response(out, "Download QR code"), "preview_url": public_download_url(out.name), "title": "QR Code"})


@app.post("/api/invoice/generate")
def invoice_generate():
    cleanup_temp_storage()
    data = request.get_json(silent=True) or request.form
    out, preview, meta = create_invoice_pdf(data)
    return jsonify({
        **file_response(out, "Download invoice PDF"),
        "preview_url": public_download_url(preview.name),
        "title": "Invoice PDF ready",
        **meta,
    })


@app.post("/api/pdf/image-to-pdf")
def image_to_pdf():
    cleanup_temp_storage()
    files = request.files.getlist("files")
    if not files and request.files.get("file"):
        files = [request.files.get("file")]
    out, preview, count = pil_images_to_pdf(files, request.form.get("page_size", "auto"))
    return jsonify({
        **file_response(out, "Download PDF"),
        "preview_url": public_download_url(preview.name),
        "page_count": count,
        "title": f"{count} image{'s' if count != 1 else ''} converted to PDF",
    })


@app.post("/api/pdf/pdf-to-image")
def pdf_to_image():
    cleanup_temp_storage()
    source = safe_file_from_upload(request.files.get("file"), kind="pdf")
    try:
        out, preview = render_pdf_to_zip(source, request.form.get("scale", 2))
        return jsonify({
            **file_response(out, "Download ZIP"),
            "preview_url": public_download_url(preview.name),
            "title": "PDF pages exported as PNG images",
        })
    finally:
        delete_quietly(source)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, use_reloader=False)
