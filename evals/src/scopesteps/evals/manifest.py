"""Lock held-out packs with a checksum manifest so later edits are detectable.

Held-out packs are the blind test: written before prompt work starts, never used to tune prompts,
and read only for the final comparison. The manifest proves they were not changed afterwards.
"""

import hashlib
from pathlib import Path

from scopesteps.evals.packs import DATASETS_DIR, load_pack, load_packs, pack_dirs

MANIFEST_NAME = "heldout.sha256"
MIN_HELDOUT_PACKS = 2


class ManifestError(Exception):
    pass


def heldout_present(root: Path = DATASETS_DIR) -> bool:
    """Held-out packs live in a private repository, cloned into ``heldout/`` (ADR 0017)."""
    return (root / "heldout").is_dir()


def manifest_path(root: Path = DATASETS_DIR) -> Path:
    return root / MANIFEST_NAME


def compute_checksums(root: Path = DATASETS_DIR) -> dict[str, str]:
    """Hash every file inside a held-out pack; files beside the packs (the clone's README,
    .git) are not part of the lock."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for pack_dir in pack_dirs("heldout", root)
        for path in sorted(pack_dir.rglob("*"))
        if path.is_file() and path.name != ".DS_Store"
    }


def read_manifest(root: Path = DATASETS_DIR) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in manifest_path(root).read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, relative = line.split(maxsplit=1)
            entries[relative] = digest
    return entries


def freeze(root: Path = DATASETS_DIR) -> Path:
    """Write the manifest once. Re-freezing would defeat the lock, so it is refused."""
    path = manifest_path(root)
    if path.exists():
        raise ManifestError(f"{path.name} already exists; held-out packs are frozen")
    packs = load_packs("heldout", root)
    if len(packs) < MIN_HELDOUT_PACKS:
        raise ManifestError(f"Need at least {MIN_HELDOUT_PACKS} valid held-out packs to freeze")
    lines = [f"{digest}  {relative}" for relative, digest in compute_checksums(root).items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def replace_frozen_set(root: Path = DATASETS_DIR) -> tuple[list[str], list[str]]:
    """Write a new manifest for the packs now in ``heldout/``, replacing the frozen set.

    Only for retiring a whole set before anything is measured on the new one: retired packs move
    to a hidden folder in the private repository (``.retired/``), which no tool reads. Every
    current pack must be valid. Returns the packs that left the lock and those that joined it.
    """
    path = manifest_path(root)
    before = {name.split("/")[1] for name in read_manifest(root)} if path.exists() else set[str]()
    packs = load_packs("heldout", root)
    if len(packs) < MIN_HELDOUT_PACKS:
        raise ManifestError(f"Need at least {MIN_HELDOUT_PACKS} valid held-out packs to freeze")
    after = {pack.path.name for pack in packs}
    lines = [f"{digest}  {relative}" for relative, digest in compute_checksums(root).items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sorted(before - after), sorted(after - before)


def freeze_new_packs(root: Path = DATASETS_DIR) -> list[str]:
    """Add packs that are not in the manifest yet, never changing an entry already there.

    Refused unless every file the manifest already covers is unchanged, so a frozen pack cannot be
    edited and re-frozen this way. Each new pack must be valid. Returns the new packs' names.
    """
    path = manifest_path(root)
    if not path.exists():
        raise ManifestError(f"{path.name} does not exist yet; freeze the first set instead")
    expected = read_manifest(root)
    actual = compute_checksums(root)
    changed = sorted(
        name for name in expected if name not in actual or actual[name] != expected[name]
    )
    if changed:
        raise ManifestError(f"frozen files are missing or changed: {', '.join(changed)}")
    frozen = {name.split("/")[1] for name in expected}
    new = [d for d in pack_dirs("heldout", root) if d.name not in frozen]
    if not new:
        raise ManifestError("no new held-out packs to freeze")
    for pack_dir in new:
        load_pack(pack_dir, "heldout")
    names = {d.name for d in new}
    added = [
        f"{digest}  {relative}"
        for relative, digest in actual.items()
        if relative.split("/")[1] in names
    ]
    with path.open("a", encoding="utf-8") as manifest:
        manifest.write("\n".join(added) + "\n")
    return sorted(names)


def verify(root: Path = DATASETS_DIR) -> list[str]:
    """Return every difference between the held-out files and the manifest."""
    actual = compute_checksums(root)
    if not manifest_path(root).exists():
        return [f"held-out files are not frozen: {name}" for name in actual]
    expected = read_manifest(root)
    problems = [f"missing: {name}" for name in sorted(expected.keys() - actual.keys())]
    problems += [f"not in manifest: {name}" for name in sorted(actual.keys() - expected.keys())]
    problems += [
        f"changed: {name}"
        for name in sorted(expected.keys() & actual.keys())
        if expected[name] != actual[name]
    ]
    if len({name.split("/")[1] for name in expected}) < MIN_HELDOUT_PACKS:
        problems.append(f"manifest covers fewer than {MIN_HELDOUT_PACKS} packs")
    return problems
