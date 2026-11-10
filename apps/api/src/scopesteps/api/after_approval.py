"""Binds `change_control`'s after-approval step to `jira_integration` (ADR 0029)."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from scopesteps.backlog.client import BacklogVersionId, load_version_summary
from scopesteps.change_control.client import AfterApproval, AfterApprovalResult
from scopesteps.identity.client import ProjectAccessResolver, get_project_access_resolver
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import SessionDep
from scopesteps.jira_integration.client import JiraRuntime, publish_after_approval


def resolve_after_approval(
    request: Request,
    session: SessionDep,
    resolve: Annotated[ProjectAccessResolver, Depends(get_project_access_resolver)],
) -> AfterApproval:
    runtime: JiraRuntime = request.app.state.jira_runtime

    def follow(version_id: UUID, also_publish_to_jira: bool) -> AfterApprovalResult:
        summary = load_version_summary(session, BacklogVersionId(version_id))
        if summary is None or summary.state != "approved":
            return AfterApprovalResult()
        started = publish_after_approval(
            session,
            runtime,
            resolve(summary.project_id),
            version_id,
            also_publish_to_jira,
            utc_now(),
        )
        return AfterApprovalResult(started.publish_id, started.problem)

    return follow
