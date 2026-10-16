from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from scopesteps.audit.client import AuditActor, EventType, Subject, SubjectKind
from scopesteps.identity.client import Actor, ProjectAccess, Role, UserId
from scopesteps.kernel.errors import NotFoundError, PermissionDeniedError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.application.reading import list_current_sources, list_source_blocks
from scopesteps.sources.application.removal import SourceUse, remove_source
from scopesteps.sources.application.speakers import list_source_speakers
from scopesteps.sources.application.upload import (
    MAX_FILES_PER_UPLOAD,
    AddSourceVersion,
    UploadReceipt,
    UploadSources,
    add_source_version,
    record_change_request,
    upload_sources,
)
from scopesteps.sources.client import SourceId, SourceVersionId
from scopesteps.sources.domain.errors import (
    IdempotencyKeyReusedError,
    NoSourceFilesError,
    SourceInUseError,
    SourceRemovedError,
    SourceTooLargeError,
    SourceWordLimitError,
    TooManySourceFilesError,
)
from scopesteps.sources.domain.source import (
    Source,
    SourceBlock,
    SourceKind,
    SourceVersion,
    SpeakerLabel,
)
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
        self.texts: dict[SourceVersionId, str] = {}
        self.labels: dict[SourceVersionId, list[SpeakerLabel]] = {}
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

    def get_source(self, project_id: ProjectId, source_id: SourceId) -> Source | None:
        return next(
            (s for s in self.sources if (s.project_id, s.id) == (project_id, source_id)), None
        )

    def latest_version_of(self, source_id: SourceId) -> SourceVersion:
        return max((v for v in self.versions if v.source_id == source_id), key=lambda v: v.version)

    def next_source_number(self, project_id: ProjectId) -> int:
        return 1 + max((s.number for s in self.sources if s.project_id == project_id), default=0)

    def add_source(self, source: Source) -> None:
        self.sources.append(source)

    def add_version(self, version: SourceVersion, text: str, blocks: Sequence[SourceBlock]) -> None:
        self.versions.append(version)
        self.blocks_by_version[version.id] = list(blocks)
        self.texts[version.id] = text

    def version_text(self, version_id: SourceVersionId) -> str:
        return self.texts[version_id]

    def speaker_labels(self, version_id: SourceVersionId) -> list[SpeakerLabel] | None:
        return self.labels.get(version_id)

    def add_speaker_labels(
        self, version_id: SourceVersionId, labels: Sequence[SpeakerLabel], detected_at: datetime
    ) -> None:
        assert version_id not in self.labels, "labels are stored once per version"
        self.labels[version_id] = list(labels)

    def current_versions(self, project_id: ProjectId) -> list[SourceVersion]:
        return [
            self.latest_version_of(source.id)
            for source in sorted(self.sources, key=lambda s: s.number)
            if source.project_id == project_id
            and not source.is_removed
            and source.kind is not SourceKind.CHANGE_REQUEST
        ]

    def get_version(
        self, project_id: ProjectId, version_id: SourceVersionId
    ) -> SourceVersion | None:
        for version in self.versions:
            if (version.project_id, version.id) == (project_id, version_id):
                return version
        return None

    def blocks(self, version_id: SourceVersionId) -> list[SourceBlock]:
        return self.blocks_by_version[version_id]

    def version_ids(self, source_id: SourceId) -> list[SourceVersionId]:
        return [v.id for v in self.versions if v.source_id == source_id]

    def mark_removed(self, source_id: SourceId, removed_by: UserId, removed_at: datetime) -> bool:
        for index, source in enumerate(self.sources):
            if source.id == source_id and not source.is_removed:
                self.sources[index] = replace(source, removed_at=removed_at, removed_by=removed_by)
                return True
        return False


class Usage:
    """A usage reader that reports the given uses for any version in `used`."""

    def __init__(self, used: Collection[SourceVersionId] = (), *uses: SourceUse) -> None:
        self.used = set(used)
        self.uses = list(uses)

    def __call__(
        self, project_id: ProjectId, version_ids: Collection[SourceVersionId]
    ) -> list[SourceUse]:
        return self.uses if self.used & set(version_ids) else []


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


