"""Outgoing email over SMTP, configured from the environment (never from the repository).

SEED_REFLECTIONS_SMTP_HOST, SEED_REFLECTIONS_SMTP_PORT (default 587), SEED_REFLECTIONS_SMTP_SECURITY
(starttls, ssl or none; default starttls), SEED_REFLECTIONS_SMTP_USER, SEED_REFLECTIONS_SMTP_PASSWORD and
SEED_REFLECTIONS_SMTP_FROM. Any ordinary mailbox works, for example one created in SiteGround or Google Workspace.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid


class MailError(ValueError):
    """The message could not be sent. The text is safe to log and never contains the password."""


def _setting(name, default=""):
    return os.environ.get("SEED_REFLECTIONS_SMTP_" + name, default).strip()


def configured():
    return bool(_setting("HOST") and _setting("FROM"))


def send(to, subject, body):
    if not configured():
        raise MailError("Email is not configured on this server.")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = _setting("FROM"), to, subject
    message["Date"], message["Message-ID"] = formatdate(localtime=False), make_msgid(domain=_setting("FROM").rsplit("@", 1)[-1] or None)
    message.set_content(body)
    host, security = _setting("HOST"), (_setting("SECURITY", "starttls") or "starttls").lower()
    try:
        port = int(_setting("PORT", "465" if security == "ssl" else "587"))
        context = ssl.create_default_context()
        client = smtplib.SMTP_SSL(host, port, timeout=20, context=context) if security == "ssl" else smtplib.SMTP(host, port, timeout=20)
        with client:
            client.ehlo()
            if security == "starttls":
                client.starttls(context=context); client.ehlo()
            if _setting("USER"):
                client.login(_setting("USER"), os.environ.get("SEED_REFLECTIONS_SMTP_PASSWORD", ""))
            client.send_message(message)
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        raise MailError(f"The email could not be sent ({type(exc).__name__}).") from None
