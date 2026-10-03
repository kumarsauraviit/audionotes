import asyncio
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode

from app.config import get_settings
from app.queue import celery_app
from app.services import process_note, recover_stale_jobs

@celery_app.task(
    name="audio_notes.process_note",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    acks_late=True,
)
def process_note_task(note_id: str) -> None:
    asyncio.run(process_note(note_id))


@celery_app.task(name="audio_notes.recover_stale_jobs")
def recover_stale_jobs_task() -> int:
    """Re-queue notes left mid-flight; safe to run periodically via Celery beat."""
    return recover_stale_jobs()


@celery_app.task(
    name="audio_notes.send_password_reset_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_password_reset_email_task(email: str, token: str) -> None:
    settings = get_settings()
    if not all((settings.smtp_host, settings.email_from, settings.frontend_reset_password_url)):
        raise RuntimeError("SMTP_HOST, EMAIL_FROM, and FRONTEND_RESET_PASSWORD_URL must be configured.")

    reset_url = f"{settings.frontend_reset_password_url}?{urlencode({'token': token})}"
    message = EmailMessage()
    message["Subject"] = "Reset your Audio Notes password"
    message["From"] = settings.email_from
    message["To"] = email
    message.set_content(
        "We received a request to reset your Audio Notes password.\n\n"
        f"Use this link within {settings.password_reset_expire_minutes} minutes:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


@celery_app.task(
    name="audio_notes.send_email_verification",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_email_verification_task(email: str, token: str) -> None:
    settings = get_settings()
    if not all((settings.smtp_host, settings.email_from, settings.frontend_verify_email_url)):
        raise RuntimeError("SMTP_HOST, EMAIL_FROM, and FRONTEND_VERIFY_EMAIL_URL must be configured.")

    verify_url = f"{settings.frontend_verify_email_url}?{urlencode({'token': token})}"
    message = EmailMessage()
    message["Subject"] = "Verify your Audio Notes email"
    message["From"] = settings.email_from
    message["To"] = email
    message.set_content(
        "Verify your Audio Notes email address using this link.\n\n"
        f"The link expires in {settings.email_verification_expire_hours} hours:\n{verify_url}"
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
