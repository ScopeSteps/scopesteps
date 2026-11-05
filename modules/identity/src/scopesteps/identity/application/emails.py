"""The account and invitation emails ScopeSteps sends (ADR 0019).

Use cases only build messages; the HTTP layer sends them once the transaction that made them has
committed, so a rolled-back action never emails anyone. Every name in a message is escaped in the
HTML part, and a message carries nothing from the project beyond its name.
"""

import html
from datetime import datetime

from scopesteps.identity.client import ROLE_NAMES, Role
from scopesteps.kernel.email import EmailMessage, email_layout


def _when(moment: datetime) -> str:
    return moment.strftime("%d %B %Y at %H:%M UTC")


def invitation_email(
    *,
    to: str,
    inviter: str,
    project: str,
    role: Role,
    link: str,
    expires_at: datetime,
) -> EmailMessage:
    named = ROLE_NAMES[role]
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
        html=email_layout(
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
        html=email_layout(
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
        html=email_layout(
            [
                "Someone, perhaps you, tried to create a ScopeSteps account with this email "
                "address. You already have one, so sign in instead.",
                "If it was not you, you can ignore this email; nothing was changed.",
            ],
            sign_in_link,
            "Sign in",
        ),
    )
