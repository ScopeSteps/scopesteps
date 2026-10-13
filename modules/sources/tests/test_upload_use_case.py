from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest

from scopesteps.audit.client import AuditActor, EventType, Subject, SubjectKind
from scopesteps.identity.client import Actor, ProjectAccess, Role, UserId
from scopesteps.kernel.errors import NotFoundError, PermissionDeniedError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.application.reading import list_current_sources, list_source_blocks
from scopesteps.sources.application.upload import UploadReceipt, UploadSources, upload_sources
from scopesteps.sources.client import SourceVersionId
from scopesteps.sources.domain.errors import IdempotencyKeyReusedError, SourceTooLargeError
from scopesteps.sources.domain.source import Source, SourceBlock, SourceKind, SourceVersion
from scopesteps.sources.domain.upload import SourceLimits, UploadedFile

PROJECT = ProjectId(UUID("019a3a5e-0000-7000-8000-0000000000a1"))
OTHER_PROJECT = ProjectId(UUID("019a3a5e-0000-7000-8000-0000000000a2"))
ACTOR = Actor(user_id=UserId(UUID("019a3a5e-0000-7000-8000-0000000000b1")), display_name="Dana")
LIMITS = SourceLimits(max_bytes=1024, max_words=100)
NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


class InMemorySourceStore:
    def __init__(self) -> None:
        self.sources: list[Source] = []
        self.versions: list[SourceVersion] = []
        self.blocks_by_version: dict[SourceVersionId, list[SourceBlock]] = {}
        self.receipts: list[UploadReceipt] = []

    def find_receipt(
        self, project_id: ProjectId, actor_id: UserId, idempotency_key: str
    ) -> UploadReceipt | None:
        for receipt in self.receipts:
            if (receipt.project_id, receipt.actor_id, receipt.idempotency_key) == (
                project_id,
                actor_id,
                idempotency_key,
            ):
                return receipt
        return None

    def add_receipt(self, receipt: UploadReceipt) -> None:
        self.receipts.append(receipt)

    def get_versions(self, version_ids: Sequence[SourceVersionId]) -> list[SourceVersion]:
        by_id = {version.id: version for version in self.versions}
        return [by_id[version_id] for version_id in version_ids]

    def latest_version(self, project_id: ProjectId, kind: SourceKind) -> SourceVersion | None:
        matching = [v for v in self.versions if (v.project_id, v.kind) == (project_id, kind)]
        return max(matching, key=lambda version: version.version, default=None)

    def add_source(self, source: Source) -> None:
        self.sources.append(source)

    def add_version(self, version: SourceVersion, text: str, blocks: Sequence[SourceBlock]) -> None:
        self.versions.append(version)
        self.blocks_by_version[version.id] = list(blocks)

    def current_versions(self, project_id: ProjectId) -> list[SourceVersion]:
        latest = (self.latest_version(project_id, kind) for kind in SourceKind)
        return [version for version in latest if version is not None]

    def get_version(
        self, project_id: ProjectId, version_id: SourceVersionId
    ) -> SourceVersion | None:
        for version in self.versions:
            if (version.project_id, version.id) == (project_id, version_id):
                return version
        return None

    def blocks(self, version_id: SourceVersionId) -> list[SourceBlock]:
        return self.blocks_by_version[version_id]


@dataclass(frozen=True)
class Recorded:
    actor: AuditActor
    type: EventType
    subjects: tuple[Subject, ...]
    summary: str


class RecordedAudit:
    def __init__(self) -> None:
        self.events: list[Recorded] = []

    def record(
        self,
        *,
        project_id: ProjectId,
        actor: AuditActor,
        type: EventType,  # noqa: A002
        subjects: Sequence[Subject],
        summary: str,
        occurred_at: datetime,
    ) -> None:
        self.events.append(Recorded(actor, type, tuple(subjects), summary))


def _access(*roles: Role, project_id: ProjectId = PROJECT) -> ProjectAccess:
    return ProjectAccess(actor=ACTOR, project_id=project_id, roles=frozenset(roles))


def _command(
    key: str = "key-0001", brief: bytes = b"Brief.\n\nGoal.", transcript: bytes = b"Dana: yes."
) -> UploadSources:
    return UploadSources(
        idempotency_key=key,
        files=(
            UploadedFile(kind=SourceKind.BRIEF, filename="brief.md", content=brief),
            UploadedFile(kind=SourceKind.TRANSCRIPT, filename="call.txt", content=transcript),
        ),
    )


def test_upload_stores_version_one_of_each_document_with_its_blocks() -> None:
    store = InMemorySourceStore()

    brief, transcript = upload_sources(
        store, RecordedAudit(), _access(Role.EDITOR), _command(), LIMITS, NOW
    )

    assert (brief.kind, brief.version, brief.block_count) == (SourceKind.BRIEF, 1, 2)
    assert (transcript.kind, transcript.version) == (SourceKind.TRANSCRIPT, 1)
    assert brief.source_id != transcript.source_id
    assert brief.uploaded_by == ACTOR.user_id
    assert [block.text for block in store.blocks(brief.id)] == ["Brief.", "Goal."]
    assert {block.source_version_id for block in store.blocks(brief.id)} == {brief.id}


def test_retrying_a_command_returns_the_same_versions_without_storing_more() -> None:
    store = InMemorySourceStore()
    access = _access(Role.EDITOR)
    first = upload_sources(store, RecordedAudit(), access, _command(), LIMITS, NOW)

    second = upload_sources(store, RecordedAudit(), access, _command(), LIMITS, NOW)

    assert second == first
    assert len(store.versions) == 2
    assert len(store.receipts) == 1


