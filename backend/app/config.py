from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://audionotes:audionotes@localhost:5433/audionotes"

    # --- Gnani ---
    gnani_api_key: str = ""
    gnani_base_url: str = "https://api.vachana.ai"
    # Poll the Batch job no more often than the documented minimum.
    gnani_poll_interval_seconds: int = 10
    gnani_max_poll_seconds: int = 1800
    # Ingest audio by reference (cloud_storage) instead of re-uploading bytes to
    # Gnani. This removes the 10 MB multipart ceiling and supports up to 4 hours.
    gnani_cloud_ingest: bool = True
    # Send a callback_url so Gnani pushes the finished job to us.
    gnani_use_webhook: bool = False
    gnani_webhook_base_url: str = ""
    gnani_webhook_secret: str = ""
    # Default recognition options (can be overridden per upload).
    gnani_default_diarization: bool = False
    gnani_default_num_speakers: int = 2
    gnani_default_denoise: bool = False
    gnani_default_bias_score: float = 1.0
    # Route short clips through the synchronous REST endpoint so Inverse Text
    # Normalization (numbers/currency/dates) is applied. Batch has no ITN.
    gnani_rest_itn_max_seconds: int = 60
    gnani_rest_timeout_seconds: int = 120

    # --- Gnani Timbre TTS ---
    gnani_tts_model: str = "timbre-v2.5"
    gnani_tts_voice: str = "Kaveri"
    gnani_tts_max_chars: int = 3500

    # --- Gemini ---
    gemini_api_key: str = ""
    # Flash-Lite: cheap and with a higher free-tier quota than full Flash. The
    # agent makes several calls per question, so a lite model is the right default.
    gemini_model: str = "gemini-3.5-flash-lite"

    # --- App / storage ---
    frontend_origin: str = "http://localhost:3000"
    backend_public_url: str = "http://localhost:8000"
    upload_dir: str = "uploads"
    # With cloud ingestion there is no Gnani byte ceiling, so allow large files.
    max_upload_mb: int = 200
    redis_url: str = "redis://localhost:6379/0"
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    supabase_bucket: str = "audio-notes"
    # Keep buckets private and hand out short-lived signed URLs.
    supabase_bucket_public: bool = False
    supabase_signed_url_expires_seconds: int = 3600
    stale_job_minutes: int = 20

    # --- Auth / email ---
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    password_reset_expire_minutes: int = 30
    frontend_reset_password_url: str = ""
    email_verification_expire_hours: int = 24
    frontend_verify_email_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    auth_rate_limit_per_minute: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
