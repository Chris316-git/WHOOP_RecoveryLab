"""Send an email over SMTP (Gmail with an app password by default)."""
import smtplib
import ssl
from email.message import EmailMessage

from src.settings import Settings, SmtpSettings


def send_email(to: str, subject: str, html: str, text: str, smtp: SmtpSettings | None = None) -> None:
    smtp = smtp or Settings.from_env().smtp
    if not smtp.configured:
        raise RuntimeError("SMTP_USER and SMTP_PASSWORD must be set to send email.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Recovery Lab <{smtp.user}>"
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    context = ssl.create_default_context()
    if smtp.port == 465:
        with smtplib.SMTP_SSL(smtp.host, smtp.port, context=context, timeout=30) as server:
            server.login(smtp.user, smtp.password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as server:
            server.starttls(context=context)
            server.login(smtp.user, smtp.password)
            server.send_message(msg)
