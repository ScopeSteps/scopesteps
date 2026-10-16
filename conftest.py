"""`--shard i/n` runs every n-th collected test, so CI can split the suite across runners.

Round-robin over the collected order keeps the shards even: neighbouring tests cost about the
same, while whole files differ by an order of magnitude (API tests against module tests).
"""

import re

import pytest

_SHARD = re.compile(r"^(\d+)/(\d+)$")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--shard",
        default=None,
        metavar="I/N",
        help="Run only shard I of N (1-based), taking every N-th collected test.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    value: str | None = config.getoption("--shard")
    if value is None:
        return
    match = _SHARD.match(value)
    if match is None or not 1 <= int(match.group(1)) <= int(match.group(2)):
        raise pytest.UsageError(f"--shard takes I/N with 1 <= I <= N, not {value!r}")
    index, count = int(match.group(1)) - 1, int(match.group(2))
    kept = items[index::count]
    deselected = [item for position, item in enumerate(items) if position % count != index]
    config.hook.pytest_deselected(items=deselected)
    items[:] = kept
