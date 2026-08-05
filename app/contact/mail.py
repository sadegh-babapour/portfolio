from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.contact.config import ContactSettings


def _send(message: EmailMessage, settings: ContactSettings) -> None:
    if settings.smtp_security == "ssl":
        smtp_client = smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=15,
            context=ssl.create_default_context(),
        )
    else:
        smtp_client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    with smtp_client as smtp:
        smtp.ehlo()
        if settings.smtp_security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def send_verification_email(
    settings: ContactSettings,
    recipient: str,
    name: str,
    verification_url: str,
) -> None:
    message = EmailMessage()
    message["Subject"] = "Verify your message to BizQLab"
    message["From"] = settings.from_email
    message["To"] = recipient
    message.set_content(
        f"Hello {name},\n\n"
        "Confirm that you sent a portfolio contact message by opening this link:\n\n"
        f"{verification_url}\n\n"
        "The link expires in 30 minutes and can be used once. If you did not send "
        "this message, you can ignore this email.\n"
    )
    _send(message, settings)


def deliver_contact_message(
    settings: ContactSettings,
    *,
    name: str,
    verified_email: str,
    category: str,
    subject: str,
    body: str,
) -> None:
    message = EmailMessage()
    message["Subject"] = f"[Portfolio: {category}] {subject}"
    message["From"] = settings.from_email
    message["To"] = settings.to_email
    message["Reply-To"] = verified_email
    message.set_content(
        f"Verified sender: {name} <{verified_email}>\n"
        f"Category: {category}\n\n{body}\n"
    )
    _send(message, settings)
