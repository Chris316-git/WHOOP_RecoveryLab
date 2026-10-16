"""Send an email over SMTP (Gmail with an app password by default)."""
import smtplib
import ssl
from email.message import EmailMessage

from src import config


def send_email(to: str, subject: str, html: str, text: str) -> None:
    if not (config.SMTP_USER and config.SMTP_PASSWORD):
        raise RuntimeError("SMTP_USER and SMTP_PASSWORD must be set to send email.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Recovery Lab <{config.SMTP_USER}>"
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    context = ssl.create_default_context()
    if config.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context, timeout=30) as smtp:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            smtp.starttls(context=context)
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
