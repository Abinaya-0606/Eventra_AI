"""Send email. Works three ways: SMTP (if configured), console (development), or an in-memory outbox (tests)."""
import smtplib
from email.message import EmailMessage

from flask import current_app


def send_email(to: str, subject: str, body: str) -> bool:
    app = current_app
    if app.config.get("TESTING"):
        app.extensions.setdefault("outbox", []).append({"to": to, "subject": subject, "body": body})
        return True

    host = app.config["SMTP_HOST"]
    if not host:
        # No email service configured. In development we print the message so you can click the link.
        if app.debug:
            app.logger.warning("EMAIL (not sent, SMTP not configured)\nTo: %s\nSubject: %s\n\n%s", to, subject, body)
        else:
            app.logger.warning("Email to %s not sent: SMTP is not configured.", to)
        return False

    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = app.config["MAIL_FROM"], to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, app.config["SMTP_PORT"], timeout=15) as smtp:
            smtp.starttls()
            if app.config["SMTP_USER"]:
                smtp.login(app.config["SMTP_USER"], app.config["SMTP_PASSWORD"])
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        app.logger.error("Could not send email to %s: %s", to, type(exc).__name__)
        return False
