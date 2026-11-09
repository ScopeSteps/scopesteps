"""Saving the agent's task suggestions on a draft (the "Suggest tasks" run).

Suggestions land on the draft only, never on a version in review or an approved one, and only
under stories it still has. A person then accepts, edits or deletes each one through the item
edit, which is where every other change to a task is made.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.backlog.application.editing import DraftStore, require_draft
from scopesteps.backlog.domain.editing import VersionChangedError
from scopesteps.backlog.domain.ids import BacklogVersionId, ItemId
from scopesteps.backlog.domain.tasks import with_suggested_tasks
from scopesteps.backlog.domain.version import Item, content_hash
from scopesteps.kernel.errors import NotFoundError
from scopesteps.kernel.ids import new_id


@dataclass(frozen=True)
class SavedSuggestions:
    revision: int
    """The draft's revision after saving, or as it was when nothing was added."""
    tasks: int
    stories: int


def save_task_suggestions(
    store: DraftStore,
    audit: AuditRecorder,
    version_id: BacklogVersionId,
    suggested: Mapping[ItemId, Sequence[str]],
    *,
    run_id: UUID,
    now: datetime,
) -> SavedSuggestions:
    """Put each story's suggested task titles on the draft, as one revision, in the caller's
    transaction. A story no longer in the draft is skipped.

    Raises VersionNotDraftError once the draft was approved or rejected, and VersionChangedError
    when someone saved it meanwhile; the caller may try again on the new revision.
    """
    version = store.get(version_id)
    if version is None:
        raise NotFoundError("Backlog version not found")
    require_draft(version)
    stories = {item.id: item for item in version.items if item.kind == "story"}
    changed: list[Item] = []
    added = 0
    for story_id, titles in suggested.items():
        story = stories.get(story_id)
        if story is None:
            continue
        updated, count = with_suggested_tasks(story, titles, new_id)
        if updated != story:
            changed.append(updated)
            added += count
    if not changed:
        return SavedSuggestions(version.revision, 0, 0)
    by_id = {item.id: item for item in changed}
    items = tuple(by_id.get(item.id, item) for item in version.items)
    new_hash = content_hash(items, version.decisions, version.out_of_scope)
    if not store.save_items(
        version, changed, expected_revision=version.revision, content_hash=new_hash
    ):
        raise VersionChangedError("The draft changed while the suggestions were being saved.")
    audit.record(
        project_id=version.project_id,
        actor=AuditActor.agent(),
        type=EventType.BACKLOG_TASKS_SUGGESTED,
        subjects=(
            Subject(SubjectKind.BACKLOG_VERSION, version.id),
            Subject(SubjectKind.RUN, run_id),
            *(Subject(SubjectKind.ITEM, item.id) for item in changed),
        ),
        summary=f"Suggested {added} {'task' if added == 1 else 'tasks'} for "
        f"{len(changed)} {'story' if len(changed) == 1 else 'stories'} in draft revision "
        f"{version.revision}",
        occurred_at=now,
    )
    return SavedSuggestions(version.revision + 1, added, len(changed))
