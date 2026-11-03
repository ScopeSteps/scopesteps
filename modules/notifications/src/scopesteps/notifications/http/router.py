from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from scopesteps.identity.client import Actor, UserDirectory, get_actor, get_user_directory
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import SessionDep
from scopesteps.notifications.application import notifications
from scopesteps.notifications.application.notifications import NotificationView, Readers
from scopesteps.notifications.client import NotificationId
from scopesteps.notifications.domain.notification import EmailSettings
from scopesteps.notifications.http.schemas import (
    NotificationItemResponse,
    NotificationPageResponse,
    NotificationResponse,
    NotificationSettings,
    UnreadCountResponse,
)
from scopesteps.notifications.infrastructure.repository import (
    BacklogItems,
    SqlNotificationStore,
    SqlSettingsStore,
)
from scopesteps.projects.client import ProjectReader, get_project_reader

router = APIRouter(tags=["notifications"])

ActorDep = Annotated[Actor, Depends(get_actor)]
DirectoryDep = Annotated[UserDirectory, Depends(get_user_directory)]
ProjectsDep = Annotated[ProjectReader, Depends(get_project_reader)]


@router.get("/me/notifications")
def list_notifications(
    actor: ActorDep,
    directory: DirectoryDep,
    projects: ProjectsDep,
    session: SessionDep,
    unread: Annotated[bool, Query(description="Only those not read yet.")] = False,
    limit: Annotated[
        int, Query(ge=1, le=notifications.MAX_PAGE_SIZE)
    ] = notifications.DEFAULT_PAGE_SIZE,
    cursor: Annotated[
        str | None, Query(max_length=200, description="`next_cursor` of the previous page.")
    ] = None,
) -> NotificationPageResponse:
    """Your notifications, newest first, without those of projects you no longer belong to."""
    page = notifications.list_notifications(
        SqlNotificationStore(session),
        Readers(directory, projects, BacklogItems(session)),
        actor,
        unread_only=unread,
        cursor=cursor,
        limit=limit,
    )
    return NotificationPageResponse(
        notifications=[_notification(view) for view in page.notifications],
        next_cursor=page.next_cursor,
    )


@router.get("/me/notifications/unread-count")
def unread_count(
    actor: ActorDep, directory: DirectoryDep, session: SessionDep
) -> UnreadCountResponse:
    return UnreadCountResponse(
        unread=notifications.unread_count(SqlNotificationStore(session), directory, actor)
    )


@router.post("/me/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(actor: ActorDep, session: SessionDep) -> None:
    notifications.mark_all_read(SqlNotificationStore(session), actor, utc_now())
    session.commit()


@router.post("/me/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(
    notification_id: NotificationId,
    actor: ActorDep,
    directory: DirectoryDep,
    session: SessionDep,
) -> None:
    """404 for a notification that is not yours. Reading one twice changes nothing."""
    notifications.mark_read(
        SqlNotificationStore(session), directory, actor, notification_id, utc_now()
    )
    session.commit()


@router.get("/me/notification-settings")
def get_notification_settings(actor: ActorDep, session: SessionDep) -> NotificationSettings:
    return _settings(notifications.get_settings(SqlSettingsStore(session), actor))


@router.put("/me/notification-settings")
def save_notification_settings(
    body: NotificationSettings, actor: ActorDep, session: SessionDep
) -> NotificationSettings:
    """Choose which notifications also come by email."""
    saved = notifications.save_settings(
        SqlSettingsStore(session),
        actor,
        EmailSettings(email_on_mention=body.email_on_mention, email_on_reply=body.email_on_reply),
    )
    session.commit()
    return _settings(saved)


def _settings(settings: EmailSettings) -> NotificationSettings:
    return NotificationSettings(
        email_on_mention=settings.email_on_mention, email_on_reply=settings.email_on_reply
    )


def _notification(view: NotificationView) -> NotificationResponse:
    n, item = view.notification, view.item
    return NotificationResponse(
        id=n.id,
        kind=n.kind,
        project_id=n.project_id,
        project_name=view.project_name,
        item=None
        if item is None
        else NotificationItemResponse(id=item.id, kind=item.kind, title=item.title),
        thread_id=n.thread_id,
        comment_id=n.comment_id,
        actor_id=n.actor_id,
        actor_name=view.actor_name,
        created_at=n.created_at,
        read_at=n.read_at,
    )