def test_reusing_a_key_for_different_content_is_rejected() -> None:
    store = InMemorySourceStore()
    access = _access(Role.EDITOR)
    upload_sources(store, RecordedAudit(), access, _command(), LIMITS, NOW)

    with pytest.raises(IdempotencyKeyReusedError):
        upload_sources(store, RecordedAudit(), access, _command(brief=b"Changed."), LIMITS, NOW)

    assert len(store.versions) == 2


def test_changed_content_becomes_the_next_version_of_the_same_source() -> None:
    store = InMemorySourceStore()
    access = _access(Role.EDITOR)
    brief_v1, transcript_v1 = upload_sources(
        store, RecordedAudit(), access, _command(), LIMITS, NOW
    )

    brief_v2, transcript_again = upload_sources(
        store,
        RecordedAudit(),
        access,
        _command(key="key-0002", brief=b"Revised brief."),
        LIMITS,
        NOW,
    )

    assert (brief_v2.source_id, brief_v2.version) == (brief_v1.source_id, 2)
    assert brief_v2.id != brief_v1.id
    assert transcript_again == transcript_v1
    assert store.blocks(brief_v1.id)[0].text == "Brief."
    assert list_current_sources(store, access) == [brief_v2, transcript_v1]


def test_one_invalid_file_means_nothing_is_stored() -> None:
    store = InMemorySourceStore()

    with pytest.raises(SourceTooLargeError):
        upload_sources(
            store,
            RecordedAudit(),
            _access(Role.EDITOR),
            _command(transcript=b"x" * 2000),
            LIMITS,
            NOW,
        )

    assert (store.sources, store.versions, store.receipts) == ([], [], [])


def test_upload_requires_the_editor_role() -> None:
    store = InMemorySourceStore()

    with pytest.raises(PermissionDeniedError):
        upload_sources(store, RecordedAudit(), _access(Role.VIEWER), _command(), LIMITS, NOW)

    assert store.versions == []


def test_non_members_are_told_the_project_does_not_exist() -> None:
    store = InMemorySourceStore()
    brief, _ = upload_sources(store, RecordedAudit(), _access(Role.EDITOR), _command(), LIMITS, NOW)

    with pytest.raises(NotFoundError):
        upload_sources(store, RecordedAudit(), _access(), _command(key="key-0002"), LIMITS, NOW)
    with pytest.raises(NotFoundError):
        list_current_sources(store, _access())
    with pytest.raises(NotFoundError):
        list_source_blocks(store, _access(), brief.id)


def test_a_version_cannot_be_read_through_another_project() -> None:
    store = InMemorySourceStore()
    brief, _ = upload_sources(store, RecordedAudit(), _access(Role.EDITOR), _command(), LIMITS, NOW)

    with pytest.raises(NotFoundError):
        list_source_blocks(store, _access(Role.VIEWER, project_id=OTHER_PROJECT), brief.id)


def test_any_member_can_read_blocks_in_paragraph_order() -> None:
    store = InMemorySourceStore()
    brief, _ = upload_sources(store, RecordedAudit(), _access(Role.EDITOR), _command(), LIMITS, NOW)

    blocks = list_source_blocks(store, _access(Role.VIEWER), brief.id)

    assert [block.ordinal for block in blocks] == [1, 2]


def test_each_new_version_is_recorded_once_as_the_uploader_s_action() -> None:
    store, audit = InMemorySourceStore(), RecordedAudit()
    access = _access(Role.EDITOR)

    brief, transcript = upload_sources(store, audit, access, _command(), LIMITS, NOW)
    upload_sources(store, audit, access, _command(), LIMITS, NOW)
    brief_v2, _ = upload_sources(
        store, audit, access, _command(key="key-0002", brief=b"Revised brief."), LIMITS, NOW
    )

    assert audit.events == [
        Recorded(
            AuditActor.user(ACTOR),
            EventType.SOURCE_ADDED,
            (
                Subject(SubjectKind.SOURCE, version.source_id),
                Subject(SubjectKind.SOURCE_VERSION, version.id),
            ),
            summary,
        )
        for version, summary in (
            (brief, "Added the brief brief.md (version 1)"),
            (transcript, "Added the transcript call.txt (version 1)"),
            (brief_v2, "Added the brief brief.md (version 2)"),
        )
    ]


def test_a_rejected_upload_records_nothing() -> None:
    audit = RecordedAudit()

    with pytest.raises(SourceTooLargeError):
        upload_sources(
            InMemorySourceStore(),
            audit,
            _access(Role.EDITOR),
            _command(transcript=b"x" * 2000),
            LIMITS,
            NOW,
        )

    assert audit.events == []


def test_a_long_filename_is_shortened_in_the_summary() -> None:
    audit = RecordedAudit()
    command = UploadSources(
        idempotency_key="key-0001",
        files=(
            UploadedFile(kind=SourceKind.BRIEF, filename="b" * 240 + ".md", content=b"Brief."),
            UploadedFile(kind=SourceKind.TRANSCRIPT, filename="call.txt", content=b"Dana: yes."),
        ),
    )

    upload_sources(InMemorySourceStore(), audit, _access(Role.EDITOR), command, LIMITS, NOW)

    assert audit.events[0].summary == f"Added the brief {'b' * 119}… (version 1)"