def _upload_one(
    store: InMemorySourceStore,
    content: bytes,
    *,
    key: str,
    kind: SourceKind = SourceKind.SUPPORTING_DOCUMENT,
    filename: str = "notes.md",
    audit: RecordedAudit | None = None,
) -> SourceVersion:
    [version] = upload_sources(
        store,
        audit or RecordedAudit(),
        _access(Role.EDITOR),
        UploadSources(key, (UploadedFile(kind=kind, filename=filename, content=content),)),
        LIMITS,
        NOW,
    )
    return version


def _new_version(
    store: InMemorySourceStore, source_id: SourceId, content: bytes, *, key: str
) -> SourceVersion:
    return add_source_version(
        store,
        RecordedAudit(),
        _access(Role.EDITOR),
        AddSourceVersion(key, source_id, "brief-revised.md", content),
        LIMITS,
        NOW,
    )


def test_upload_stores_each_file_as_version_one_of_a_new_numbered_source() -> None:
    store = InMemorySourceStore()

    brief, transcript = upload_sources(
        store, RecordedAudit(), _access(Role.EDITOR), _command(), LIMITS, NOW
    )

    assert (brief.kind, brief.version, brief.block_count) == (SourceKind.BRIEF, 1, 2)
    assert (transcript.kind, transcript.version) == (SourceKind.TRANSCRIPT, 1)
    assert (brief.source_number, transcript.source_number) == (1, 2)
    assert brief.source_id != transcript.source_id
    assert brief.uploaded_by == ACTOR.user_id
    assert [block.text for block in store.blocks(brief.id)] == ["Brief.", "Goal."]
    assert {block.source_version_id for block in store.blocks(brief.id)} == {brief.id}


def test_a_single_supporting_document_can_be_uploaded_on_its_own() -> None:
    store = InMemorySourceStore()

    notes = _upload_one(store, b"Room list.", key="key-0001")

    assert (notes.kind, notes.version, notes.source_number) == (
        SourceKind.SUPPORTING_DOCUMENT,
        1,
        1,
    )
    assert list_current_sources(store, _access(Role.VIEWER)) == [notes]


def test_several_files_of_one_kind_become_separate_sources() -> None:
    store = InMemorySourceStore()
    command = UploadSources(
        "key-0001",
        tuple(
            UploadedFile(SourceKind.TRANSCRIPT, f"call-{n}.txt", f"Call {n}.".encode())
            for n in (1, 2, 3)
        ),
    )

    versions = upload_sources(store, RecordedAudit(), _access(Role.EDITOR), command, LIMITS, NOW)

    assert [v.source_number for v in versions] == [1, 2, 3]
    assert len({v.source_id for v in versions}) == 3


def test_later_uploads_add_to_the_project_s_sources() -> None:
    store = InMemorySourceStore()
    access = _access(Role.EDITOR)
    brief, transcript = upload_sources(store, RecordedAudit(), access, _command(), LIMITS, NOW)

    notes = _upload_one(store, b"Room list.", key="key-0002")

    assert notes.source_number == 3
    assert list_current_sources(store, access) == [brief, transcript, notes]


def test_an_upload_needs_at_least_one_file_and_at_most_the_limit() -> None:
    store, access = InMemorySourceStore(), _access(Role.EDITOR)
    too_many = tuple(
        UploadedFile(SourceKind.SUPPORTING_DOCUMENT, f"{n}.md", b"x")
        for n in range(MAX_FILES_PER_UPLOAD + 1)
    )

    with pytest.raises(NoSourceFilesError):
        upload_sources(store, RecordedAudit(), access, UploadSources("k-1", ()), LIMITS, NOW)
    with pytest.raises(TooManySourceFilesError):
        upload_sources(store, RecordedAudit(), access, UploadSources("k-2", too_many), LIMITS, NOW)

    assert store.versions == []


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


def test_content_identical_to_a_current_version_returns_that_version() -> None:
    store = InMemorySourceStore()
    access = _access(Role.EDITOR)
    brief, transcript = upload_sources(store, RecordedAudit(), access, _command(), LIMITS, NOW)

    again = _upload_one(store, b"Brief.\n\nGoal.", key="key-0002", filename="copy.md")

    assert again == brief
    assert list_current_sources(store, access) == [brief, transcript]


