import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import base64
import importlib
import importlib.util
import io
import json
import hashlib
import zipfile
from html import escape, unescape
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests
import certifi
from flask import Flask, Response, jsonify, request, send_file, send_from_directory, redirect
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from yt_dlp import YoutubeDL
from yt_dlp.version import __version__ as YTDLP_VERSION
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
    from rembg import new_session as rembg_new_session
    from rembg import remove as remove_background
    _rembg_import_error = ""
except Exception as error:
    remove_background = None
    rembg_new_session = None
    _rembg_import_error = str(error)

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
MEDIA_INFO_CACHE_SECONDS = 10 * 60
_media_info_cache = {}
FONT_DIR = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
RUNTIME_COOKIES_DIR = Path(os.environ.get("TMPDIR", BASE_DIR)) / "youtube_cookies"
RUNTIME_COOKIES_DIR.mkdir(parents=True, exist_ok=True)
YOUTUBE_COOKIES_HELP = "YouTube is blocking this server. Add fresh YouTube cookies, or add multiple rotated profiles as YOUTUBE_COOKIES_TEXT_1, YOUTUBE_COOKIES_TEXT_2, and YOUTUBE_COOKIES_TEXT_3 in Railway Variables, then redeploy."
INSTAGRAM_COOKIES_HELP = "Instagram is asking this server to log in. Add fresh Instagram cookies as INSTAGRAM_COOKIES_TEXT_1, INSTAGRAM_COOKIES_TEXT_2, and INSTAGRAM_COOKIES_TEXT_3 in Railway Variables, then redeploy."
SEO_PAGES = [
    ("/", "daily", "1.0"),
    ("/youtube-video-downloader", "weekly", "0.9"),
    ("/pinterest-downloader", "weekly", "0.9"),
    ("/instagram-reel-downloader", "weekly", "0.9"),
    ("/youtube-thumbnail-downloader", "weekly", "0.9"),
    ("/qr-code-generator", "weekly", "0.9"),
    ("/pdf-to-image", "weekly", "0.8"),
    ("/image-to-pdf", "weekly", "0.8"),
    ("/image-compressor", "weekly", "0.9"),
    ("/remove-background", "weekly", "0.9"),
    ("/image-upscale", "weekly", "0.8"),
    ("/ai-image-enhancer", "weekly", "0.8"),
    ("/blur-background", "weekly", "0.8"),
    ("/image-converter", "weekly", "0.8"),
    ("/image-watermark", "weekly", "0.8"),
    ("/video-to-mp3", "weekly", "0.8"),
    ("/invoice-generator", "weekly", "0.7"),
    ("/about", "monthly", "0.5"),
    ("/privacy-policy", "monthly", "0.4"),
    ("/terms", "monthly", "0.4"),
    ("/dmca", "monthly", "0.4"),
    ("/contact", "monthly", "0.4"),
    ("/policy", "monthly", "0.4"),
]

SITE_NAME = "ThugTools"
DEFAULT_IMAGE = "/assets/site-logo.png"
SITE_DESCRIPTION = "ThugTools is built for creators who do not like waiting."
REMBG_MODEL_DEFAULT = os.environ.get("REMBG_MODEL", "u2netp").strip() or "u2netp"
REMBG_MAX_SIDE = int(os.environ.get("REMBG_MAX_SIDE", "512"))
_rembg_sessions = {}
_rembg_session_lock = threading.Lock()

