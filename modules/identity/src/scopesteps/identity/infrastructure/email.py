"""Email delivery adapters for the `EmailSender` port (ADR 0019).

Postmark, Resend and Amazon SES all accept SMTP, so the service is chosen by settings alone. In
development the SMTP settings point at a local Mailpit inbox, so no email reaches a real person.
"""

import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, make_msgid

from scopesteps.identity.application.emails import EmailMessage, EmailSendError

# Port 465 speaks TLS from the first byte; any other port is upgraded with STARTTLS when the
# server offers it, and must offer it whenever credentials are sent.
IMPLICIT_TLS_PORT = 465


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    sender: str
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    timeout_seconds: float = 10.0


class SmtpEmailSender:
    def __init__(self, settings: SmtpSettings) -> None:
        self._settings = settings

    def send(self, message: EmailMessage) -> None:
        settings = self._settings
        mime = MimeMessage()
        mime["From"] = formataddr(("ScopeSteps", settings.sender))
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime["Message-ID"] = make_msgid(domain=settings.sender.rpartition("@")[2] or None)
        mime.set_content(message.text)
        mime.add_alternative(message.html, subtype="html")
        try:
            with self._connect() as smtp:
                if settings.username and settings.password:
                    smtp.login(settings.username, settings.password)
                smtp.send_message(mime)
        except (smtplib.SMTPException, OSError) as error:
            # The message is not in the error, so it never carries a link into the logs.
            raise EmailSendError(type(error).__name__) from None

    def _connect(self) -> smtplib.SMTP:
        settings = self._settings
        context = ssl.create_default_context()
        if settings.port == IMPLICIT_TLS_PORT:
            return smtplib.SMTP_SSL(
                settings.host, settings.port, timeout=settings.timeout_seconds, context=context
            )
        smtp = smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout_seconds)
        smtp.ehlo()
        if smtp.has_extn("starttls"):
            smtp.starttls(context=context)
            smtp.ehlo()
        elif settings.username:
            smtp.quit()
            raise EmailSendError("The SMTP server does not offer STARTTLS for credentials")
        return smtp


class RecordingEmailSender:
    """Keeps every message in memory instead of sending it, for tests. `fail` makes the next
    sends raise, as an unreachable service would."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = False

    def send(self, message: EmailMessage) -> None:
        if self.fail:
            raise EmailSendError("unavailable")
        self.sent.append(message)
