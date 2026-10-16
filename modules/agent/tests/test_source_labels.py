from uuid import UUID

from scopesteps.agent.application.ports import Passage
from scopesteps.agent.application.steps import source_blocks
from scopesteps.sources.client import SourceBlockId, SourceVersionId

BRIEF = SourceVersionId(UUID(int=1))
FIRST_CALL = SourceVersionId(UUID(int=2))
SECOND_CALL = SourceVersionId(UUID(int=3))
NOTES = SourceVersionId(UUID(int=4))


def _passage(version: SourceVersionId, kind: str, ordinal: int) -> Passage:
    return Passage(SourceBlockId(UUID(int=100 + ordinal)), version, kind, ordinal, "Text.")


def test_a_kind_pinned_once_is_labelled_by_kind_alone() -> None:
    blocks = source_blocks([_passage(BRIEF, "brief", 1), _passage(FIRST_CALL, "transcript", 1)])

    assert [(b.id, b.label) for b in blocks] == [
        ("B1", "brief paragraph 1"),
        ("B2", "transcript paragraph 1"),
    ]


def test_versions_of_one_kind_are_numbered_in_pinned_order() -> None:
    blocks = source_blocks(
        [
            _passage(SECOND_CALL, "transcript", 1),
            _passage(SECOND_CALL, "transcript", 2),
            _passage(FIRST_CALL, "transcript", 1),
            _passage(NOTES, "supporting_document", 1),
        ]
    )

    assert [b.label for b in blocks] == [
        "transcript 1 paragraph 1",
        "transcript 1 paragraph 2",
        "transcript 2 paragraph 1",
        "supporting document paragraph 1",
    ]


def test_a_single_source_run_numbers_its_blocks_from_b1() -> None:
    blocks = source_blocks([_passage(NOTES, "supporting_document", n) for n in (1, 2)])

    assert [b.id for b in blocks] == ["B1", "B2"]


def test_only_a_change_run_s_own_request_is_the_change_request() -> None:
    earlier = SourceVersionId(UUID(int=5))
    current = SourceVersionId(UUID(int=6))

    blocks = source_blocks(
        [
            _passage(BRIEF, "brief", 1),
            _passage(earlier, "change_request", 1),
            _passage(current, "change_request", 1),
        ],
        current,
    )

    assert [b.label for b in blocks] == [
        "brief paragraph 1",
        "earlier change request paragraph 1",
        "change request paragraph 1",
    ]
