from collections.abc import Callable
from pathlib import Path

import pytest

from scopesteps.evals.manifest import ManifestError, freeze, heldout_present, verify
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
