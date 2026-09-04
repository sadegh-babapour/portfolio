from __future__ import annotations

from email.message import EmailMessage
from html import escape

import requests

from app.contact.config import ContactSettings

RESEND_EMAILS_URL = "https://api.resend.com/emails"


def _send(message: EmailMessage, settings: ContactSettings) -> None:
    plain_part = (
        message.get_body(preferencelist=("plain",))
        if message.is_multipart()
        else message
    )
    payload: dict[str, object] = {
        "from": message["From"],
        "to": [message["To"]],
        "subject": message["Subject"],
        "text": plain_part.get_content(),
    }
    html_part = message.get_body(preferencelist=("html",))
    if html_part is not None:
        payload["html"] = html_part.get_content()
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
    message["Subject"] = "Confirm your message to Bizqlab"
    message["From"] = settings.from_email
    message["To"] = recipient
    message.set_content(
        f"Hello {name},\n\n"
        "Please use the link below to confirm it was you who asked Bizqlab to send "
        "this message. Your message will not be delivered until you confirm.\n\n"
        f"{verification_url}\n\n"
        "This confirmation link expires in 30 minutes and can be used once. If you "
        "did not make this request, you can safely ignore this email.\n"
    )
    safe_name = escape(name)
    safe_url = escape(verification_url, quote=True)
    message.add_alternative(
        f"""<!doctype html><html><body style="font-family:Arial,sans-serif;line-height:1.6;color:#172033">
        <p>Hello {safe_name},</p>
        <p>Please confirm it was you who asked Bizqlab to send this message. Your message
        will not be delivered until you confirm.</p>
        <p><a href="{safe_url}" style="display:inline-block;padding:12px 18px;border-radius:8px;
        background:#2563eb;color:#fff;text-decoration:none;font-weight:700">Verify and send my message</a></p>
        <p style="font-size:13px;color:#5b6472">This link expires in 30 minutes and can be used once.
        If you did not make this request, you can safely ignore this email.</p>
        </body></html>""",
        subtype="html",
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
