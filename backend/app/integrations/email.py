from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)


async def send_email(settings: Settings, *, to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        start_tls=settings.is_production,
        timeout=10,
    )
    log.info("email_sent", to_domain=to.split("@")[-1], subject=subject)