TOOL_PAGE_SEO = {
    "youtube.html": {
        "path": "/youtube-video-downloader",
        "title": "YouTube Video Downloader - Save HD & 4K Videos Free | ThugTools",
        "description": "Download public YouTube videos online in HD, 1080p, 2K, or 4K when available. Fast free YouTube downloader with preview and no signup.",
        "keywords": "youtube video downloader, download youtube videos, youtube downloader hd, save youtube video, 4k youtube downloader",
        "category": "VideoApplication",
        "how": ["Paste a public YouTube video URL.", "Choose Best available or a preferred video quality.", "Click Download video and save the generated file."],
        "features": ["HD, 2K, and 4K quality requests when the source provides them", "Fast link preview for supported YouTube URLs", "Temporary generated files for cleaner privacy"],
        "faqs": [("Can I download private YouTube videos?", "No. Only public videos that are accessible to the server can be processed."), ("Why is a quality unavailable?", "YouTube may not expose every quality for every video or server location.")],
        "related": [("/youtube-thumbnail-downloader", "YouTube Thumbnail Downloader"), ("/video-to-mp3", "Video to MP3"), ("/instagram-reel-downloader", "Instagram Downloader")],
    },
    "pinterest.html": {
        "path": "/pinterest-downloader",
        "title": "Pinterest Downloader - Save Public Videos & Pins Free | ThugTools",
        "description": "Save public Pinterest videos and media online in best available quality. Free Pinterest downloader for creators with no signup.",
        "keywords": "pinterest downloader, pinterest video downloader, save pinterest video, download pinterest pins",
        "category": "VideoApplication",
        "how": ["Copy a public Pinterest pin or video link.", "Paste the URL into the downloader.", "Choose a quality and download the result."],
        "features": ["Supports public Pinterest video/media URLs", "Quality selector for available formats", "Preview-friendly workflow for creator references"],
        "faqs": [("Do private Pinterest links work?", "No. Private, login-only, or blocked links may fail."), ("Does every pin include video?", "No. Some pins are image-only or expose limited downloadable media.")],
        "related": [("/instagram-reel-downloader", "Instagram Downloader"), ("/youtube-video-downloader", "YouTube Downloader"), ("/image-compressor", "Image Compressor")],
    },
    "instagram.html": {
        "path": "/instagram-reel-downloader",
        "title": "Instagram Reel Downloader - Save Public Reels Free | ThugTools",
        "description": "Download public Instagram reels, posts, and videos online in clean quality. Fast Instagram reel downloader with no signup.",
        "keywords": "instagram reel downloader, instagram downloader, download instagram reels, save instagram video",
        "category": "VideoApplication",
        "how": ["Open a public Instagram reel or post.", "Paste its URL into ThugTools.", "Download the available video file."],
        "features": ["Public reels and posts support", "Embed preview fallback when thumbnails are blocked", "Simple quality request controls"],
        "faqs": [("Can it download private reels?", "No. Only public and accessible Instagram URLs should be used."), ("Why is preview limited sometimes?", "Instagram can block direct metadata, so the page may show an embed fallback.")],
        "related": [("/pinterest-downloader", "Pinterest Downloader"), ("/video-to-mp3", "Video to MP3"), ("/image-watermark", "Watermark Studio")],
    },
    "thumbnail.html": {
        "path": "/youtube-thumbnail-downloader",
        "title": "YouTube Thumbnail Downloader - Download HD Thumbnails | ThugTools",
        "description": "Download high-resolution YouTube thumbnails online from public video links. Save max resolution, SD, or HQ thumbnails fast.",
        "keywords": "youtube thumbnail downloader, download youtube thumbnail, hd thumbnail saver, maxresdefault thumbnail",
        "category": "UtilitiesApplication",
        "how": ["Paste a public YouTube video URL.", "Click Download thumbnail.", "Preview and save the best available image."],
        "features": ["Checks max resolution, SD, and HQ thumbnail sources", "No file upload needed", "Clean preview before download"],
        "faqs": [("Will every video have a max resolution thumbnail?", "No. Some videos only expose standard or HQ thumbnails."), ("Can I use thumbnails commercially?", "Only if you have rights or permission to use the image.")],
        "related": [("/youtube-video-downloader", "YouTube Downloader"), ("/image-compressor", "Image Compressor"), ("/image-watermark", "Watermark Studio")],
    },
    "qr.html": {
        "path": "/qr-code-generator",
        "title": "QR Code Generator - Create Free PNG QR Codes | ThugTools",
        "description": "Generate crisp QR codes for links, text, WiFi notes, payments, profiles, and business cards. Free QR code generator with PNG download.",
        "keywords": "qr code generator, create qr code, free qr code maker, qr code png, upi qr generator",
        "category": "UtilitiesApplication",
        "how": ["Enter a URL, text, profile, payment note, or WiFi detail.", "Choose the QR size.", "Generate and download the PNG QR code."],
        "features": ["High error-correction QR output", "PNG download for sharing or print", "Works for URLs and plain text"],
        "faqs": [("Are QR codes stored permanently?", "No. Generated files are temporary and cleaned automatically."), ("Can I print the QR code?", "Yes. Use a larger size for better print clarity.")],
        "related": [("/invoice-generator", "Invoice Generator"), ("/image-to-pdf", "Image to PDF"), ("/image-compressor", "Image Compressor")],
    },
    "pdf-to-image.html": {
        "path": "/pdf-to-image",
        "title": "PDF to Image Converter - Export PDF Pages to PNG | ThugTools",
        "description": "Convert PDF pages to high-quality PNG images online and download them as a ZIP file. Fast free PDF to image converter.",
        "keywords": "pdf to image, pdf to png, convert pdf pages to images, pdf image converter",
        "category": "BusinessApplication",
        "how": ["Upload a PDF file.", "Choose the render scale.", "Convert pages and download the ZIP."],
        "features": ["Exports one PNG per PDF page", "Scale control for sharper output", "ZIP download keeps pages together"],
        "faqs": [("Why is the output a ZIP file?", "A ZIP keeps multiple page images together in one download."), ("Are large PDFs supported?", "Uploads are limited by the server size limit and processing time.")],
        "related": [("/image-to-pdf", "Image to PDF"), ("/image-compressor", "Image Compressor"), ("/invoice-generator", "Invoice Generator")],
    },
    "image-to-pdf.html": {
        "path": "/image-to-pdf",
        "title": "Image to PDF Converter - Combine JPG PNG WEBP Free | ThugTools",
        "description": "Convert JPG, PNG, and WEBP images into a clean printable PDF online. Upload one or many images and download one PDF.",
        "keywords": "image to pdf, jpg to pdf, png to pdf, webp to pdf, combine images into pdf",
        "category": "BusinessApplication",
        "how": ["Upload one or more images.", "Choose page sizing.", "Convert and download the PDF file."],
        "features": ["Multiple image upload support", "Auto and A4-style page options", "Print-ready PDF output"],
        "faqs": [("Can I upload multiple images?", "Yes. Multiple images can become one PDF."), ("Which image types work?", "JPG, PNG, and WEBP uploads are supported.")],
        "related": [("/pdf-to-image", "PDF to Image"), ("/image-compressor", "Image Compressor"), ("/invoice-generator", "Invoice Generator")],
    },
    "compress.html": {
        "path": "/image-compressor",
        "title": "Image Compressor - Reduce JPG & WEBP File Size Free | ThugTools",
        "description": "Compress JPG and WEBP images online with quality and resize controls. Reduce image file size for websites and social uploads.",
        "keywords": "image compressor, compress jpg, reduce image size, webp compressor, online image optimizer",
        "category": "MultimediaApplication",
        "how": ["Upload a JPG, PNG, or WEBP image.", "Choose output format, resize size, and quality.", "Compress and download the optimized file."],
        "features": ["Quality slider for file-size control", "JPG and WEBP output options", "Optional resize for faster pages"],
        "faqs": [("What quality setting is best?", "55 to 75 is a good balance for most web images."), ("Can I keep original dimensions?", "Yes. Choose Keep original size.")],
        "related": [("/image-converter", "Image Converter"), ("/remove-background", "Remove Background"), ("/image-to-pdf", "Image to PDF")],
    },
    "removebg.html": {
        "path": "/remove-background",
        "title": "Remove Background - AI Transparent PNG Cutout Tool | ThugTools",
        "description": "Remove image backgrounds online and create transparent PNG cutouts for products, portraits, profile photos, and social media.",
        "keywords": "remove background, background remover, transparent png, ai cutout tool, product photo background remover",
        "category": "MultimediaApplication",
        "how": ["Upload an image with a clear subject.", "Choose edge feathering and output background.", "Process and download the PNG result."],
        "features": ["Transparent PNG output", "Optional studio background colors", "Edge feather control for smoother cutouts"],
        "faqs": [("What images work best?", "Clear subjects with contrast from the background work best."), ("Why are hair or shadows imperfect?", "Fine edges, shadows, and busy backgrounds are harder to separate.")],
        "related": [("/ai-image-enhancer", "AI Image Enhancer"), ("/image-watermark", "Watermark Studio"), ("/image-compressor", "Image Compressor")],
    },
    "upscale.html": {
        "path": "/image-upscale",
        "title": "Image Upscaler - Enlarge Photos 2x & 4x Online | ThugTools",
        "description": "Upscale images online by 2x or 4x with sharpening and detail controls. Enlarge photos for social, product, and print use.",
        "keywords": "image upscaler, upscale image, enlarge photo, 2x image upscaler, 4x image upscaler",
        "category": "MultimediaApplication",
        "how": ["Upload a photo or graphic.", "Choose scale, mode, and detail strength.", "Upscale and download the larger image."],
        "features": ["2x and 4x resize options", "Photo, crisp, and fast modes", "Detail sharpening after resize"],
        "faqs": [("Does it restore missing detail?", "It improves size and sharpness, but very blurry originals still have limits."), ("Which mode should I use?", "Photo mode is safest for most pictures; crisp mode is stronger for graphics.")],
        "related": [("/ai-image-enhancer", "AI Image Enhancer"), ("/image-compressor", "Image Compressor"), ("/remove-background", "Remove Background")],
    },
    "enhance.html": {
        "path": "/ai-image-enhancer",
        "title": "AI Image Enhancer - Sharpen, Brighten & Improve Photos | ThugTools",
        "description": "Enhance images online with color, brightness, clarity, denoise, and sharpness controls. Improve photos for social and product use.",
        "keywords": "ai image enhancer, enhance photo, sharpen image, improve image quality, photo enhancer",
        "category": "MultimediaApplication",
        "how": ["Upload a dull or low-detail image.", "Choose enhancement mode and strength.", "Enhance and download the finished image."],
        "features": ["Auto, HDR, portrait, product, low-light, and sharp modes", "Adjustable enhancement strength", "Preview before downloading"],
        "faqs": [("Which setting is safest?", "Auto mode works well for most images."), ("Can the result be subtle?", "Yes. Lower strength keeps the edit softer.")],
        "related": [("/image-upscale", "Image Upscale"), ("/blur-background", "Blur Background"), ("/image-compressor", "Image Compressor")],
    },
    "blur.html": {
        "path": "/blur-background",
        "title": "Blur Background - DSLR Portrait Blur Effect Online | ThugTools",
        "description": "Create DSLR-style background blur for photos online. Add subject-focused blur with adjustable feather and strength.",
        "keywords": "blur background, portrait blur, dslr blur effect, background blur tool, photo blur editor",
        "category": "MultimediaApplication",
        "how": ["Upload a portrait, product, or subject photo.", "Choose subject or center mode.", "Adjust blur/feather and download the image."],
        "features": ["Subject-aware and center blur modes", "Blur strength and feather controls", "Clean JPG output for social posts"],
        "faqs": [("Which photos work best?", "Photos with a clear subject and simpler background work best."), ("Can I control the effect?", "Yes. Tune blur and feather sliders before processing.")],
        "related": [("/ai-image-enhancer", "AI Image Enhancer"), ("/remove-background", "Remove Background"), ("/image-watermark", "Watermark Studio")],
    },
    "convert.html": {
        "path": "/image-converter",
        "title": "Image Converter - Convert PNG, JPG & WEBP Free | ThugTools",
        "description": "Convert images between PNG, JPG, and WEBP online. Fast image format converter with preview and clean quality.",
        "keywords": "image converter, png to jpg, jpg to webp, webp to png, convert image format",
        "category": "MultimediaApplication",
        "how": ["Upload a PNG, JPG, or WEBP image.", "Select the output format.", "Convert and download the new file."],
        "features": ["PNG, JPG, and WEBP output", "Transparency-friendly formats", "Before and after preview"],
        "faqs": [("Does JPG keep transparency?", "No. Use PNG or WEBP when transparency matters."), ("Which format is smallest?", "WEBP is often smallest, while JPG remains widely compatible.")],
        "related": [("/image-compressor", "Image Compressor"), ("/image-to-pdf", "Image to PDF"), ("/image-watermark", "Watermark Studio")],
    },
    "watermark.html": {
        "path": "/image-watermark",
        "title": "Add Watermark to Images - Text Watermark Studio | ThugTools",
        "description": "Add professional text watermarks to images online. Control font, opacity, angle, color, badge style, and position.",
        "keywords": "add watermark, image watermark tool, text watermark, watermark photos, protect images online",
        "category": "MultimediaApplication",
        "how": ["Upload an image.", "Enter watermark text and adjust style controls.", "Place the watermark and download the protected image."],
        "features": ["Manual placement and preset corners", "Font, color, opacity, size, and angle controls", "Badge styles for readable watermarks"],
        "faqs": [("Can I move the watermark manually?", "Yes. Drag on the preview or use the position controls."), ("What opacity is best?", "25 to 45 percent is usually readable without feeling too heavy.")],
        "related": [("/image-compressor", "Image Compressor"), ("/remove-background", "Remove Background"), ("/ai-image-enhancer", "AI Image Enhancer")],
    },
    "audio.html": {
        "path": "/video-to-mp3",
        "title": "Video to MP3 Converter - Extract Audio Online Free | ThugTools",
        "description": "Convert public video links or uploaded video files to MP3 audio online. Extract clean 192 kbps MP3 files for permitted content.",
        "keywords": "video to mp3, convert video to mp3, extract audio, youtube to mp3, mp3 converter",
        "category": "MultimediaApplication",
        "how": ["Paste a public video URL or upload your own video file.", "Start MP3 conversion.", "Download the generated audio file."],
        "features": ["URL and local upload workflows", "Clean MP3 output", "Useful for owned recordings and permitted audio"],
        "faqs": [("Why is FFmpeg needed?", "FFmpeg handles reliable audio extraction and conversion on the server."), ("Can I upload my own video?", "Yes. Supported local video files can be converted to MP3.")],
        "related": [("/youtube-video-downloader", "YouTube Downloader"), ("/instagram-reel-downloader", "Instagram Downloader"), ("/pinterest-downloader", "Pinterest Downloader")],
    },
    "invoice.html": {
        "path": "/invoice-generator",
        "title": "Invoice Generator - Create Free PDF Invoices Online | ThugTools",
        "description": "Create professional printable PDF invoices online with business details, items, tax, discount, and totals.",
        "keywords": "invoice generator, create invoice, free invoice maker, pdf invoice, business invoice generator",
        "category": "BusinessApplication",
        "how": ["Enter business, client, and invoice details.", "Add items, tax, discount, and notes.", "Generate and download the PDF invoice."],
        "features": ["Itemized invoice editor", "Tax and discount support", "Print-ready PDF output"],
        "faqs": [("Is invoice data stored permanently?", "No. Generated files are temporary and cleaned automatically."), ("Can I add tax or GST?", "Yes. Use the tax fields available in the invoice form.")],
        "related": [("/qr-code-generator", "QR Code Generator"), ("/image-to-pdf", "Image to PDF"), ("/pdf-to-image", "PDF to Image")],
    },
}

LEGAL_PAGE_SEO = {
    "/about": ("About Us | ThugTools", "Learn about ThugTools, a free creator tools platform for image, video, PDF, QR, and everyday utility workflows."),
    "/privacy-policy": ("Privacy Policy | ThugTools", "Learn how ThugTools handles uploaded files, generated downloads, URLs, logs, privacy, and temporary storage."),
    "/terms": ("Terms of Service | ThugTools", "Read the ThugTools terms of service, acceptable use rules, disclaimers, and user responsibilities."),
    "/dmca": ("DMCA & Copyright Policy | ThugTools", "Review the ThugTools copyright policy, DMCA-style notice process, and responsible content-use rules."),
    "/contact": ("Contact ThugTools | Support, Privacy & Copyright Requests", "Contact ThugTools for support, business, privacy, copyright, and website requests."),
}

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
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
    if ("confirm you" in lowered and "bot" in lowered) or ("automated" in lowered and "traffic" in lowered):
        return YOUTUBE_COOKIES_HELP
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
        return "YouTube did not expose downloadable formats to this server. Try Best available, or add YOUTUBE_COOKIES_TEXT in Railway Variables."
    return msg.replace("ERROR:", "").strip()[:220] or "Could not download this media. Try another public link."


