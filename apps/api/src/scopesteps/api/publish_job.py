"""The background sender for Jira publishes (ADR 0029): a daemon thread in the API process, or,
with `JIRA_PUBLISH_WORKER=separate`, the same loop in its own process (`scopesteps-jira-worker`).

Several senders are safe: each publish is claimed under a lease before anything is sent.
"""

import logging
import signal
import threading
from types import FrameType

from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import State

from scopesteps.api.settings import get_settings
from scopesteps.infrastructure.database import create_database_engine, create_session_factory
from scopesteps.jira_integration.client import JiraRuntime, send_due_publishes

logger = logging.getLogger(__name__)


class PublishJob:
    """Reads the session factory and the Jira runtime from `state` on every round."""

    def __init__(self, state: State) -> None:
        self._state = state
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> int:
        """One round; returns how many publishes moved."""
        session_factory: sessionmaker[Session] = self._state.session_factory
        runtime: JiraRuntime = self._state.jira_runtime
        return send_due_publishes(session_factory, runtime)

    def run(self, interval_seconds: float) -> None:
        """Rounds until stopped. A round that moved something is followed at once by the next."""
        while not self._stop.is_set():
            try:
                moved = self.tick()
            except Exception:
                # By type only, and the next round tries again: one bad row must not stop it.
                logger.exception("Jira publish job failed")
                moved = 0
            if moved == 0 and self._stop.wait(interval_seconds):
                return

    def start(self, interval_seconds: float) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self.run, args=(interval_seconds,), name="jira-publish-job", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Lets the round in progress finish the item it is on, then stops."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=30)


def main() -> None:
    """`scopesteps-jira-worker`: the background sender on its own, for a separate process."""
    from scopesteps.api.main import jira_runtime_for

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    state = State()
    state.session_factory = create_session_factory(engine)
    state.jira_runtime = jira_runtime_for(settings)
    job = PublishJob(state)

    def stop(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        job.stop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    job.run(settings.jira_publish_interval_seconds)
    engine.dispose()
