"""Readable names for the labels a model sees (B3, A1, S2, S2.C1) when it writes them in prose.

Prompts give every block and baseline item a short label to cite, and models sometimes repeat
those labels in text meant for people ("left open (B12)"). Those labels mean nothing outside the
request, so prose is rewritten with the names people see before it is stored. Ids, citations and
quotes are never touched: code still resolves and checks them by label.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from scopesteps.agent.application.schemas import SourceBlockInput

_LABEL = re.compile(r"\b[A-Z]\d+(?:\.C\d+)?\b")

# Fields that hold labels, ids or verbatim text, never prose for people.
_NOT_PROSE = frozenset(
    {
        "affects",
        "block_id",
        "covered_by",
        "covers",
        "id",
        "item",
        "kind",
        "needs_decision",
        "op",
        "origin",
        "outcome",
        "parent",
        "parent_ref",
        "quote",
        "ref",
        "remove_criteria",
        "reverses",
        "rights",
        "speaker",
    }
)


def block_names(blocks: Sequence[SourceBlockInput]) -> dict[str, str]:
    """Each block label by the name of its passage ("brief paragraph 3", "reviewer answer")."""
    return {block.id: block.label for block in blocks}


def name_labels(text: str, names: Mapping[str, str]) -> str:
    """`text` with every label in `names` replaced by its name; other words stay as they are."""
    return _LABEL.sub(lambda match: names.get(match.group(0), match.group(0)), text)


def name_labels_in(data: Any, names: Mapping[str, str]) -> Any:
    """A JSON-like model output with labels named in its prose fields only."""
    if isinstance(data, str):
        return name_labels(data, names)
    if isinstance(data, list):
        return [name_labels_in(value, names) for value in cast(list[Any], data)]
    if isinstance(data, dict):
        mapping = cast(dict[str, Any], data)
        return {
            key: value if key in _NOT_PROSE else name_labels_in(value, names)
            for key, value in mapping.items()
        }
    return data
