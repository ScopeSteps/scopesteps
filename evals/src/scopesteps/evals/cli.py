import argparse
import sys

from scopesteps.evals.manifest import ManifestError, freeze, verify
from scopesteps.evals.packs import PackError, load_pack, pack_dirs


def _validate() -> int:
    failures = 0
    for split in ("dev", "heldout"):
        for pack_dir in pack_dirs(split):
            try:
                pack = load_pack(pack_dir, split)
            except PackError as error:
                failures += 1
                print(f"FAIL {split}/{pack_dir.name}")
                for problem in error.problems:
                    print(f"  - {problem}")
            else:
                # Counts only: printing held-out content would leak the blind test.
                print(f"ok   {split}/{pack.id} ({len(pack.annotations.annotations)} annotations)")
    problems = verify()
    for problem in problems:
        print(f"LOCK {problem}")
    return 1 if failures or problems else 0


def _freeze() -> int:
    try:
        path = freeze()
    except (ManifestError, PackError) as error:
        print(f"Not frozen: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {path}. Commit it together with the held-out packs.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="scopesteps-evals")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="Check every pack and the held-out lock")
    commands.add_parser("freeze-heldout", help="Write the held-out checksum manifest (once)")
    args = parser.parse_args()
    sys.exit(_validate() if args.command == "validate" else _freeze())
