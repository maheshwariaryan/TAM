"""
Outbound email — currently just password reset.

Dispatches on settings.smtp_host, the same pattern app/agents/base.py uses for
settings.use_mock_llm: one real path, one local-only fallback, chosen by
whether the real dependency is configured. No provider SDK is required for the
real path — SMTP is the one delivery mechanism every provider (SES, SendGrid,
Mailgun, Postmark, Gmail, a self-hosted relay) exposes, so this isn't a
vendor-specific integration to swap out later.
"""

import logging
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def send_password_reset_email(to: str, reset_url: str) -> None:
    subject = "Reset your TAM password"
    body = (
        f"A password reset was requested for this email address.\n\n"
        f"Reset your password: {reset_url}\n\n"
        f"This link expires in 1 hour. If you didn't request this, you can "
        f"ignore this email — your password won't be changed."
    )

    if settings.smtp_host:
        _send_via_smtp(to, subject, body)
    else:
        _write_to_dev_outbox(to, subject, body)


def _send_via_smtp(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from_address
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)

    # Never log the body — it contains the reset link, a bearer credential.
    logger.info("AUDIT password_reset_email_sent via=smtp")


def _write_to_dev_outbox(to: str, subject: str, body: str) -> None:
    # Local-dev-only stand-in for real delivery — see settings.smtp_host's
    # docstring. Writes to a gitignored directory, never to the shared
    # application log stream, so this doesn't put a reset link where a log
    # aggregator or CI log viewer could pick it up.
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    safe_recipient = to.replace("/", "_").replace("\\", "_")
    outbox_path = settings.dev_email_outbox_dir / f"{timestamp}__{safe_recipient}.txt"
    outbox_path.write_text(f"To: {to}\nSubject: {subject}\n\n{body}\n", encoding="utf-8")

    logger.info(
        "AUDIT password_reset_email_sent via=dev_outbox path=%s "
        "(no SMTP configured — see settings.smtp_host)",
        outbox_path,
    )
