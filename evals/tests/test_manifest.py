from collections.abc import Callable
from pathlib import Path

import pytest

from scopesteps.evals.manifest import (
    ManifestError,
    freeze,
    freeze_new_packs,
    heldout_present,
    replace_frozen_set,
    verify,
)
from scopesteps.evals.packs import pack_dirs

PackFactory = Callable[..., Path]


def test_freeze_needs_two_heldout_packs(tmp_path: Path, make_pack: PackFactory) -> None:
    make_pack("only-one", "heldout")

    with pytest.raises(ManifestError, match="at least 2"):
        freeze(tmp_path)


def test_unfrozen_heldout_files_are_reported(tmp_path: Path, make_pack: PackFactory) -> None:
    make_pack("pack-a", "heldout")

    assert "held-out files are not frozen: heldout/pack-a/brief.md" in verify(tmp_path)


def test_frozen_packs_verify_until_changed(tmp_path: Path, make_pack: PackFactory) -> None:
    pack_a = make_pack("pack-a", "heldout")
    make_pack("pack-b", "heldout")
    freeze(tmp_path)

    assert verify(tmp_path) == []

    (pack_a / "brief.md").write_text("# Brief\n\nEdited after freezing.\n")
    (pack_a / "notes.md").write_text("new file")
    (tmp_path / "heldout" / "pack-b" / "transcript.md").unlink()

    assert verify(tmp_path) == [
        "missing: heldout/pack-b/transcript.md",
        "not in manifest: heldout/pack-a/notes.md",
        "changed: heldout/pack-a/brief.md",
    ]


def test_freezing_twice_is_refused(tmp_path: Path, make_pack: PackFactory) -> None:
    make_pack("pack-a", "heldout")
    make_pack("pack-b", "heldout")
    freeze(tmp_path)

    with pytest.raises(ManifestError, match="already exists"):
        freeze(tmp_path)


def test_dev_packs_are_not_locked(tmp_path: Path, make_pack: PackFactory) -> None:
    make_pack("pack-a", "dev")

    assert verify(tmp_path) == []


@pytest.mark.skipif(not heldout_present(), reason="held-out packs are not cloned")
def test_repository_heldout_packs_match_manifest() -> None:
    assert verify() == []


def test_heldout_present_only_when_cloned(tmp_path: Path, make_pack: PackFactory) -> None:
    assert not heldout_present(tmp_path)

    make_pack("pack-a", "heldout")

    assert heldout_present(tmp_path)


def test_lock_ignores_files_beside_the_packs(tmp_path: Path, make_pack: PackFactory) -> None:
    make_pack("pack-a", "heldout")
    make_pack("pack-b", "heldout")
    freeze(tmp_path)
    (tmp_path / "heldout" / "README.md").write_text("Clone notes.\n")
    (tmp_path / "heldout" / ".git").mkdir()
    (tmp_path / "heldout" / ".git" / "HEAD").write_text("ref: refs/heads/main\n")

    assert verify(tmp_path) == []
    assert [path.name for path in pack_dirs("heldout", tmp_path)] == ["pack-a", "pack-b"]


def test_new_packs_are_added_without_changing_frozen_entries(
    tmp_path: Path, make_pack: PackFactory
) -> None:
    make_pack("pack-a", "heldout")
    make_pack("pack-b", "heldout")
    freeze(tmp_path)
    frozen = (tmp_path / "heldout.sha256").read_text()
    make_pack("pack-c", "heldout")

    added = freeze_new_packs(tmp_path)

    assert added == ["pack-c"]
    after = (tmp_path / "heldout.sha256").read_text()
    assert after.startswith(frozen), "every frozen line is kept as it was"
    assert "heldout/pack-c/brief.md" in after
    assert verify(tmp_path) == []


def test_adding_is_refused_when_a_frozen_pack_changed(
    tmp_path: Path, make_pack: PackFactory
) -> None:
    pack_a = make_pack("pack-a", "heldout")
    make_pack("pack-b", "heldout")
    freeze(tmp_path)
    (pack_a / "brief.md").write_text("# Brief\n\nUsers can book two rooms.\n")
    make_pack("pack-c", "heldout")

    with pytest.raises(ManifestError, match=r"changed: .*|missing or changed: heldout/pack-a"):
        freeze_new_packs(tmp_path)


def test_adding_needs_an_existing_manifest_and_a_new_pack(
    tmp_path: Path, make_pack: PackFactory
) -> None:
    make_pack("pack-a", "heldout")
    make_pack("pack-b", "heldout")

    with pytest.raises(ManifestError, match="does not exist yet"):
        freeze_new_packs(tmp_path)

    freeze(tmp_path)

    with pytest.raises(ManifestError, match="no new held-out packs"):
        freeze_new_packs(tmp_path)


def test_a_retired_set_is_replaced_by_the_packs_now_cloned(
    tmp_path: Path, make_pack: PackFactory
) -> None:
    old_a = make_pack("old-a", "heldout")
    old_b = make_pack("old-b", "heldout")
    freeze(tmp_path)
    retired = tmp_path / "heldout" / ".retired"
    retired.mkdir()
    old_a.rename(retired / "old-a")
    old_b.rename(retired / "old-b")
    make_pack("new-a", "heldout")
    make_pack("new-b", "heldout")

    left, joined = replace_frozen_set(tmp_path)

    assert (left, joined) == (["old-a", "old-b"], ["new-a", "new-b"])
    assert verify(tmp_path) == []
    assert ".retired" not in (tmp_path / "heldout.sha256").read_text()


def test_a_replacement_set_needs_two_valid_packs(tmp_path: Path, make_pack: PackFactory) -> None:
    make_pack("only-one", "heldout")

    with pytest.raises(ManifestError, match="at least 2"):
        replace_frozen_set(tmp_path)
