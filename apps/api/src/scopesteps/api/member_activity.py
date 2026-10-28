"""Binds `identity.client.get_member_activity` to the activity log, which builds on identity."""

from scopesteps.audit.client import (
    AuditActor,
    EventType,
    Subject,
    SubjectKind,
    audit_recorder,
)
from scopesteps.identity.client import MemberActivity, MemberEvent
from scopesteps.infrastructure.http import SessionDep


def resolve_member_activity(session: SessionDep) -> MemberActivity:
    recorder = audit_recorder(session)

    class _Recorder:
        def record(self, event: MemberEvent) -> None:
            subjects = [Subject(SubjectKind.PROJECT, event.project_id)]
            if event.member_id is not None:
                subjects.append(Subject(SubjectKind.USER, event.member_id))
            if event.invitation_id is not None:
                subjects.append(Subject(SubjectKind.INVITATION, event.invitation_id))
            recorder.record(
                project_id=event.project_id,
                actor=AuditActor.user(event.actor),
                type=EventType(event.kind),
                subjects=subjects,
                summary=event.summary,
                occurred_at=event.occurred_at,
            )

    return _Recorder()
