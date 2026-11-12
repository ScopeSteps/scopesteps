"""`JiraNotices` through the notifications module: in-app notices, and emails its job sends."""

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy.orm import Session

from scopesteps.identity.client import Role, UserDirectory
from scopesteps.jira_integration.domain.connection import JiraConnection, TokenNotice
from scopesteps.jira_integration.domain.publish import Publish
from scopesteps.notifications.client import NewNotification, notifier


class NotificationNotices:
    def __init__(self, session: Session, directory: UserDirectory) -> None:
        self._notifier = notifier(session)
        self._directory = directory

    def publish_finished(self, publish: Publish, counts: Mapping[str, int], now: datetime) -> None:
        self._notifier.notify(
            [
                NewNotification(
                    recipient=publish.created_by,
                    kind="jira_published" if publish.status == "done" else "jira_publish_failed",
                    project_id=publish.project_id,
                    item_id=None,
                    thread_id=None,
                    comment_id=None,
                    actor_id=publish.created_by,
                    created_at=now,
                    subject_id=publish.id,
                    version_id=publish.version_id,
                    details=dict(counts),
                )
            ]
        )

    def token_needs_attention(
        self, connection: JiraConnection, notice: TokenNotice, now: datetime
    ) -> None:
        approvers = [
            member
            for member in self._directory.members(connection.project_id)
            if member.role is Role.APPROVER
        ]
        self._notifier.notify(
            [
                NewNotification(
                    recipient=approver.user_id,
                    kind="jira_token_expiring"
                    if notice.reason == "expiring"
                    else "jira_token_stopped",
                    project_id=connection.project_id,
                    item_id=None,
                    thread_id=None,
                    comment_id=None,
                    actor_id=connection.connected_by,
                    created_at=now,
                    subject_id=notice.key,
                    details=None if notice.days_left is None else {"days_left": notice.days_left},
                )
                for approver in approvers
            ]
        )
