"""WhatsApp deep links and the background email notification task.

The ordering rule for lead capture: the row is committed *first*, then the
notification is queued. A mail outage must never cost a lead.
"""

from __future__ import annotations

import logging
import smtplib
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from urllib.parse import quote

import anyio.to_thread
from sqlalchemy import update

from app.core.config import settings
from app.db.session import SessionFactory
from app.models.enquiry import Enquiry

logger = logging.getLogger(__name__)


def build_whatsapp_url(
    *,
    name: str,
    subject: str | None = None,
    message: str | None = None,
    phone: str | None = None,
) -> str:
    """Return a ``wa.me`` link with a pre-filled, URL-encoded message.

    ``wa.me`` requires digits only — no ``+``, spaces or dashes.
    """
    digits = "".join(ch for ch in (phone or settings.WHATSAPP_PHONE) if ch.isdigit())

    lines = [f"Hi, this is {name}."]
    if subject:
        lines.append(f"Regarding: {subject}")
    if message:
        # WhatsApp truncates very long prefills; keep the link usable.
        excerpt = message.strip()
        lines.append(excerpt if len(excerpt) <= 400 else f"{excerpt[:397]}...")
    lines.append("I just sent an enquiry through your website.")

    # quote() with an empty safe set percent-encodes newlines and '&' correctly.
    encoded = quote("\n".join(lines), safe="")
    return f"https://wa.me/{digits}?text={encoded}"


def _render_email(enquiry: Enquiry) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"[Portfolio] New enquiry from {enquiry.name}"
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USERNAME or "noreply@localhost"
    msg["To"] = settings.ENQUIRY_NOTIFY_EMAIL or ""
    # Replying from the inbox should reach the enquirer, not the SMTP account.
    msg["Reply-To"] = enquiry.email

    msg.set_content(
        "\n".join(
            [
                f"Name:    {enquiry.name}",
                f"Email:   {enquiry.email}",
                f"Phone:   {enquiry.phone or '-'}",
                f"Subject: {enquiry.subject or '-'}",
                f"Source:  {enquiry.source}",
                f"IP:      {enquiry.ip_address or '-'}",
                f"Agent:   {enquiry.user_agent or '-'}",
                "",
                "Message",
                "-------",
                enquiry.message,
                "",
                f"Enquiry id: {enquiry.id}",
            ]
        )
    )
    return msg


def _send_sync(msg: EmailMessage) -> None:
    """Blocking SMTP send. Called inside a thread by BackgroundTasks."""
    host, port = settings.SMTP_HOST, settings.SMTP_PORT
    assert host is not None  # guarded by settings.email_enabled

    if port == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=20)
    else:
        server = smtplib.SMTP(host, port, timeout=20)

    with server:
        if port != 465 and settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)


async def notify_new_enquiry(enquiry_id: uuid.UUID) -> None:
    """Background task: email the artist and record the outcome on the row.

    Re-reads the enquiry in its own session because the request session is
    already closed by the time BackgroundTasks runs. Never raises — a failed
    notification is recorded in ``notification_error`` for later retry.
    """
    if not settings.email_enabled:
        logger.info("SMTP not configured; skipping notification for %s", enquiry_id)
        return

    async with SessionFactory() as session:
        enquiry = await session.get(Enquiry, enquiry_id)
        if enquiry is None:
            logger.warning("Enquiry %s vanished before notification", enquiry_id)
            return

        message = _render_email(enquiry)
        error: str | None = None
        try:
            await anyio.to_thread.run_sync(_send_sync, message)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.exception("Enquiry notification failed for %s", enquiry_id)

        await session.execute(
            update(Enquiry)
            .where(Enquiry.id == enquiry_id)
            .values(
                notified=error is None,
                notified_at=datetime.now(tz=UTC) if error is None else None,
                notification_error=error,
            )
        )
        await session.commit()

    if error is None:
        logger.info("Enquiry notification sent for %s", enquiry_id)
