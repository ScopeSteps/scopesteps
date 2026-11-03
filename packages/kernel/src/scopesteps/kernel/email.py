"""The port every module sends email through (ADR 0019), and the page all messages share."""

import html
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str


class EmailSendError(Exception):
    """The email service refused the message or could not be reached."""


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None:
        """Deliver one message, or raise `EmailSendError`."""
        ...


def email_layout(paragraphs: list[str], link: str, action: str) -> str:
    """`paragraphs` are HTML: the caller has escaped every name in them."""
    body = "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)
    url = html.escape(link, quote=True)
    return (
        '<!doctype html><html><body style="font-family: sans-serif; line-height: 1.5">'
        f'{body}<p><a href="{url}">{html.escape(action)}</a></p>'
        f"<p>Or copy this link into your browser:<br>{url}</p>"
        "</body></html>"
    )
