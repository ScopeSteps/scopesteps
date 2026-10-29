"""The emails ScopeSteps sends and the port that sends them (ADR 0019).

Use cases only build messages; the HTTP layer sends them once the transaction that made them has
committed, so a rolled-back action never emails anyone. Every name in a message is escaped in the
HTML part, and a message carries nothing from the project beyond its name.
"""

import html
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from scopesteps.identity.client import Role


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


_ROLE_NAMES = {Role.VIEWER: "Viewer", Role.EDITOR: "Editor", Role.APPROVER: "Approver"}
_ROLE_ORDER = (Role.VIEWER, Role.EDITOR, Role.APPROVER)


def role_names(roles: Collection[Role]) -> str:
    """ "Viewer", "Editor and Approver", in a fixed order."""
    names = [_ROLE_NAMES[role] for role in _ROLE_ORDER if role in roles]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _when(moment: datetime) -> str:
    return moment.strftime("%d %B %Y at %H:%M UTC")


def _layout(paragraphs: list[str], link: str, action: str) -> str:
    body = "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)
    url = html.escape(link, quote=True)
    return (
        '<!doctype html><html><body style="font-family: sans-serif; line-height: 1.5">'
        f'{body}<p><a href="{url}">{html.escape(action)}</a></p>'
        f"<p>Or copy this link into your browser:<br>{url}</p>"
        "</body></html>"
    )


def invitation_email(
    *,
    to: str,
    inviter: str,
    project: str,
    roles: Collection[Role],
    link: str,
    expires_at: datetime,
) -> EmailMessage:
    named = role_names(roles)
    text = (
        f"{inviter} invited you to the project {project} on ScopeSteps as {named}.\n\n"
        f"Join the project: {link}\n\n"
        f"The link works once and expires on {_when(expires_at)}. If you did not expect this "
        "invitation, you can ignore this email.\n"
    )
    return EmailMessage(
        to=to,
        subject=f"You're invited to {project} on ScopeSteps",
        text=text,
        html=_layout(
            [
                f"{html.escape(inviter)} invited you to the project "
                f"<strong>{html.escape(project)}</strong> on ScopeSteps as {named}.",
                f"The link works once and expires on {_when(expires_at)}. If you did not expect "
                "this invitation, you can ignore this email.",
            ],
            link,
            "Join the project",
        ),
    )


def confirmation_email(*, to: str, name: str, link: str, expires_at: datetime) -> EmailMessage:
    text = (
        f"Hello {name},\n\n"
        f"Confirm your email address to start using ScopeSteps: {link}\n\n"
        f"The link works once and expires on {_when(expires_at)}. If you did not create an "
        "account, you can ignore this email.\n"
    )
    return EmailMessage(
        to=to,
        subject="Confirm your email address for ScopeSteps",
        text=text,
        html=_layout(
            [
                f"Hello {html.escape(name)},",
                "Confirm your email address to start using ScopeSteps.",
                f"The link works once and expires on {_when(expires_at)}. If you did not create "
                "an account, you can ignore this email.",
            ],
            link,
            "Confirm my email address",
        ),
    )


def account_exists_email(*, to: str, sign_in_link: str) -> EmailMessage:
    text = (
        "Someone, perhaps you, tried to create a ScopeSteps account with this email address. "
        f"You already have one, so sign in instead: {sign_in_link}\n\n"
        "If it was not you, you can ignore this email; nothing was changed.\n"
    )
    return EmailMessage(
        to=to,
        subject="You already have a ScopeSteps account",
        text=text,
        html=_layout(
            [
                "Someone, perhaps you, tried to create a ScopeSteps account with this email "
                "address. You already have one, so sign in instead.",
                "If it was not you, you can ignore this email; nothing was changed.",
            ],
            sign_in_link,
            "Sign in",
        ),
    )