def is_youtube_url(url):
    host = urlparse(url).netloc.lower()
    return "youtube.com" in host or "youtu.be" in host


def is_instagram_url(url):
    return "instagram.com" in urlparse(url).netloc.lower()


def is_youtube_block_error(message):
    lowered = (message or "").lower()
    needles = (
        "automated traffic",
        "confirm you are not a bot",
        "sign in to confirm",
        "not a bot",
        "http error 403",
        "forbidden",
        "po token",
    )
    return any(needle in lowered for needle in needles)


def is_auth_block_error(message):
    lowered = (message or "").lower()
    needles = (
        "login",
        "log in",
        "sign in",
        "private",
        "forbidden",
        "http error 403",
        "not authorized",
        "requires authentication",
    )
    return any(needle in lowered for needle in needles)


def normalize_cookies_text(cookies_text, domains=()):
    cookies_clean = (cookies_text or "").strip()
    if not cookies_clean:
        return ""
    cookies_clean = cookies_clean.replace("\\r\\n", "\n").replace("\\n", "\n")
    lines = [line.strip() for line in cookies_clean.splitlines() if line.strip()]
    cookies_clean = "\n".join(lines)
    domains = tuple(domains or ())
    if not (
        cookies_clean.startswith("#")
        or any(domain in cookies_clean for domain in domains)
    ):
        return ""
    if not cookies_clean.startswith("#"):
        cookies_clean = "# Netscape HTTP Cookie File\n" + cookies_clean
    return cookies_clean + "\n"


def decode_cookie_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        return ""
    try:
        return base64.b64decode(value).decode("utf-8").strip()
    except Exception:
        return ""


def platform_cookie_sources(prefix, domains, allow_no_cookies=True):
    sources = []
    seen = set()

    cookies_file = os.environ.get(f"{prefix}_COOKIES_FILE", "").strip()
    if cookies_file and Path(cookies_file).exists():
        sources.append({"label": f"{prefix}_COOKIES_FILE", "file": cookies_file})

    env_names = [f"{prefix}_COOKIES_TEXT", f"{prefix}_COOKIES_TEXT_B64"]
    for index in range(1, 8):
        env_names.extend([f"{prefix}_COOKIES_TEXT_{index}", f"{prefix}_COOKIES_TEXT_B64_{index}"])

    for name in env_names:
        raw = decode_cookie_env(name) if name.endswith("_B64") else os.environ.get(name, "")
        cookies_clean = normalize_cookies_text(raw, domains)
        if not cookies_clean:
            continue
        digest = hashlib.sha256(cookies_clean.encode("utf-8")).hexdigest()[:16]
        if digest in seen:
            continue
        seen.add(digest)
        path = RUNTIME_COOKIES_DIR / f"{digest}.txt"
        try:
            path.write_text(cookies_clean, encoding="utf-8")
            sources.append({"label": name, "file": str(path), "length": len(cookies_clean)})
        except OSError:
            continue

    fallback_env = os.environ.get(f"{prefix}_ALLOW_NO_COOKIES_FALLBACK", "1" if allow_no_cookies else "0")
    if fallback_env.strip().lower() not in {"0", "false", "no"}:
        sources.append({"label": "NO_COOKIES", "file": ""})

    return sources or [{"label": "NO_COOKIES", "file": ""}]


def youtube_cookie_sources():
    return platform_cookie_sources("YOUTUBE", ("youtube.com", ".youtube.com", "google.com", ".google.com"))


def instagram_cookie_sources():
    return platform_cookie_sources("INSTAGRAM", ("instagram.com", ".instagram.com"))


def youtube_po_tokens():
    values = []
    for name in ("YOUTUBE_PO_TOKEN", "YOUTUBE_PO_TOKEN_1", "YOUTUBE_PO_TOKEN_2", "YOUTUBE_PO_TOKEN_3"):
        value = os.environ.get(name, "").strip()
        if value:
            values.append(value)
    raw = os.environ.get("YOUTUBE_PO_TOKENS", "").strip()
    if raw:
        values.extend([item.strip() for item in raw.split(",") if item.strip()])
    return list(dict.fromkeys(values))


def youtube_extractor_args(client):
    youtube_args = {
        "player_client": [client],
        "lang": ["en"],
    }
    if client in {"web", "mweb"}:
        youtube_args["player_skip"] = ["configs"]
    elif client == "tv":
        youtube_args["player_client"] = ["tv_embedded"]
        youtube_args["player_skip"] = ["dash", "configs"]

    visitor_data = os.environ.get("YOUTUBE_VISITOR_DATA", "").strip()
    if visitor_data:
        youtube_args["visitor_data"] = [visitor_data]

    tokens = youtube_po_tokens()
    if tokens:
        youtube_args["po_token"] = tokens

    return {"youtube": youtube_args, "youtubetab": {"skip": ["webpage"]}}


def ytdlp_base_opts(client="web", cookie_source=None):
    """Generate base yt-dlp options with advanced client emulation for YouTube blocking avoidance."""
    user_agents = {
        "web": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "mweb": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
        "tv": "Mozilla/5.0 (CrKey armv7l 1.54.192706) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }
    
    # Comprehensive HTTP headers to mimic real browser
    http_headers = {
        "User-Agent": user_agents.get(client, user_agents["web"]),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="125", "Chromium";v="125"',
        "Sec-Ch-Ua-Mobile": "?1" if client == "mweb" else "?0",
        "Sec-Ch-Ua-Platform": '"Android"' if client == "mweb" else '"Windows"',
    }
    
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": QuietYtdlpLogger(),
        "ignoreconfig": True,
        "noplaylist": True,
        "cachedir": False,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "skip_unavailable_fragments": True,
        "nocheckcertificate": True,
        "http_headers": http_headers,
    }
    
    opts["extractor_args"] = youtube_extractor_args(client)
    
    # Add request delay to avoid rate limiting
    opts["postprocessor_args"] = {
        "ffmpeg_o": ["-hide_banner", "-loglevel", "error"]
    }
    
    if cookie_source is None:
        cookie_source = youtube_cookie_sources()[0]
    if cookie_source.get("file"):
        opts["cookiefile"] = cookie_source["file"]
    
    return opts


def youtube_cookies_text():
    for source in youtube_cookie_sources():
        if source.get("file"):
            try:
                return Path(source["file"]).read_text(encoding="utf-8").strip()
            except OSError:
                continue
    return ""


def youtube_cookie_status():
    sources = [source for source in youtube_cookie_sources() if source["label"] != "NO_COOKIES"]
    return platform_cookie_status("YOUTUBE", sources)


def platform_cookie_status(prefix, sources):
    cookies_file = os.environ.get(f"{prefix}_COOKIES_FILE", "")
    cookies_text_raw = os.environ.get(f"{prefix}_COOKIES_TEXT", "")
    cookies_b64 = os.environ.get(f"{prefix}_COOKIES_TEXT_B64", "")
    cookies_ready = bool(sources)
    return {
        "cookies_file_configured": bool(cookies_file),
        "cookies_file_exists": bool(cookies_file and Path(cookies_file).exists()),
        "cookies_text_configured": bool(cookies_text_raw.strip()),
        "cookies_text_b64_configured": bool(cookies_b64.strip()),
        "cookie_profiles": [source["label"] for source in sources],
        "cookie_profile_count": len(sources),
        "cookies_ready": cookies_ready,
        "po_token_configured": bool(youtube_po_tokens()),
        "visitor_data_configured": bool(os.environ.get("YOUTUBE_VISITOR_DATA", "").strip()),
        "yt_dlp_version": YTDLP_VERSION,
        "cookies_problem": "" if cookies_ready else f"Set {prefix}_COOKIES_TEXT_1, {prefix}_COOKIES_TEXT_2, and {prefix}_COOKIES_TEXT_3 in Railway backend service variables, then redeploy.",
    }


def instagram_cookie_status():
    sources = [source for source in instagram_cookie_sources() if source["label"] != "NO_COOKIES"]
    status = platform_cookie_status("INSTAGRAM", sources)
    status.pop("po_token_configured", None)
    status.pop("visitor_data_configured", None)
    return status


def extract_info_safe(url, download=False, extra_opts=None, client="web", cookie_source=None):
    opts = {**ytdlp_base_opts(client=client, cookie_source=cookie_source), **(extra_opts or {})}
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
        permalink = f"https://www.instagram.com/{media_type}/{shortcode_match.group(1)}/"
    else:
        permalink = url
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
        "embed_type": "instagram" if embed_url else "",
        "permalink": permalink,
        "preview_note": "Instagram preview is shown through an embed when direct thumbnail metadata is blocked." if embed_url else (reason or "Limited preview. The site may require login or block metadata."),
    }


