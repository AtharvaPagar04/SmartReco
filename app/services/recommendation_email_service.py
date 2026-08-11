from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    message_id: str | None = None
    error: str | None = None
    permanent: bool = False


def render_digest(run, base_url: str | None = None) -> tuple[str, str]:
    base = (base_url or settings.app_base_url).rstrip("/")
    items = [item for item in run.items if item.dismissed_at is None and item.course and item.course.is_active][:3]
    lines = [run.headline or "Your SmartReco learning path", "", run.narrative or "Based on your recent course activity.", ""]
    html_items = []
    for item in items:
        url = f"{base}/courses/{item.course.slug}"
        lines.extend([item.course.title, item.reason, url, ""])
        html_items.append(f'<li><a href="{escape(url, quote=True)}">{escape(item.course.title)}</a><br>{escape(item.reason)}</li>')
    return "\n".join(lines), f"<h1>{escape(run.headline or 'Your SmartReco learning path')}</h1><p>{escape(run.narrative or 'Based on your recent course activity.')}</p><ul>{''.join(html_items)}</ul>"


class ConsoleEmailProvider:
    async def send_recommendation_digest(self, *, recipient: str, subject: str, text: str, html: str) -> DeliveryResult:
        logger.info("recommendation email", extra={"recipient": recipient, "subject": subject})
        return DeliveryResult(True, message_id="console")


class SMTPEmailProvider:
    async def send_recommendation_digest(self, *, recipient: str, subject: str, text: str, html: str) -> DeliveryResult:
        def send() -> DeliveryResult:
            try:
                message = EmailMessage()
                message["From"] = settings.email_from_address
                message["To"] = recipient
                message["Subject"] = subject
                message.set_content(text)
                message.add_alternative(html, subtype="html")
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.mesh_request_timeout_seconds) as smtp:
                    if settings.smtp_use_tls:
                        smtp.starttls()
                    if settings.smtp_username:
                        smtp.login(settings.smtp_username, settings.smtp_password)
                    smtp.send_message(message)
                return DeliveryResult(True, message_id="smtp")
            except smtplib.SMTPRecipientsRefused:
                return DeliveryResult(False, error="recipient_rejected", permanent=True)
            except Exception:
                return DeliveryResult(False, error="smtp_delivery_failed")
        return await asyncio.to_thread(send)


import resend

class ResendEmailProvider:
    def __init__(self, api_key: str | None = None, from_address: str | None = None):
        self.api_key = api_key or settings.resend_api_key
        self.from_address = from_address or settings.email_from_address

    async def send_recommendation_digest(self, *, recipient: str, subject: str, text: str, html: str) -> DeliveryResult:
        def send_sync() -> DeliveryResult:
            if not self.api_key:
                return DeliveryResult(False, error="resend_api_key_missing", permanent=True)
            if not self.from_address:
                return DeliveryResult(False, error="email_from_missing", permanent=True)

            resend.api_key = self.api_key
            params = {
                "from": self.from_address,
                "to": recipient,
                "subject": subject,
                "html": html,
                "text": text,
            }
            try:
                response = resend.Emails.send(params)
                msg_id = None
                if isinstance(response, dict):
                    msg_id = response.get("id")
                elif hasattr(response, "id"):
                    msg_id = getattr(response, "id")
                elif hasattr(response, "get"):
                    msg_id = response.get("id")

                logger.info(
                    "recommendation.delivery.sent",
                    extra={
                        "provider": "resend",
                        "provider_message_id": msg_id,
                        "recipient": recipient,
                    },
                )
                return DeliveryResult(True, message_id=msg_id or "resend")
            except resend.exceptions.ResendError as exc:
                err_msg = str(exc)
                code = getattr(exc, "code", None)
                is_permanent = (
                    code in (401, 403, 422)
                    or isinstance(
                        exc,
                        (
                            resend.exceptions.InvalidApiKeyError,
                            resend.exceptions.MissingApiKeyError,
                            resend.exceptions.ValidationError,
                            resend.exceptions.MissingRequiredFieldsError,
                        ),
                    )
                )
                logger.warning(
                    "resend.delivery.failed",
                    extra={
                        "provider": "resend",
                        "recipient": recipient,
                        "error": err_msg,
                        "code": code,
                        "permanent": is_permanent,
                    },
                )
                return DeliveryResult(False, error=f"resend_error: {err_msg}", permanent=is_permanent)
            except Exception as exc:
                err_msg = str(exc)
                logger.warning(
                    "resend.delivery.failed",
                    extra={
                        "provider": "resend",
                        "recipient": recipient,
                        "error": err_msg,
                        "permanent": False,
                    },
                )
                return DeliveryResult(False, error=f"resend_error: {err_msg}", permanent=False)

        return await asyncio.to_thread(send_sync)


def email_provider():
    provider = settings.email_provider.lower()
    if provider == "console":
        return ConsoleEmailProvider()
    elif provider == "smtp":
        if not settings.smtp_host or not settings.email_from_address:
            raise ValueError("SMTP email provider missing required configuration: SMTP_HOST and EMAIL_FROM_ADDRESS are required when EMAIL_PROVIDER is set to 'smtp'.")
        return SMTPEmailProvider()
    elif provider == "resend":
        if not settings.resend_api_key or not settings.email_from_address:
            raise ValueError("Resend email provider missing required configuration: RESEND_API_KEY and EMAIL_FROM_ADDRESS (or EMAIL_FROM) are required when EMAIL_PROVIDER is set to 'resend'.")
        return ResendEmailProvider()
    else:
        raise ValueError(f"Unsupported EMAIL_PROVIDER: '{settings.email_provider}'. Must be one of 'console', 'smtp', or 'resend'.")
