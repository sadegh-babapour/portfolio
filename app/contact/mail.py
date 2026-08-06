from __future__ import annotations

from email.message import EmailMessage

import requests

from app.contact.config import ContactSettings

RESEND_EMAILS_URL = "https://api.resend.com/emails"


def _send(message: EmailMessage, settings: ContactSettings) -> None:
    payload: dict[str, object] = {
        "from": message["From"],
        "to": [message["To"]],
        "subject": message["Subject"],
        "text": message.get_content(),
    }
    if message["Reply-To"]:
        payload["reply_to"] = message["Reply-To"]

    response = requests.post(
        RESEND_EMAILS_URL,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "bizqlab-portfolio-contact/1.0",
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()


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