def clean_url(value):
    value = (value or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ApiError("Please enter a valid public URL.")
    return value


def extract_youtube_video_id(value):
    parsed = urlparse(value)
    host = parsed.netloc.lower().replace("www.", "").replace("m.", "")
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
        return video_id if re.fullmatch(r"[\w-]{11}", video_id or "") else None
    if "youtube.com" not in host:
        return None
    query_id = parse_qs(parsed.query).get("v", [""])[0]
    if re.fullmatch(r"[\w-]{11}", query_id or ""):
        return query_id
    for marker in ("/shorts/", "/embed/", "/live/"):
        if marker in parsed.path:
            video_id = parsed.path.split(marker, 1)[1].split("/", 1)[0]
            return video_id if re.fullmatch(r"[\w-]{11}", video_id or "") else None
    return None


def media_cache_key(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    if "instagram.com" in host:
        match = re.search(r"/(reel|p|tv)/([^/?#]+)/?", parsed.path)
        if match:
            return f"instagram:{match.group(1)}:{match.group(2)}"
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def cache_media_info(url, info):
    _media_info_cache[media_cache_key(url)] = {"time": time.time(), "info": info}


def cached_media_info(url):
    item = _media_info_cache.get(media_cache_key(url))
    if not item:
        return None
    if time.time() - item["time"] > MEDIA_INFO_CACHE_SECONDS:
        _media_info_cache.pop(media_cache_key(url), None)
        return None
    return item["info"]


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
        "preview_url": public_download_url(path.name),
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
    youtube_url = is_youtube_url(url)
    instagram_url = is_instagram_url(url)
    clients = ["web", "mweb", "tv"] if youtube_url else ["web"]
    if youtube_url:
        cookie_sources = youtube_cookie_sources()
    elif instagram_url:
        cookie_sources = instagram_cookie_sources()
    else:
        cookie_sources = [{"label": "NO_COOKIES", "file": ""}]
    attempts = [(cookie_source, client) for cookie_source in cookie_sources for client in clients]
    last_error = None
    for attempt_idx, (cookie_source, client) in enumerate(attempts):
        try:
            info, _ = extract_info_safe(
                url,
                download=False,
                client=client,
                cookie_source=cookie_source,
                extra_opts={"skip_download": True},
            )
            break
        except ApiError as error:
            last_error = error
            if youtube_url and is_youtube_block_error(error.message) and attempt_idx < len(attempts) - 1:
                time.sleep(1)
                continue
            if instagram_url and is_auth_block_error(error.message) and attempt_idx < len(attempts) - 1:
                time.sleep(1)
                continue
            if attempt_idx < len(attempts) - 1:
                continue
            raise
    else:
        raise last_error or ApiError("Could not fetch preview.", 400)
    if is_instagram_url(url):
        cache_media_info(url, info)
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


def postprocess_cutout(path, feather=2, background="transparent", hd_mode=False):
    """Minimal cutout post-processing to preserve content."""
    with Image.open(path) as img:
        rgba = img.convert("RGBA")
        
        # Get alpha channel
        alpha_channel = rgba.split()[3]
        
        # Apply light feathering only
        if feather > 0:
            alpha_channel = alpha_channel.filter(ImageFilter.GaussianBlur(min(feather, 4) * 0.3))
        
        # Apply refined alpha
        rgba.putalpha(alpha_channel)
        
        # Apply background if needed
        if background != "transparent":
            colors = {
                "white": (255, 255, 255, 255),
                "black": (10, 13, 20, 255),
                "blue": (37, 99, 235, 255),
            }
            canvas = Image.new("RGBA", rgba.size, colors.get(background, (255, 255, 255, 255)))
            canvas.alpha_composite(rgba)
            rgba = canvas
        
        # Save with best quality settings
        rgba.save(path, "PNG", optimize=False)  # Disable PIL optimization to preserve quality


def refine_cutout_alpha(alpha, feather=1):
    """Original refinement function - kept for compatibility."""
    if feather > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(min(feather, 6) * 0.45))
    return alpha.point(lambda p: 0 if p < 6 else 255 if p > 250 else p)


def refine_cutout_alpha_advanced(alpha, rgb, feather=1, hd_mode=False):
    """
    Advanced alpha refinement with:
    - Multi-level edge smoothing
    - Halo removal
    - Jagged edge reduction
    - Anti-aliasing
    - Contour rendering
    """
    import numpy as np
    
    # Convert to numpy for advanced processing
    alpha_array = np.array(alpha, dtype=np.float32)
    rgb_array = np.array(rgb, dtype=np.float32)
    height, width = alpha_array.shape
    
    # Step 1: Transparent pixel cleanup - identify and clean isolated noise
    alpha_clean = cleanup_transparent_pixels(alpha_array.copy())
    
    # Step 2: Adaptive threshold for better boundary detection
    alpha_clean = adaptive_alpha_threshold(alpha_clean)
    
    # Step 3: Advanced edge refinement with morphological operations
    alpha_edges = refine_edges_morphological(alpha_clean)
    
    # Step 4: Color-aware edge blending for smooth transitions
    if rgb_array is not None:
        alpha_edges = color_aware_edge_blend(alpha_edges, rgb_array)
    
    # Step 5: Anti-aliasing for smooth contours
    alpha_edges = apply_antialiasing(alpha_edges)
    
    # Step 6: Gaussian blur for feathering (feather range 0-8)
    if feather > 0:
        sigma = min(feather * 0.35, 2.8)  # Optimized sigma for edge smoothing
        alpha_smooth = gaussian_blur_numpy(alpha_edges, sigma)
    else:
        alpha_smooth = alpha_edges
    
    # Step 7: Halo removal - reduce white outlines
    alpha_dehalo = remove_halo_effect(alpha_smooth)
    
    # Step 8: HD mode - additional refinement passes for cleaner cutout
    if hd_mode:
        alpha_dehalo = apply_hd_refinement(alpha_dehalo, rgb_array)
    
    # Step 9: Final alpha channel refinement with proper thresholding
    final_alpha = finalize_alpha_channel(alpha_dehalo)
    
    # Convert back to PIL Image
    final_alpha_uint8 = np.uint8(np.clip(final_alpha * 255, 0, 255))
    return Image.fromarray(final_alpha_uint8, mode='L')


def cleanup_transparent_pixels(alpha_array):
    """Remove isolated noise and create clean transparent regions."""
    import numpy as np
    import scipy.ndimage
    
    # Create binary mask (0 for transparent, 1 for opaque)
    binary = (alpha_array > 30).astype(np.float32)
    
    # Remove small isolated regions (noise cleanup)
    labeled, num_features = scipy.ndimage.label(binary)
    sizes = scipy.ndimage.sum(binary, labeled, range(num_features + 1))
    
    # Keep only regions larger than minimum threshold
    min_region_size = max(10, alpha_array.size // 10000)
    cleaned = np.zeros_like(binary)
    for i in range(1, num_features + 1):
        if sizes[i] > min_region_size:
            cleaned[labeled == i] = 1
    
    # Also clean very small transparent islands inside opaque regions
    binary_inv = 1 - cleaned
    labeled_inv, num_features_inv = scipy.ndimage.label(binary_inv)
    sizes_inv = scipy.ndimage.sum(binary_inv, labeled_inv, range(num_features_inv + 1))
    
    for i in range(1, num_features_inv + 1):
        if sizes_inv[i] < min_region_size:
            cleaned[labeled_inv == i] = 1
    
    return cleaned * alpha_array.max()


def adaptive_alpha_threshold(alpha_array):
    """Apply adaptive thresholding for better boundary detection."""
    import numpy as np
    import scipy.ndimage
    
    alpha_norm = alpha_array / 255.0
    
    # Calculate local mean for adaptive thresholding
    kernel_size = max(5, min(21, alpha_array.shape[0] // 50))
    if kernel_size % 2 == 0:
        kernel_size += 1
    
    # Compute local statistics using morphology
    from scipy import ndimage
    local_mean = ndimage.uniform_filter(alpha_norm, size=kernel_size)
    local_var = ndimage.uniform_filter(alpha_norm**2, size=kernel_size) - local_mean**2
    local_std = np.sqrt(np.maximum(local_var, 0))
    
    # Adaptive threshold: pixel > local_mean + 0.5*local_std
    threshold_map = local_mean + 0.3 * local_std
    adaptive_binary = (alpha_norm > threshold_map).astype(np.float32)
    
    # Blend original with adaptive for smooth transition
    result = alpha_norm * 0.6 + adaptive_binary * 0.4
    return result


def refine_edges_morphological(alpha_array):
    """Apply morphological operations to refine edges."""
    import numpy as np
    import scipy.ndimage
    from scipy import ndimage
    
    alpha_norm = alpha_array / 255.0
    
    # Create binary mask for operations
    binary = (alpha_norm > 0.5).astype(np.float32)
    
    # Morphological closing: remove small holes
    structure = np.ones((3, 3))
    closed = ndimage.binary_closing(binary, structure=structure, iterations=1).astype(np.float32)
    
    # Morphological opening: remove small artifacts on edges
    opened = ndimage.binary_opening(closed, structure=structure, iterations=1).astype(np.float32)
    
    # Gradient for edge detection
    gradient = ndimage.gaussian_gradient_magnitude(alpha_norm, sigma=0.5)
    
    # Enhance edges where there's high gradient
    edge_boost = 1.0 + (gradient * 0.3)
    
    # Blend original with processed
    result = (opened * edge_boost) * alpha_norm + (alpha_norm * 0.1)
    return np.clip(result, 0, 1)


def color_aware_edge_blend(alpha_array, rgb_array):
    """Blend edges based on color information for smooth transitions."""
    import numpy as np
    from scipy import ndimage
    
    alpha_norm = alpha_array / 255.0 if alpha_array.max() > 1 else alpha_array
    
    # Calculate color gradients
    r_grad = ndimage.gaussian_gradient_magnitude(rgb_array[:, :, 0], sigma=0.5)
    g_grad = ndimage.gaussian_gradient_magnitude(rgb_array[:, :, 1], sigma=0.5)
    b_grad = ndimage.gaussian_gradient_magnitude(rgb_array[:, :, 2], sigma=0.5)
    color_grad = (r_grad + g_grad + b_grad) / 3.0
    
    # Normalize color gradient
    color_grad = color_grad / (np.max(color_grad) + 1e-6)
    
    # Adaptive blending based on color variation
    # Smoother blending in areas with color gradients (edges)
    blend_factor = 0.7 + (color_grad * 0.3)
    result = alpha_norm * blend_factor
    
    return np.clip(result, 0, 1)


def apply_antialiasing(alpha_array):
    """Apply anti-aliasing filter to reduce jagged edges."""
    import numpy as np
    from scipy import ndimage
    
    alpha_norm = alpha_array / 255.0 if alpha_array.max() > 1 else alpha_array
    
    # Apply edge-aware bilateral-like filter
    # Use multiple Gaussian passes at different scales
    smooth_1 = ndimage.gaussian_filter(alpha_norm, sigma=0.5)
    smooth_2 = ndimage.gaussian_filter(alpha_norm, sigma=1.2)
    smooth_3 = ndimage.gaussian_filter(alpha_norm, sigma=0.8)
    
    # Weighted blend for anti-aliasing
    result = smooth_1 * 0.4 + smooth_2 * 0.3 + smooth_3 * 0.3
    return result


def gaussian_blur_numpy(alpha_array, sigma):
    """High-quality Gaussian blur using numpy/scipy."""
    import numpy as np
    from scipy import ndimage
    
    alpha_norm = alpha_array / 255.0 if alpha_array.max() > 1 else alpha_array
    blurred = ndimage.gaussian_filter(alpha_norm, sigma=sigma)
    return blurred


def remove_halo_effect(alpha_array):
    """Remove white outlines/halo around edges."""
    import numpy as np
    from scipy import ndimage
    
    alpha_norm = alpha_array / 255.0 if alpha_array.max() > 1 else alpha_array
    
    # Detect halo regions: semi-transparent pixels at boundaries
    # Halo typically shows as intermediate alpha values (100-200)
    binary_strong = (alpha_norm > 0.85).astype(np.float32)
    binary_weak = (alpha_norm > 0.35).astype(np.float32)
    binary_halo = (binary_weak - binary_strong) > 0
    
    # Apply controlled dilation to preserve soft edges
    structure = np.ones((3, 3))
    halo_region = ndimage.binary_dilation(binary_halo, structure=structure, iterations=1).astype(np.float32)
    
    # Calculate proper alpha for halo region to match nearby strong alpha
    strong_dilated = ndimage.binary_dilation(binary_strong, structure=structure, iterations=2).astype(np.float32)
    
    # Smooth transition from strong to weak
    transition = ndimage.gaussian_filter(alpha_norm * strong_dilated, sigma=1.5)
    
    # Replace halo with smooth transition
    result = alpha_norm.copy()
    halo_mask = halo_region > 0
    result[halo_mask] = np.minimum(result[halo_mask], transition[halo_mask] * 0.95)
    
    return result


def apply_hd_refinement(alpha_array, rgb_array):
    """Apply additional refinement for HD mode cleaner cutouts."""
    import numpy as np
    from scipy import ndimage
    
    alpha_norm = alpha_array / 255.0 if alpha_array.max() > 1 else alpha_array
    
    # Additional edge enhancement
    edges = ndimage.sobel(alpha_norm)
    edge_mask = edges > np.percentile(edges, 80)
    
    # Sharpen edges
    edge_sharpening = ndimage.laplace(alpha_norm)
    sharpened = alpha_norm - (edge_sharpening * 0.1)
    
    # Enhance clarity at boundaries
    result = alpha_norm * 0.85 + sharpened * 0.15
    
    return np.clip(result, 0, 1)


def finalize_alpha_channel(alpha_array):
    """Final processing to prepare alpha channel - keep it simple to preserve content."""
    import numpy as np
    
    alpha_norm = alpha_array / 255.0 if alpha_array.max() > 1 else alpha_array
    
    # Apply gentle Gaussian blur for smoothing without destroying content
    from scipy import ndimage
    blurred = ndimage.gaussian_filter(alpha_norm, sigma=0.3)
    
    # Gentle threshold to clean up very noisy pixels only
    result = np.where(blurred < 0.02, 0, blurred)
    
    return np.clip(result, 0, 1)


def cutout_has_useful_alpha(path):
    try:
        with Image.open(path) as img:
            alpha = img.convert("RGBA").getchannel("A")
            if not alpha.getbbox():
                return False
            hist = alpha.histogram()
            visible = sum(hist[8:])
            total = alpha.width * alpha.height
            visible_ratio = visible / max(1, total)
            return 0.015 <= visible_ratio <= 0.96
    except Exception:
        return False


def rembg_model_for_mode(mode):
    return REMBG_MODEL_DEFAULT


def get_rembg_session(model_name):
    if rembg_new_session is None:
        return None
    with _rembg_session_lock:
        if model_name not in _rembg_sessions:
            app.logger.info(f"Loading rembg model session: {model_name}")
            _rembg_sessions[model_name] = rembg_new_session(model_name)
        return _rembg_sessions[model_name]


def remove_background_ai(source, out, feather=1, background="transparent", mode="ai", hd_mode=False):
    if remove_background is None:
        raise ApiError(f"Remove background AI dependency is unavailable: {_rembg_import_error}", 500)
    
    with Image.open(source) as img:
        original = ImageOps.exif_transpose(img).convert("RGBA")
    
    working = original.copy()
    original_size = working.size
    
    # For HD mode, process at higher resolution for better quality
    if hd_mode:
        max_side = min(1024, REMBG_MAX_SIDE * 2)
    else:
        max_side = REMBG_MAX_SIDE
    
    if max(working.size) > max_side:
        working.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    
    model_name = rembg_model_for_mode(mode)
    session = get_rembg_session(model_name)
    kwargs = {"session": session, "post_process_mask": True} if session is not None else {"post_process_mask": True}
    
    # Enable alpha_matting with balanced parameters
    kwargs["alpha_matting"] = True
    kwargs["alpha_matting_foreground_threshold"] = 150
    kwargs["alpha_matting_background_threshold"] = 5
    
    result = remove_background(working, **kwargs)
    
    if isinstance(result, (bytes, bytearray)):
        with Image.open(io.BytesIO(result)) as result_img:
            cutout = result_img.convert("RGBA")
    else:
        cutout = result.convert("RGBA")
    
    alpha = cutout.getchannel("A")
    
    # Resize alpha to match original size if needed
    if alpha.size != original_size:
        alpha = alpha.resize(original_size, Image.Resampling.LANCZOS)
    
    original.putalpha(alpha)
    
    # Save with high quality settings
    original.save(out, "PNG", optimize=False)
    
    if not cutout_has_useful_alpha(out):
        raise ApiError("AI cutout returned an empty or invalid mask.", 500)
    
    # Apply basic post-processing with minimal feathering
    postprocess_cutout(out, feather=feather, background=background, hd_mode=hd_mode)


def warm_removebg_model():
    if os.environ.get("REMBG_WARMUP", "1").strip().lower() in {"0", "false", "no", "off"}:
        return
    if remove_background is None:
        app.logger.warning(f"RemoveBG warmup skipped: {_rembg_import_error}")
        return
    try:
        session = get_rembg_session(REMBG_MODEL_DEFAULT)
        probe_size = max(128, min(REMBG_MAX_SIDE, 512))
        probe = Image.new("RGBA", (probe_size, probe_size), (255, 255, 255, 255))
        draw = ImageDraw.Draw(probe)
        margin = max(16, probe_size // 5)
        draw.ellipse((margin, margin // 2, probe_size - margin, probe_size - margin // 2), fill=(37, 99, 235, 255))
        remove_background(probe, session=session, post_process_mask=True)
        app.logger.info(f"RemoveBG model warmed: {REMBG_MODEL_DEFAULT}")
    except Exception as error:
        app.logger.exception(f"RemoveBG warmup failed: {str(error)[:200]}")


warm_removebg_model()


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


def downloaded_video_details(info):
    downloads = info.get("requested_downloads") or []
    video_parts = [item for item in downloads if item.get("vcodec") and item.get("vcodec") != "none"]
    selected = video_parts[0] if video_parts else info
    height = selected.get("height") or info.get("height")
    width = selected.get("width") or info.get("width")
    fps = selected.get("fps") or info.get("fps")
    codec = selected.get("vcodec") or info.get("vcodec")
    format_id = selected.get("format_id") or info.get("format_id")
    return {
        "video_width": width,
        "video_height": height,
        "video_fps": fps,
        "video_codec": codec,
        "format_id": format_id,
    }


def requested_video_height(quality):
    quality_value = str(quality or "best").lower()
    height = re.sub(r"[^0-9]", "", quality_value)
    if quality_value == "best" or not height:
        return None
    return max(144, min(4320, int(height)))


def format_number(value, default=0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


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


def choose_available_video_format(info, quality, has_ffmpeg):
    requested_height = requested_video_height(quality)
    formats = info.get("formats") or []
    videos = [
        item for item in formats
        if item.get("format_id")
        and item.get("vcodec")
        and item.get("vcodec") != "none"
        and format_number(item.get("height")) > 0
    ]
    audios = [
        item for item in formats
        if item.get("format_id")
        and item.get("acodec")
        and item.get("acodec") != "none"
        and (not item.get("vcodec") or item.get("vcodec") == "none")
    ]
    progressive = [
        item for item in videos
        if item.get("acodec") and item.get("acodec") != "none"
    ]
    if requested_height:
        limited_videos = [item for item in videos if format_number(item.get("height")) <= requested_height]
        limited_progressive = [item for item in progressive if format_number(item.get("height")) <= requested_height]
    else:
        limited_videos = videos
        limited_progressive = progressive

    selected = max(limited_videos or videos, key=video_format_score, default=None)
    if not selected:
        return ytdlp_video_format(quality, has_ffmpeg)[0], "", None

    selected_height = int(format_number(selected.get("height")))
    note = ""
    if requested_height and selected_height and selected_height != requested_height:
        note = f"Downloaded {selected_height}p because {requested_height}p was not available."

    selected_id = selected["format_id"]
    if has_ffmpeg:
        if selected.get("acodec") and selected.get("acodec") != "none":
            return f"{selected_id}/b", note, selected_height
        audio = max(audios, key=audio_format_score, default=None)
        if audio:
            return f"{selected_id}+{audio['format_id']}/{selected_id}/b", note, selected_height
        return f"{selected_id}/b", note, selected_height

    progressive_selected = max(limited_progressive or progressive, key=video_format_score, default=None)
    if progressive_selected:
        progressive_height = int(format_number(progressive_selected.get("height")))
        if requested_height and progressive_height and progressive_height != requested_height:
            note = f"Downloaded {progressive_height}p because {requested_height}p was not available without FFmpeg merge."
        return f"{progressive_selected['format_id']}/b", note, progressive_height
    return "b", "Downloaded best available single-file quality because FFmpeg merge is not available.", None


def ytdlp_video_format(quality, has_ffmpeg):
    quality_value = str(quality or "best").lower()
    height = re.sub(r"[^0-9]", "", quality_value)
    if quality_value == "best" or not height:
        return "bv*+ba/b" if has_ffmpeg else "b", None
    height = str(max(144, min(4320, int(height))))
    if has_ffmpeg:
        return f"bv*[height<={height}]+ba/b[height<={height}]/bv*+ba/b", height
    return f"b[height<={height}]/b", height


def best_direct_video_format(info, quality):
    """Select best video format, prioritizing formats with audio for Instagram."""
    formats = info.get("formats") or []
    videos = [
        item for item in formats
        if item.get("url")
        and item.get("vcodec")
        and item.get("vcodec") != "none"
        and format_number(item.get("height")) > 0
    ]
    
    # Separate formats with and without audio
    videos_with_audio = [
        item for item in videos
        if item.get("acodec") and item.get("acodec") != "none"
    ]
    
    requested_height = requested_video_height(quality)
    
    # First try to find format with audio at requested quality
    if videos_with_audio:
        if requested_height:
            limited_with_audio = [item for item in videos_with_audio if format_number(item.get("height")) <= requested_height]
            selected = max(limited_with_audio or videos_with_audio, key=video_format_score, default=None)
        else:
            selected = max(videos_with_audio, key=video_format_score, default=None)
        
        if selected:
            return selected
    
    # Fallback to any video format if no audio version found
    if requested_height:
        limited = [item for item in videos if format_number(item.get("height")) <= requested_height]
    else:
        limited = videos
    selected = max(limited or videos, key=video_format_score, default=None)
    if selected:
        return selected
    if info.get("url"):
        return info
    return None


def direct_instagram_download_from_cache(url, quality):
    info = cached_media_info(url)
    if not info:
        return None
    selected = best_direct_video_format(info, quality)
    if not selected:
        return None
    media_url = selected.get("url")
    headers = {
        "User-Agent": ytdlp_base_opts()["http_headers"]["User-Agent"],
        "Referer": info.get("webpage_url") or url,
        "Accept": "*/*",
    }
    headers.update(selected.get("http_headers") or {})
    title = secure_filename((info.get("title") or "instagram_reel")[:80]) or "instagram_reel"
    ext = (selected.get("ext") or "mp4").split("-", 1)[0]
    if ext not in {"mp4", "mov", "webm", "m4v"}:
        ext = "mp4"
    path = DOWNLOAD_DIR / f"{make_id()}_{title}.{ext}"
    try:
        with requests.get(media_url, headers=headers, timeout=60, stream=True, verify=certifi.where()) as response:
            response.raise_for_status()
            with path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        handle.write(chunk)
    except requests.exceptions.SSLError:
        with requests.get(media_url, headers=headers, timeout=60, stream=True, verify=False) as response:
            response.raise_for_status()
            with path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        handle.write(chunk)
    except Exception:
        delete_quietly(path)
        return None
    if not path.exists() or path.stat().st_size < 1024:
        delete_quietly(path)
        return None
    height = selected.get("height") or info.get("height")
    note = "Downloaded from the preview session to avoid Instagram login re-checks."
    if requested_video_height(quality) and height and int(format_number(height)) != requested_video_height(quality):
        note = f"Downloaded {int(format_number(height))}p from the preview session because Instagram did not expose the requested quality."
    return {
        "success": True,
        "title": info.get("title") or "Instagram reel",
        "filename": path.name,
        "file_size": path.stat().st_size,
        "download_url": public_download_url(path.name),
        "download_label": "Download video",
        "note": note,
        "video_width": selected.get("width") or info.get("width"),
        "video_height": height,
        "video_fps": selected.get("fps") or info.get("fps"),
        "video_codec": selected.get("vcodec") or info.get("vcodec"),
        "format_id": selected.get("format_id") or info.get("format_id"),
    }


def run_yt_dlp(url, mode, quality="1080"):
    if mode == "video" and is_instagram_url(url):
        cached_download = direct_instagram_download_from_cache(url, quality)
        if cached_download:
            return cached_download

    output_prefix = make_id()
    output_template = str(DOWNLOAD_DIR / f"{output_prefix}_%(title).80s.%(ext)s")
    youtube_url = is_youtube_url(url)
    instagram_url = is_instagram_url(url)
    clients = ["web", "mweb", "tv"] if youtube_url else ["web"]
    if youtube_url:
        cookie_sources = youtube_cookie_sources()
    elif instagram_url:
        cookie_sources = instagram_cookie_sources()
    else:
        cookie_sources = [{"label": "NO_COOKIES", "file": ""}]
    attempts = [(cookie_source, client) for cookie_source in cookie_sources for client in clients]
    last_error = None
    info = None
    ydl = None
    fallback_note = ""
    quality_note = ""
    
    import random
    
    for attempt_idx, (cookie_source, client) in enumerate(attempts):
        try:
            # Add progressive delay between attempts to avoid rate limiting
            if attempt_idx > 0:
                # Progressive delay: 1-2s for first retry, 2-3s for second, etc.
                base_delay = min(attempt_idx * 0.8, 3.5)
                jitter = random.uniform(0.5, 1.5)
                delay = base_delay + jitter
                time.sleep(delay)
            
            common_opts = {
                **ytdlp_base_opts(client=client, cookie_source=cookie_source),
                "outtmpl": output_template,
                "restrictfilenames": True,
                "windowsfilenames": True,
            }
            fallback_note = ""
            
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
                has_ffmpeg = shutil.which("ffmpeg") is not None
                probe_info, _ = extract_info_safe(
                    url,
                    download=False,
                    client=client,
                    cookie_source=cookie_source,
                    extra_opts={"skip_download": True},
                )
                format_selector, quality_note, _height = choose_available_video_format(probe_info, quality, has_ffmpeg)
                ydl_opts = {
                    **common_opts,
                    "format": format_selector,
                }
                if has_ffmpeg:
                    ydl_opts["merge_output_format"] = "mp4"

            try:
                info, ydl = extract_info_safe(
                    url,
                    download=True,
                    client=client,
                    cookie_source=cookie_source,
                    extra_opts=ydl_opts,
                )
                break  # Success with this client
            except ApiError as error:
                format_error = (
                    "Requested quality is not available" in error.message
                    or "did not expose downloadable formats" in error.message
                )
                if youtube_url and is_youtube_block_error(error.message) and attempt_idx < len(attempts) - 1:
                    last_error = error
                    time.sleep(1)
                    continue
                if instagram_url and is_auth_block_error(error.message) and attempt_idx < len(attempts) - 1:
                    last_error = error
                    time.sleep(1)
                    continue
                if mode != "audio" and format_error and attempt_idx < len(attempts) - 1:
                    last_error = error
                    time.sleep(1)
                    continue
                elif mode != "audio" and format_error:
                    # Last client, try best format fallback
                    ydl_opts["format"] = "bv*+ba/b" if shutil.which("ffmpeg") else "b"
                    fallback_note = "Downloaded best available quality from the formats exposed by the source."
                    try:
                        info, ydl = extract_info_safe(
                            url,
                            download=True,
                            client=client,
                            cookie_source=cookie_source,
                            extra_opts=ydl_opts,
                        )
                        break
                    except ApiError as fallback_error:
                        last_error = fallback_error
                        if attempt_idx < len(attempts) - 1:
                            time.sleep(1)
                            continue
                        if is_youtube_block_error(fallback_error.message):
                            status = youtube_cookie_status()
                            raise ApiError(
                                f"YouTube is blocking this server after {len(attempts)} attempts. "
                                f"Cookie profiles configured: {status['cookie_profile_count']}. "
                                "Add 2-3 fresh cookie profiles and optional YOUTUBE_PO_TOKEN/YOUTUBE_VISITOR_DATA, then redeploy.",
                                429,
                            ) from fallback_error
                        if instagram_url and is_auth_block_error(fallback_error.message):
                            status = instagram_cookie_status()
                            raise ApiError(
                                f"Instagram is asking this server to log in after {len(attempts)} attempts. "
                                f"Cookie profiles configured: {status['cookie_profile_count']}. "
                                "Add 2-3 fresh Instagram cookie profiles in Railway Variables, then redeploy.",
                                429,
                            ) from fallback_error
                        raise
                else:
                    last_error = error
                    if attempt_idx < len(attempts) - 1:
                        time.sleep(1)
                        continue
                    if instagram_url and is_auth_block_error(error.message):
                        status = instagram_cookie_status()
                        raise ApiError(
                            f"Instagram is asking this server to log in after {len(attempts)} attempts. "
                            f"Cookie profiles configured: {status['cookie_profile_count']}. "
                            "Add 2-3 fresh Instagram cookie profiles in Railway Variables, then redeploy.",
                            429,
                        ) from error
                    raise
        except Exception as e:
            last_error = e
            if attempt_idx < len(attempts) - 1:
                time.sleep(1)
                continue
            if instagram_url and isinstance(e, ApiError) and is_auth_block_error(e.message):
                status = instagram_cookie_status()
                raise ApiError(
                    f"Instagram is asking this server to log in after {len(attempts)} attempts. "
                    f"Cookie profiles configured: {status['cookie_profile_count']}. "
                    "Add 2-3 fresh Instagram cookie profiles in Railway Variables, then redeploy.",
                    429,
                ) from e
            raise
    
    if not info or not ydl:
        raise last_error or ApiError("Could not download this media.", 400)

    if mode != "audio" and not fallback_note:
        fallback_note = quality_note
    
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
    details = downloaded_video_details(info) if mode != "audio" else {}
    return {
        "success": True,
        "title": info.get("title", "Downloaded file"),
        "filename": file_path.name,
        "file_size": file_path.stat().st_size,
        "download_url": public_download_url(file_path.name),
        "download_label": "Download MP3" if mode == "audio" else "Download video",
        "note": fallback_note,
        **details,
    }


@app.route("/")
def home():
    return seo_html("index.html")


def site_url():
    configured = os.environ.get("SITE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    host = request.host.split(",", 1)[0]
    if "thugtools.xyz" in host:
        return f"https://{host}"
    return request.host_url.rstrip("/")


def absolute_url(path):
    if path.startswith(("http://", "https://")):
        return path
    return f"{site_url()}{path if path.startswith('/') else '/' + path}"


def first_match(pattern, text, default=""):
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return unescape(match.group(1).strip()) if match else default


def json_ld_script(data):
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "</script>"


def html_attr(value):
    return escape(str(value), quote=True)


def base_schema_graph(path="/", title=None, description=None):
    url = absolute_url(path)
    image = absolute_url(DEFAULT_IMAGE)
    title = title or SITE_NAME
    description = description or SITE_DESCRIPTION
    return [
        {
            "@type": "Organization",
            "@id": absolute_url("/#organization"),
            "name": SITE_NAME,
            "url": absolute_url("/"),
            "logo": {"@type": "ImageObject", "url": image, "width": 512, "height": 512},
            "description": SITE_DESCRIPTION,
            "contactPoint": {"@type": "ContactPoint", "email": "thugtoolscontact@gmail.com", "contactType": "customer support"},
        },
        {
            "@type": "WebSite",
            "@id": absolute_url("/#website"),
            "name": SITE_NAME,
            "url": absolute_url("/"),
            "publisher": {"@id": absolute_url("/#organization")},
            "potentialAction": {
                "@type": "SearchAction",
                "target": {"@type": "EntryPoint", "urlTemplate": absolute_url("/?search={search_term_string}")},
                "query-input": "required name=search_term_string",
            },
        },
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": absolute_url("/")},
                {"@type": "ListItem", "position": 2, "name": title.replace(" | ThugTools", ""), "item": url},
            ] if path != "/" else [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": absolute_url("/")},
            ],
        },
    ]


def tool_schema(filename, title, description):
    config = TOOL_PAGE_SEO.get(filename)
    if not config:
        return []
    app_type = config.get("category", "WebApplication")
    faq_items = [
        {"@type": "Question", "name": question, "acceptedAnswer": {"@type": "Answer", "text": answer}}
        for question, answer in config.get("faqs", [])
    ]
    return [
        {
            "@type": "SoftwareApplication",
            "@id": absolute_url(config["path"] + "#software"),
            "name": title.replace(" | ThugTools", ""),
            "applicationCategory": app_type,
            "operatingSystem": "Any",
            "url": absolute_url(config["path"]),
            "description": description,
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            "publisher": {"@id": absolute_url("/#organization")},
        },
        {"@type": "FAQPage", "mainEntity": faq_items},
    ]


def inject_meta_and_schema(html, filename):
    config = TOOL_PAGE_SEO.get(filename)
    title = config.get("title") if config else first_match(r"<title>(.*?)</title>", html, SITE_NAME)
    description = config.get("description") if config else first_match(r'<meta name="description" content="([^"]*)"', html)
    path = config.get("path") if config else request.path
    keywords = config.get("keywords") if config else "free online tools, creator tools, image tools, video downloader, pdf tools, qr code generator"
    title_attr = html_attr(title)
    description_attr = html_attr(description)
    keywords_attr = html_attr(keywords)

    if config:
        html = re.sub(r"<title>.*?</title>", f"<title>{escape(title)}</title>", html, count=1, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r'(<meta name="description" content=")[^"]*(")', lambda m: f"{m.group(1)}{description_attr}{m.group(2)}", html, count=1, flags=re.IGNORECASE)
        html = re.sub(r'(<link rel="canonical" href=")[^"]*(")', lambda m: f"{m.group(1)}{absolute_url(path)}{m.group(2)}", html, count=1, flags=re.IGNORECASE)
        html = re.sub(r'(<meta property="og:title" content=")[^"]*(")', lambda m: f"{m.group(1)}{title_attr}{m.group(2)}", html, count=1, flags=re.IGNORECASE)
        html = re.sub(r'(<meta property="og:description" content=")[^"]*(")', lambda m: f"{m.group(1)}{description_attr}{m.group(2)}", html, count=1, flags=re.IGNORECASE)
        html = re.sub(r'(<meta property="og:url" content=")[^"]*(")', lambda m: f"{m.group(1)}{absolute_url(path)}{m.group(2)}", html, count=1, flags=re.IGNORECASE)
        html = re.sub(r'(<meta name="twitter:title" content=")[^"]*(")', lambda m: f"{m.group(1)}{title_attr}{m.group(2)}", html, count=1, flags=re.IGNORECASE)
        html = re.sub(r'(<meta name="twitter:description" content=")[^"]*(")', lambda m: f"{m.group(1)}{description_attr}{m.group(2)}", html, count=1, flags=re.IGNORECASE)

    if 'name="keywords"' not in html:
        html = html.replace("  <meta name=\"robots\"", f"  <meta name=\"keywords\" content=\"{keywords_attr}\">\n  <meta name=\"robots\"", 1)
    if 'name="author"' not in html:
        html = html.replace("  <meta name=\"robots\"", f"  <meta name=\"author\" content=\"{SITE_NAME}\">\n  <meta name=\"robots\"", 1)
    if 'rel="icon"' not in html:
        html = html.replace("</head>", '  <link rel="icon" href="/favicon.ico" sizes="any">\n  <link rel="icon" type="image/svg+xml" href="/favicon.svg">\n  <link rel="apple-touch-icon" href="/assets/site-logo.png">\n</head>', 1)
    if 'rel="preload" href="../style.css"' not in html and "../style.css" in html:
        html = html.replace('  <link rel="stylesheet" href="../style.css">', '  <link rel="preload" href="../style.css" as="style">\n  <link rel="stylesheet" href="../style.css">', 1)
    if 'rel="preload" href="style.css"' not in html and 'href="style.css"' in html:
        html = html.replace('  <link rel="stylesheet" href="style.css">', '  <link rel="preload" href="style.css" as="style">\n  <link rel="stylesheet" href="style.css">', 1)
    if "data-seo-schema" not in html and (config or 'application/ld+json' not in html):
        graph = base_schema_graph(path, title, description) + tool_schema(filename, title, description)
        schema = json_ld_script({"@context": "https://schema.org", "@graph": graph}).replace("<script ", '<script data-seo-schema ')
        html = html.replace("</head>", f"  {schema}\n</head>", 1)
    if 'G-PRQ6Z3GFZS' not in html:
        ga_script = """  <!-- Google tag (gtag.js) -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-PRQ6Z3GFZS"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
    gtag('js', new Date());

    gtag('config', 'G-PRQ6Z3GFZS');
  </script>"""
        html = html.replace("</head>", f"{ga_script}\n</head>", 1)
    return html


def list_items(items):
    return "".join(f"<li>{item}</li>" for item in items)


def enrich_tool_body(html, filename):
    config = TOOL_PAGE_SEO.get(filename)
    if not config or "seo-upgrade" in html:
        return html
    downloader_notice = ""
    if filename in {"youtube.html", "pinterest.html", "instagram.html", "thumbnail.html", "audio.html"}:
        downloader_notice = '<p class="safe-notice"><strong>Safe Usage Notice:</strong> Use ThugTools only with files and public URLs you own or are authorized to process. Respect copyright, privacy, and platform terms.</p>'
    related = "".join(f'<a href="{href}">{label}</a>' for href, label in config.get("related", []))
    faq = "".join(
        f"<details><summary>{question}</summary><p>{answer}</p></details>"
        for question, answer in config.get("faqs", [])
    )
    upgrade = f"""
    <section class="seo-upgrade" aria-label="{config['title'].split('|')[0].strip()} guide">
      <div class="seo-card">
        <h2>How to Use {config['title'].split(' - ')[0]}</h2>
        <ol>{list_items(config.get('how', []))}</ol>
      </div>
      <div class="seo-card">
        <h2>Key Features</h2>
        <ul>{list_items(config.get('features', []))}</ul>
      </div>
      <div class="seo-card seo-faq">
        <h2>Frequently Asked Questions</h2>
        {faq}
      </div>
      <div class="seo-card related-tools">
        <h2>Related Tools</h2>
        <div>{related}</div>
      </div>
      {downloader_notice}
    </section>"""
    return html.replace("  </div></main>", f"{upgrade}\n  </div></main>", 1)


def seo_html(filename, subdir=None):
    folder = FRONTEND_DIR / subdir if subdir else FRONTEND_DIR
    path = (folder / filename).resolve()
    if folder.resolve() not in path.parents or not path.exists():
        return send_from_directory(folder, filename)
    html = path.read_text(encoding="utf-8")
    html = re.sub(
        r'(<link rel="canonical" href=")(/[^"]*)(")',
        lambda match: f'{match.group(1)}{absolute_url(match.group(2))}{match.group(3)}',
        html,
    )
    html = re.sub(
        r'(<meta property="og:url" content=")(/[^"]*)(")',
        lambda match: f'{match.group(1)}{absolute_url(match.group(2))}{match.group(3)}',
        html,
    )
    html = re.sub(
        r'(<meta (?:property="og:image"|name="twitter:image") content=")(/[^"]*)(")',
        lambda match: f'{match.group(1)}{absolute_url(match.group(2))}{match.group(3)}',
        html,
    )
    html = re.sub(
        r'(<meta (?:property="og:image"|name="twitter:image") content=")[^"]*remove-bg-logo\.png(")',
        lambda match: f"{match.group(1)}{absolute_url(DEFAULT_IMAGE)}{match.group(2)}",
        html,
        flags=re.IGNORECASE,
    )
    html = inject_meta_and_schema(html, filename)
    html = enrich_tool_body(html, filename)
    return Response(html, mimetype="text/html")


@app.route("/robots.txt")
def robots_txt():
    base = site_url()
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /download/\n"
        "Disallow: /backend/\n"
        "Disallow: /uploads/\n\n"
        "User-agent: Googlebot\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /download/\n\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    base = site_url()
    today = time.strftime("%Y-%m-%d")
    urls = []
    for path, changefreq, priority in SEO_PAGES:
        urls.append(
            "  <url>\n"
            f"    <loc>{base}{path}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )
    body = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    body += "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
    body += "\n".join(urls)
    body += "\n</urlset>\n"
    return Response(body, mimetype="application/xml")


@app.route("/healthz")
def healthz():
    return jsonify({
        "success": True,
        "status": "ok",
        "removebg_model": REMBG_MODEL_DEFAULT,
        "removebg_max_side": REMBG_MAX_SIDE,
        "removebg_warmup_probe": max(128, min(REMBG_MAX_SIDE, 512)),
        "removebg_ready": REMBG_MODEL_DEFAULT in _rembg_sessions,
    })


@app.route("/api/youtube/status")
def youtube_status():
    return jsonify({
        "success": True,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffmpeg_path": shutil.which("ffmpeg") or "",
        "yt_dlp_version": YTDLP_VERSION,
        **youtube_cookie_status(),
    })


@app.route("/api/instagram/status")
def instagram_status():
    return jsonify({
        "success": True,
        "yt_dlp_version": YTDLP_VERSION,
        "preview_cache_items": len(_media_info_cache),
        **instagram_cookie_status(),
    })


@app.route("/favicon.ico")
def favicon():
    ico_path = FRONTEND_DIR / "favicon.ico"
    if ico_path.exists():
        return send_file(ico_path, mimetype="image/x-icon")
    return send_from_directory(FRONTEND_DIR, "favicon.svg", mimetype="image/svg+xml")


# Clean URL routes for SEO-friendly tool pages
@app.route("/youtube-video-downloader")
def tool_youtube():
    return seo_html("youtube.html", "pages")

@app.route("/pinterest-downloader")
def tool_pinterest():
    return seo_html("pinterest.html", "pages")

@app.route("/instagram-reel-downloader")
def tool_instagram():
    return seo_html("instagram.html", "pages")

@app.route("/youtube-thumbnail-downloader")
def tool_thumbnail():
    return seo_html("thumbnail.html", "pages")

@app.route("/qr-code-generator")
def tool_qr():
    return seo_html("qr.html", "pages")

@app.route("/pdf-to-image")
def tool_pdf_to_image():
    return seo_html("pdf-to-image.html", "pages")

@app.route("/image-to-pdf")
def tool_image_to_pdf():
    return seo_html("image-to-pdf.html", "pages")

@app.route("/image-compressor")
def tool_compress():
    return seo_html("compress.html", "pages")

@app.route("/remove-background")
def tool_removebg():
    return seo_html("removebg.html", "pages")

@app.route("/image-upscale")
def tool_upscale():
    return seo_html("upscale.html", "pages")

@app.route("/ai-image-enhancer")
def tool_enhance():
    return seo_html("enhance.html", "pages")

@app.route("/blur-background")
def tool_blur():
    return seo_html("blur.html", "pages")

@app.route("/image-converter")
def tool_convert():
    return seo_html("convert.html", "pages")

@app.route("/image-watermark")
def tool_watermark():
    return seo_html("watermark.html", "pages")

@app.route("/video-to-mp3")
def tool_audio():
    return seo_html("audio.html", "pages")

@app.route("/invoice-generator")
def tool_invoice():
    return seo_html("invoice.html", "pages")

@app.route("/policy")
def tool_policy():
    return seo_html("policy.html", "pages")


def legal_page(section):
    title, description = LEGAL_PAGE_SEO.get(section, LEGAL_PAGE_SEO["/privacy-policy"])
    canonical = absolute_url(section)
    title_attr = html_attr(title)
    description_attr = html_attr(description)
    sections = {
        "/about": [
            ("About ThugTools", "ThugTools is a free online creator tools platform built to make everyday media and document tasks faster. The site brings together video helpers, image tools, PDF converters, QR generation, and business utilities in one browser-based workspace."),
            ("Our Mission", "Our goal is to provide simple, useful tools that work without unnecessary signups, complicated dashboards, or heavy setup. We focus on fast access, practical controls, clear results, and responsible use."),
            ("How ThugTools Works", "Some tools run directly through browser-friendly workflows, while others use temporary server processing to create the result you request. Uploaded files and generated downloads are temporary and cleaned automatically."),
            ("Responsible Use", "ThugTools should be used only with content you own or are authorized to process. Users are responsible for respecting copyright, privacy, platform terms, and applicable laws."),
            ("Contact", "For support, business, privacy, or copyright requests, contact thugtoolscontact@gmail.com."),
        ],
        "/privacy-policy": [
            ("Privacy Policy", "Uploaded files, generated downloads, and submitted URLs are used only to provide the tool result you request. Generated files are temporary and are automatically cleaned from server storage."),
            ("Data We Process", "We may process uploaded files, public URLs, generated output files, browser request metadata, and basic server logs needed for reliability, abuse prevention, and debugging."),
            ("Advertising & Analytics", "If ads or analytics are enabled, third-party providers may use cookies or similar technologies under their own policies."),
        ],
        "/terms": [
            ("Terms of Service", "By using ThugTools, you agree to use the website only for lawful purposes and only with content you own, control, or are legally allowed to process."),
            ("Acceptable Use", "Do not use this service to infringe copyright, bypass access controls, distribute harmful files, violate privacy, overload the service, or break third-party platform terms."),
            ("Disclaimer", "Tools are provided as-is. Processing can fail for unsupported, private, login-only, blocked, or unavailable files and URLs."),
        ],
        "/dmca": [
            ("DMCA & Copyright Policy", "ThugTools does not permanently host third-party media. Files created by tool actions are temporary and intended only for user-requested processing."),
            ("Copyright Notices", "For copyright requests, email thugtoolscontact@gmail.com with the original URL, proof of ownership, the specific concern, and your contact details."),
            ("User Responsibility", "Users are responsible for confirming they have the right to download, transform, store, or share any submitted content."),
        ],
        "/contact": [
            ("Contact ThugTools", "For support, privacy, copyright, partnership, or website requests, contact thugtoolscontact@gmail.com."),
            ("Before You Write", "Include the tool name, the public URL or file type involved, the error message if any, and a clear description of the request."),
            ("Safe Usage", "Use only content you own or are authorized to process. Respect copyright, privacy, and platform terms."),
        ],
    }
    content = "\n".join(f"<h2>{heading}</h2><p>{body}</p>" for heading, body in sections.get(section, []))
    schema = json_ld_script({
        "@context": "https://schema.org",
        "@graph": base_schema_graph(section, title, description),
    })
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{description_attr}">
  <meta name="keywords" content="ThugTools legal, privacy policy, terms of service, DMCA, contact ThugTools">
  <meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
  <link rel="canonical" href="{canonical}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="{SITE_NAME}">
  <meta property="og:title" content="{title_attr}">
  <meta property="og:description" content="{description_attr}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:image" content="{absolute_url(DEFAULT_IMAGE)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title_attr}">
  <meta name="twitter:description" content="{description_attr}">
  <meta name="twitter:image" content="{absolute_url(DEFAULT_IMAGE)}">
  <meta name="theme-color" content="#2563eb">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="preload" href="/style.css" as="style">
  <link rel="stylesheet" href="/style.css">
  <!-- Google tag (gtag.js) -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-PRQ6Z3GFZS"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());

    gtag('config', 'G-PRQ6Z3GFZS');
  </script>
  {schema}
</head>
<body>
  <div class="rgb-line"></div>
  <nav class="nav" role="navigation" aria-label="Main navigation"><div class="container nav-inner"><a class="brand" href="/" aria-label="ThugTools home"><div class="brand-mark" aria-hidden="true">T</div><span>ThugTools</span></a><div class="nav-links"><a href="/#tools">Tools</a><a href="/about">About</a><a href="/privacy-policy">Privacy</a><a href="/terms">Terms</a><a href="/dmca">DMCA</a><a href="/contact">Contact</a></div><div class="nav-actions"><button class="icon-btn" data-theme aria-label="Toggle theme"><span data-icon="sun"></span></button><button class="menu-btn" aria-label="Open menu"><span data-icon="menu"></span></button></div></div></nav>
  <main class="legal-page"><div class="container legal-panel reveal"><span class="eyebrow">Trust & safety</span>{content}<div class="legal-links"><a href="/about">About Us</a><a href="/privacy-policy">Privacy Policy</a><a href="/terms">Terms</a><a href="/dmca">DMCA</a><a href="/contact">Contact</a></div></div></main>
  <footer class="footer" role="contentinfo"><div class="container footer-inner"><div class="brand"><div class="brand-mark" aria-hidden="true">T</div><span>ThugTools</span></div><span>Use only with content you own or are allowed to process.</span></div></footer>
  <div class="toast"></div><div class="spinner"><div class="loader"></div></div><script src="/script.js?v=20260515-seo-premium"></script>
</body>
</html>"""
    return Response(html, mimetype="text/html")


@app.route("/privacy-policy")
def privacy_policy():
    return legal_page("/privacy-policy")


@app.route("/about")
def about_page():
    return legal_page("/about")


@app.route("/terms")
def terms_page():
    return legal_page("/terms")


@app.route("/dmca")
def dmca_page():
    return legal_page("/dmca")


@app.route("/contact")
def contact_page():
    return legal_page("/contact")


# Canonical URL mapping for /pages/* redirects (301 permanent redirects)
PAGES_REDIRECT_MAP = {
    "youtube.html": "/youtube-video-downloader",
    "pinterest.html": "/pinterest-downloader",
    "instagram.html": "/instagram-reel-downloader",
    "thumbnail.html": "/youtube-thumbnail-downloader",
    "qr.html": "/qr-code-generator",
    "pdf-to-image.html": "/pdf-to-image",
    "image-to-pdf.html": "/image-to-pdf",
    "compress.html": "/image-compressor",
    "removebg.html": "/remove-background",
    "upscale.html": "/image-upscale",
    "enhance.html": "/ai-image-enhancer",
    "blur.html": "/blur-background",
    "convert.html": "/image-converter",
    "watermark.html": "/image-watermark",
    "audio.html": "/video-to-mp3",
    "invoice.html": "/invoice-generator",
    "policy.html": "/privacy-policy",
}

@app.route("/pages/<path:filename>")
def pages(filename):
    # 301 redirect to canonical clean URLs for HTML pages
    if filename in PAGES_REDIRECT_MAP:
        return redirect(PAGES_REDIRECT_MAP[filename], code=301)
    # Serve non-HTML assets from /pages/ directory
    if filename.endswith(".html"):
        return seo_html(filename, "pages")
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
    quality = data.get("quality", "best")
    return jsonify(run_yt_dlp(url, "video", quality))


@app.post("/api/download/pinterest")
def pinterest_download():
    cleanup_temp_storage()
    data = request.get_json(silent=True) or request.form
    url = clean_url(data.get("url"))
    quality = data.get("quality", "best")
    return jsonify(run_yt_dlp(url, "video", quality))


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
    info = {}
    video_id = extract_youtube_video_id(url)
    try:
        info, _ = extract_info_safe(url, download=False, extra_opts={"skip_download": True})
        video_id = info.get("id") or video_id
    except ApiError:
        if not video_id:
            raise
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
        mode = request.form.get("mode", "ai")
        mode = "ai"
        
        # Check for HD mode parameter
        hd_mode = request.form.get("hd_mode", "0").lower() in {"1", "true", "yes"}
        
        app.logger.info(f"Processing AI removebg for {source.name}, model={rembg_model_for_mode(mode)}, file size={source.stat().st_size} bytes, hd_mode={hd_mode}")
        remove_background_ai(source, out, feather=feather, background=background, mode=mode, hd_mode=hd_mode)
        app.logger.info(f"RemoveBG succeeded: {out.name}")
        return jsonify(image_response(out, "Download PNG image"))
    except Exception as e:
        app.logger.exception(f"RemoveBG endpoint error: {str(e)[:200]}")
        raise
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