def test_identical_files_in_one_upload_share_one_new_version() -> None:
    store = InMemorySourceStore()
    command = UploadSources(
        "key-0001",
        (
            UploadedFile(SourceKind.BRIEF, "a.md", b"Same text."),
            UploadedFile(SourceKind.BRIEF, "b.md", b"Same text."),
        ),
    )

    first, second = upload_sources(
        store, RecordedAudit(), _access(Role.EDITOR), command, LIMITS, NOW
    )

    assert first == second
    assert len(store.sources) == 1


def test_the_word_limit_counts_current_sources_plus_the_upload() -> None:
    store = InMemorySourceStore()
    _upload_one(store, b"word " * 60, key="key-0001")

    with pytest.raises(SourceWordLimitError) as raised:
        _upload_one(store, b"more " * 41, key="key-0002", filename="more.md")

    assert raised.value.details == {"word_count": 101, "current_word_count": 60, "max_words": 100}
    assert len(store.sources) == 1


def test_unchanged_content_does_not_count_twice_towards_the_word_limit() -> None:
    store = InMemorySourceStore()
    notes = _upload_one(store, b"word " * 60, key="key-0001")

    again = _upload_one(store, b"word " * 60, key="key-0002")

    assert again == notes


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


def test_corrected_content_becomes_the_next_version_of_the_same_source() -> None:
    store = InMemorySourceStore()
    access = _access(Role.EDITOR)
    brief_v1, transcript = upload_sources(store, RecordedAudit(), access, _command(), LIMITS, NOW)

    brief_v2 = _new_version(store, brief_v1.source_id, b"Revised brief.", key="key-0002")

    assert (brief_v2.source_id, brief_v2.version, brief_v2.source_number) == (
        brief_v1.source_id,
        2,
        1,
    )
    assert store.blocks(brief_v1.id)[0].text == "Brief."
    assert list_current_sources(store, access) == [brief_v2, transcript]


def test_a_new_version_identical_to_the_current_one_returns_it() -> None:
    store = InMemorySourceStore()
    brief, _ = upload_sources(store, RecordedAudit(), _access(Role.EDITOR), _command(), LIMITS, NOW)

    again = _new_version(store, brief.source_id, b"Brief.\n\nGoal.", key="key-0002")

    assert again == brief


def test_a_new_version_counts_in_place_of_the_current_one_for_the_word_limit() -> None:
    store = InMemorySourceStore()
    notes = _upload_one(store, b"word " * 90, key="key-0001")

    revised = _new_version(store, notes.source_id, b"word " * 100, key="key-0002")
    with pytest.raises(SourceWordLimitError):
        _new_version(store, notes.source_id, b"word " * 101, key="key-0003")

    assert revised.word_count == 100


def test_a_new_version_needs_a_source_of_the_project_that_is_not_removed() -> None:
    store = InMemorySourceStore()
    notes = _upload_one(store, b"Room list.", key="key-0001")
    remove_source(store, RecordedAudit(), Usage(), _access(Role.EDITOR), notes.source_id, NOW)

    with pytest.raises(NotFoundError):
        _new_version(store, SourceId(UUID(int=7)), b"Text.", key="key-0002")
    with pytest.raises(SourceRemovedError):
        _new_version(store, notes.source_id, b"Text.", key="key-0003")


def test_each_new_version_is_recorded_once_as_the_uploader_s_action() -> None:
    store, audit = InMemorySourceStore(), RecordedAudit()
    access = _access(Role.EDITOR)

    brief, transcript = upload_sources(store, audit, access, _command(), LIMITS, NOW)
    upload_sources(store, audit, access, _command(), LIMITS, NOW)
    notes = _upload_one(store, b"Room list.", key="key-0002", audit=audit)

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
            (notes, "Added the supporting document notes.md (version 1)"),
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
        files=(UploadedFile(kind=SourceKind.BRIEF, filename="b" * 240 + ".md", content=b"Brief."),),
    )

    upload_sources(InMemorySourceStore(), audit, _access(Role.EDITOR), command, LIMITS, NOW)

    assert audit.events[0].summary == f"Added the brief {'b' * 119}… (version 1)"


