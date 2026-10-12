"""Trace attributes for model calls, set by callers and read by the tracing provider.

Attribute names follow the OpenTelemetry GenAI semantic conventions (`gen_ai.*`) so events can be
exported to an OpenTelemetry backend later without renaming. Product-specific attributes use the
`scopesteps.*` prefix. Traces never carry prompts, source text, answers or model output.
"""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar

TraceValue = str | int | float | bool | None

_attributes: ContextVar[Mapping[str, TraceValue] | None] = ContextVar(
    "trace_attributes", default=None
)


@contextmanager
def trace_scope(**attributes: TraceValue) -> Generator[None]:
    """Add `scopesteps.<name>` attributes to every model call made inside the block."""
    token = _attributes.set(
        {
            **(_attributes.get() or {}),
            **{f"scopesteps.{key}": value for key, value in attributes.items()},
        }
    )
    try:
        yield
    finally:
        _attributes.reset(token)


def current_attributes() -> dict[str, TraceValue]:
    return dict(_attributes.get() or {})
