"""Option images: validate + shrink with Pillow, store in a public Supabase Storage bucket.

Only the standard library is used for HTTP. Uploads are enabled when both
SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set; otherwise the form hides the field.
"""
import io
import json
import logging
import urllib.error
import urllib.request
import uuid

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SIDE = 800
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs


class ImageError(Exception):
    """User-facing (Turkish) validation or upload problem."""


def uploads_enabled():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)


def process_image(uploaded):
    """Validate an uploaded file and return WebP bytes (max 800px on the long side)."""
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise ImageError("Görsel en fazla 5 MB olabilir.")
    try:
        data = uploaded.read()
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        image = Image.open(io.BytesIO(data))
        if image.format not in ALLOWED_FORMATS:
            raise ImageError("Sadece JPG, PNG, WebP veya GIF yükleyebilirsin.")
        image = ImageOps.exif_transpose(image)
        image.thumbnail((MAX_SIDE, MAX_SIDE))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        out = io.BytesIO()
        image.save(out, "WEBP", quality=82, method=4)
        return out.getvalue()
    except ImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ImageError("Bu dosya geçerli bir görsel değil.")


def _auth_headers():
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    headers = {"apikey": key}
    if not key.startswith("sb_secret_"):  # legacy service_role JWT
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _request(method, url, data=None, content_type=None):
    headers = _auth_headers()
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.status


def _bucket_url(path=""):
    base = settings.SUPABASE_URL.rstrip("/")
    return f"{base}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}{path}"


def public_url(name):
    base = settings.SUPABASE_URL.rstrip("/")
    return f"{base}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/{name}"


def upload_image(webp_bytes):
    """Upload processed bytes; return the public URL."""
    name = f"options/{uuid.uuid4().hex}.webp"
    try:
        _request("POST", _bucket_url(f"/{name}"), data=webp_bytes, content_type="image/webp")
    except (urllib.error.URLError, TimeoutError) as error:
        detail = error.read().decode(errors="replace")[:300] if isinstance(error, urllib.error.HTTPError) else ""
        logger.error("Görsel yüklenemedi: %s %s", error, detail)
        raise ImageError("Görsel yüklenemedi, lütfen tekrar dene.")
    return public_url(name)


def delete_images(urls):
    """Best effort: remove stored files for the given public URLs (errors are only logged)."""
    prefix = public_url("")
    names = [url[len(prefix):] for url in urls if url and url.startswith(prefix)]
    if not names or not uploads_enabled():
        return
    try:
        _request("DELETE", _bucket_url(), data=json.dumps({"prefixes": names}).encode(), content_type="application/json")
    except (urllib.error.URLError, TimeoutError) as error:
        logger.warning("Görseller silinemedi: %s", error)