def test_an_unused_source_is_removed_from_the_current_set_and_its_versions_kept() -> None:
    store, audit = InMemorySourceStore(), RecordedAudit()
    access = _access(Role.EDITOR)
    brief, transcript = upload_sources(store, RecordedAudit(), access, _command(), LIMITS, NOW)

    removed = remove_source(store, audit, Usage(), access, transcript.source_id, NOW)

    assert (removed.id, removed.number, removed.removed_by) == (
        transcript.source_id,
        2,
        ACTOR.user_id,
    )
    assert list_current_sources(store, access) == [brief]
    assert [b.text for b in list_source_blocks(store, access, transcript.id)] == ["Dana: yes."]
    assert audit.events == [
        Recorded(
            AuditActor.user(ACTOR),
            EventType.SOURCE_REMOVED,
            (Subject(SubjectKind.SOURCE, transcript.source_id),),
            "Removed the transcript call.txt",
        )
    ]


def test_removing_a_removed_source_returns_it_and_records_nothing() -> None:
    store, audit = InMemorySourceStore(), RecordedAudit()
    notes = _upload_one(store, b"Room list.", key="key-0001")
    first = remove_source(store, audit, Usage(), _access(Role.EDITOR), notes.source_id, NOW)

    second = remove_source(store, audit, Usage(), _access(Role.EDITOR), notes.source_id, NOW)

    assert second == first
    assert len(audit.events) == 1


@pytest.mark.parametrize(
    ("uses", "message", "used_by"),
    [
        ([SourceUse("run", UUID(int=1))], "used by 1 run,", {"run": 1}),
        (
            [
                SourceUse("run", UUID(int=1)),
                SourceUse("run", UUID(int=2)),
                SourceUse("backlog_version", UUID(int=3)),
                SourceUse("person", UUID(int=4)),
            ],
            "used by 2 runs, 1 backlog version and 1 person,",
            {"run": 2, "backlog_version": 1, "person": 1},
        ),
    ],
)
def test_a_source_something_refers_to_cannot_be_removed(
    uses: list[SourceUse], message: str, used_by: dict[str, int]
) -> None:
    store, audit = InMemorySourceStore(), RecordedAudit()
    access = _access(Role.EDITOR)
    notes = _upload_one(store, b"Room list.", key="key-0001")

    with pytest.raises(SourceInUseError) as raised:
        remove_source(store, audit, Usage([notes.id], *uses), access, notes.source_id, NOW)

    assert message in raised.value.message
    assert raised.value.details == {"source_id": str(notes.source_id), "used_by": used_by}
    assert list_current_sources(store, access) == [notes]
    assert audit.events == []


def test_a_reference_to_an_earlier_version_also_blocks_removal() -> None:
    store = InMemorySourceStore()
    v1 = _upload_one(store, b"Room list.", key="key-0001")
    _new_version(store, v1.source_id, b"Room list, revised.", key="key-0002")
    usage = Usage([v1.id], SourceUse("run", UUID(int=1)))

    with pytest.raises(SourceInUseError):
        remove_source(store, RecordedAudit(), usage, _access(Role.EDITOR), v1.source_id, NOW)


def test_removal_needs_an_editor_and_a_source_of_the_project() -> None:
    store = InMemorySourceStore()
    notes = _upload_one(store, b"Room list.", key="key-0001")

    with pytest.raises(PermissionDeniedError):
        remove_source(store, RecordedAudit(), Usage(), _access(Role.VIEWER), notes.source_id, NOW)
    with pytest.raises(NotFoundError):
        remove_source(
            store,
            RecordedAudit(),
            Usage(),
            _access(Role.EDITOR, project_id=OTHER_PROJECT),
            notes.source_id,
            NOW,
        )


def test_re_uploading_removed_content_creates_a_new_source() -> None:
    store = InMemorySourceStore()
    notes = _upload_one(store, b"Room list.", key="key-0001")
    remove_source(store, RecordedAudit(), Usage(), _access(Role.EDITOR), notes.source_id, NOW)

    again = _upload_one(store, b"Room list.", key="key-0002")

    assert again.source_id != notes.source_id
    assert again.source_number == 2


def test_removed_sources_do_not_count_towards_the_word_limit() -> None:
    store = InMemorySourceStore()
    notes = _upload_one(store, b"word " * 90, key="key-0001")
    remove_source(store, RecordedAudit(), Usage(), _access(Role.EDITOR), notes.source_id, NOW)

    other = _upload_one(store, b"other " * 90, key="key-0002", filename="other.md")

    assert other.word_count == 90


