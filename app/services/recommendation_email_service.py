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


def email_provider():
    return SMTPEmailProvider() if settings.email_provider == "smtp" and settings.smtp_host and settings.email_from_address else ConsoleEmailProvider()
