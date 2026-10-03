import logging
from pathlib import Path
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)

SUPABASE_REF_PREFIX = "supabase://"
MIME_MAP = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".aac": "audio/aac",
    ".webm": "audio/webm",
    ".amr": "audio/amr",
}


def get_supabase_headers() -> dict[str, str] | None:
    settings = get_settings()
    if not settings.supabase_url:
        return None
    key = settings.supabase_secret_key or settings.supabase_publishable_key
    if not key:
        return None
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }


def is_supabase_enabled() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url and (settings.supabase_secret_key or settings.supabase_publishable_key))


def is_supabase_ref(value: str | None) -> bool:
    return bool(value) and value.startswith(SUPABASE_REF_PREFIX)


def _split_ref(value: str) -> tuple[str, str]:
    """Return (bucket, object_path) for a ``supabase://bucket/path`` reference."""
    raw = value[len(SUPABASE_REF_PREFIX):]
    bucket, _, object_path = raw.partition("/")
    return bucket, object_path


def ensure_bucket_exists() -> None:
    """Ensure the configured Supabase bucket exists, creating it if possible."""
    settings = get_settings()
    headers = get_supabase_headers()
    if not headers or not settings.supabase_url:
        return

    bucket = settings.supabase_bucket
    base_url = settings.supabase_url.rstrip("/")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{base_url}/storage/v1/bucket/{bucket}", headers=headers)
            if resp.status_code == 404:
                create_resp = client.post(
                    f"{base_url}/storage/v1/bucket",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"id": bucket, "name": bucket, "public": settings.supabase_bucket_public},
                )
                if create_resp.status_code in (200, 201):
                    logger.info("Created Supabase storage bucket: %s (public=%s)", bucket, settings.supabase_bucket_public)
                else:
                    logger.warning("Could not auto-create Supabase bucket %s: %s", bucket, create_resp.text)
    except Exception as exc:
        logger.warning("Supabase bucket check error: %s", exc)


def upload_audio_to_supabase(file_name: str, data: bytes, content_type: str | None = None) -> str:
    """Upload audio and return a stable ``supabase://bucket/path`` reference.

    We store a reference rather than a public URL so the bucket can stay private
    and access is always mediated by a short-lived signed URL.
    """
    settings = get_settings()
    headers = get_supabase_headers()
    if not headers or not settings.supabase_url:
        raise RuntimeError("Supabase credentials not configured.")

    if not content_type:
        content_type = MIME_MAP.get(Path(file_name).suffix.lower(), "application/octet-stream")

    bucket = settings.supabase_bucket
    base_url = settings.supabase_url.rstrip("/")
    url = f"{base_url}/storage/v1/object/{bucket}/{file_name}"

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            url,
            headers={**headers, "Content-Type": content_type, "x-upsert": "true"},
            content=data,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Failed to upload audio to Supabase (HTTP {resp.status_code}): {resp.text}")

    ref = f"{SUPABASE_REF_PREFIX}{bucket}/{file_name}"
    logger.info("Uploaded %s to Supabase Storage (%s)", file_name, ref)
    return ref


def create_signed_url(file_path_or_ref: str, expires_in: int | None = None) -> str | None:
    """Create a short-lived signed URL for a stored object."""
    settings = get_settings()
    if not is_supabase_ref(file_path_or_ref):
        # Legacy public URLs are returned unchanged.
        if file_path_or_ref.startswith(("http://", "https://")):
            return file_path_or_ref
        return None

    headers = get_supabase_headers()
    if not headers:
        return None
    bucket, object_path = _split_ref(file_path_or_ref)
    base_url = settings.supabase_url.rstrip("/")
    ttl = expires_in or settings.supabase_signed_url_expires_seconds
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{base_url}/storage/v1/object/sign/{bucket}/{object_path}",
                headers={**headers, "Content-Type": "application/json"},
                json={"expiresIn": ttl},
            )
            if resp.status_code not in (200, 201):
                logger.warning("Could not sign %s: HTTP %s %s", file_path_or_ref, resp.status_code, resp.text)
                return None
            signed = resp.json().get("signedURL")
            if not signed:
                return None
            if signed.startswith("http"):
                return signed
            return f"{base_url}/storage/v1{signed}"
    except Exception as exc:
        logger.warning("Error signing %s: %s", file_path_or_ref, exc)
        return None


def download_audio_from_supabase(file_path_or_url: str) -> bytes:
    """Download audio bytes from Supabase given a ref, path, or URL."""
    settings = get_settings()
    headers = get_supabase_headers() or {}

    if is_supabase_ref(file_path_or_url):
        bucket, object_path = _split_ref(file_path_or_url)
        base_url = settings.supabase_url.rstrip("/")
        download_url = f"{base_url}/storage/v1/object/{bucket}/{object_path}"
    elif file_path_or_url.startswith(("http://", "https://")):
        download_url = file_path_or_url
    else:
        bucket = settings.supabase_bucket
        base_url = settings.supabase_url.rstrip("/")
        download_url = f"{base_url}/storage/v1/object/{bucket}/{file_path_or_url}"

    with httpx.Client(timeout=120.0) as client:
        resp = client.get(download_url, headers=headers)
        if resp.is_error:
            raise RuntimeError(f"Failed to download audio from Supabase ({download_url}): HTTP {resp.status_code}")
        return resp.content


def delete_audio_from_supabase(file_name_or_url: str) -> None:
    """Delete an audio object from Supabase Storage."""
    settings = get_settings()
    headers = get_supabase_headers()
    if not headers or not settings.supabase_url:
        return

    bucket = settings.supabase_bucket
    base_url = settings.supabase_url.rstrip("/")

    if is_supabase_ref(file_name_or_url):
        bucket, file_name = _split_ref(file_name_or_url)
    elif f"/storage/v1/object/public/{bucket}/" in file_name_or_url:
        file_name = file_name_or_url.split(f"/storage/v1/object/public/{bucket}/")[-1]
    else:
        file_name = Path(file_name_or_url).name

    url = f"{base_url}/storage/v1/object/{bucket}"
    try:
        with httpx.Client(timeout=15.0) as client:
            client.request(
                "DELETE",
                url,
                headers={**headers, "Content-Type": "application/json"},
                json={"prefixes": [file_name]},
            )
            logger.info("Deleted %s from Supabase Storage", file_name)
    except Exception as exc:
        logger.warning("Error deleting %s from Supabase: %s", file_name, exc)