def test_a_change_request_is_stored_as_evidence_but_is_not_a_current_source() -> None:
    store, audit = InMemorySourceStore(), RecordedAudit()
    access = _access(Role.EDITOR)
    brief, transcript = upload_sources(store, audit, access, _command(), LIMITS, NOW)
    recorded = len(audit.events)

    request = record_change_request(store, PROJECT, "Add weekly bookings.", ACTOR.user_id, NOW)

    assert (request.kind, request.source_number, request.uploaded_by) == (
        SourceKind.CHANGE_REQUEST,
        3,
        ACTOR.user_id,
    )
    assert [b.text for b in list_source_blocks(store, access, request.id)] == [
        "Add weekly bookings."
    ]
    assert list_current_sources(store, access) == [brief, transcript]
    assert len(audit.events) == recorded, "the change request's own event names it"
    with pytest.raises(NotFoundError):
        _new_version(store, request.source_id, b"Something else.", key="key-0002")
    with pytest.raises(NotFoundError):
        remove_source(store, audit, Usage(), access, request.source_id, NOW)


def test_a_transcript_s_speakers_are_detected_when_it_is_stored() -> None:
    store = InMemorySourceStore()
    transcript = b"Mira: Hello.\n\nTomas: Hi.\n\nMira: Bye."

    version = _upload_one(store, transcript, key="key-0001", kind=SourceKind.TRANSCRIPT)

    blocks = store.blocks(version.id)
    assert [
        (label.label, label.turn_count, label.first_block_id) for label in store.labels[version.id]
    ] == [
        ("Mira", 2, blocks[0].id),
        ("Tomas", 1, blocks[1].id),
    ]


def test_other_kinds_are_not_searched_for_speakers() -> None:
    store = InMemorySourceStore()

    version = _upload_one(store, b"Mira: a brief that looks like a turn.", key="key-0001")

    assert version.id not in store.labels
    assert list_source_speakers(store, _access(Role.VIEWER), version.source_id, NOW).speakers == []


def test_a_new_transcript_version_gets_its_own_labels() -> None:
    store = InMemorySourceStore()
    first = _upload_one(store, b"Mira: Hello.", key="key-0001", kind=SourceKind.TRANSCRIPT)

    second = _new_version(store, first.source_id, b"Mira: Hello.\n\nAna: Hi.", key="key-0002")

    assert [label.label for label in store.labels[first.id]] == ["Mira"]
    assert [label.label for label in store.labels[second.id]] == ["Mira", "Ana"]


def test_any_member_lists_the_current_version_s_speakers() -> None:
    store = InMemorySourceStore()
    first = _upload_one(store, b"Mira: Hello.", key="key-0001", kind=SourceKind.TRANSCRIPT)
    second = _new_version(store, first.source_id, b"Ana: Hi.\n\nMira: Hey.", key="key-0002")

    found = list_source_speakers(store, _access(Role.VIEWER), first.source_id, NOW)

    assert found.version == second
    assert [(label.label, label.sample) for label in found.speakers] == [
        ("Ana", "Hi."),
        ("Mira", "Hey."),
    ]


def test_a_transcript_stored_before_detection_gets_its_labels_on_first_read() -> None:
    store = InMemorySourceStore()
    version = _upload_one(store, b"Mira: Hello.", key="key-0001", kind=SourceKind.TRANSCRIPT)
    del store.labels[version.id]

    found = list_source_speakers(store, _access(Role.VIEWER), version.source_id, NOW)

    assert [label.label for label in found.speakers] == ["Mira"]
    assert store.labels[version.id] == found.speakers


@pytest.mark.parametrize("project_id", [OTHER_PROJECT, PROJECT])
def test_speakers_of_another_project_s_or_a_missing_source_are_not_found(
    project_id: ProjectId,
) -> None:
    store = InMemorySourceStore()
    version = _upload_one(store, b"Mira: Hello.", key="key-0001", kind=SourceKind.TRANSCRIPT)
    source_id = version.source_id if project_id == OTHER_PROJECT else SourceId(OTHER_PROJECT)

    with pytest.raises(NotFoundError):
        list_source_speakers(store, _access(Role.EDITOR, project_id=project_id), source_id, NOW)


def test_speakers_need_a_role_on_the_project() -> None:
    store = InMemorySourceStore()
    version = _upload_one(store, b"Mira: Hello.", key="key-0001", kind=SourceKind.TRANSCRIPT)

    with pytest.raises(NotFoundError):
        list_source_speakers(store, _access(), version.source_id, NOW)
