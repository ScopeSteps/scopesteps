"""The background job behind notifications: due emails, and clearing expired ones once a day.

One daemon thread per API process, because nothing else in the POC runs without a request. Several
processes are safe: the module claims each email before sending it (ADR 0021).
"""

import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import State

from scopesteps.identity.infrastructure.repository import SqlUserDirectory
from scopesteps.infrastructure.database import utc_now
from scopesteps.kernel.email import EmailSender
from scopesteps.notifications.client import delete_expired_notifications, send_due_emails
from scopesteps.projects.http.router import resolve_project_reader

logger = logging.getLogger(__name__)

_CLEAN_UP_EVERY = timedelta(days=1)


class NotificationJob:
    def __init__(self, state: State, base_url: str) -> None:
        self._state = state
        self._base_url = base_url
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_clean_up: datetime | None = None

    def tick(self, now: datetime) -> int:
        """One round of work; returns how many emails were sent."""
        session_factory: sessionmaker[Session] = self._state.session_factory
        sender: EmailSender = self._state.email_sender
        with session_factory() as session:
            if self._next_clean_up is None or now >= self._next_clean_up:
                delete_expired_notifications(session, now)
                session.commit()
                self._next_clean_up = now + _CLEAN_UP_EVERY
            return send_due_emails(
                session,
                SqlUserDirectory(session),
                resolve_project_reader(session),
                sender,
                self._base_url,
                now,
            )

    def start(self, interval_seconds: float) -> None:
        self._stop.clear()

        def loop() -> None:
            while not self._stop.wait(interval_seconds):
                try:
                    self.tick(utc_now())
                except Exception:
                    # By type only, and the next tick tries again: the job must outlive one bad row.
                    logger.exception("Notification job failed")

        self._thread = threading.Thread(target=loop, name="notification-job", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
