"""Lock held-out packs with a checksum manifest so later edits are detectable.

Held-out packs are the blind test: written before prompt work starts, never used to tune prompts,
and read only for the final comparison. The manifest proves they were not changed afterwards.
"""

import hashlib
from pathlib import Path

from scopesteps.evals.packs import DATASETS_DIR, load_packs

MANIFEST_NAME = "heldout.sha256"
MIN_HELDOUT_PACKS = 2


class ManifestError(Exception):
    pass


def manifest_path(root: Path = DATASETS_DIR) -> Path:
    return root / MANIFEST_NAME


def compute_checksums(root: Path = DATASETS_DIR) -> dict[str, str]:
    heldout = root / "heldout"
    if not heldout.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(heldout.rglob("*"))
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
