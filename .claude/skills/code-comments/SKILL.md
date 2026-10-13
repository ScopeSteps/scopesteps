---
name: code-comments
description: When and how to write code comments and docstrings in ScopeSteps, in Python and TypeScript. Use when writing new code, reviewing code, or asked to add, improve or clean up comments, docstrings or JSDoc.
---

# Comments and docstrings

The rule from [CONTRIBUTING.md](../../../CONTRIBUTING.md): code explains itself through names
and types. Write a comment only for what the code cannot say.

## Write a comment for

- **Why**, when the reason is not obvious: a decision, a trade-off, a rejected alternative.
- **A constraint the reader cannot see:** an external limit, an ordering requirement, a security
  or billing consequence.
- **The contract of a public interface:** what a port, `client.py` type or exported function
  promises, especially what it will never do.
- **A surprising value:** why a constant is that number.

Examples from this repository:

```python
# Deliberately pessimistic (about 3 characters per token) so the pre-call check errs towards
# stopping. Real usage reported by the provider replaces the estimate after each call.
CHARS_PER_TOKEN_ESTIMATE = 3
```

```python
def after_failed_call(self) -> RunCounters:
    """A failed or timed-out call still counts: the provider may have done (and billed) work."""
```

```ts
/**
 * Typed API client. Types are generated from contracts/openapi.json.
 * An unset or empty VITE_API_BASE_URL means same origin (the Vite dev proxy locally).
 */
```

## Do not write

- A restatement of the code: `# increment the counter`, `"""Returns the user."""` on `get_user`.
- Parameter and return lists that repeat the type hints.
- History: who changed it, when, what it used to do, ticket narratives. That is git's job.
- Commented-out code. Delete it.
- Section banners and decorative dividers.
- A comment that excuses unclear code. Rename or restructure instead.
- `TODO` without an owner or ticket. Either do it, or reference the ticket: `# TODO(SSPOC-8): …`.

## Decisions live in ADRs

An ADR is the single source of truth for its decision. Where someone might otherwise "fix" a
deliberate choice, point to it: `# No fallback model (ADR 0004).` Do not copy its reasoning,
numbers or measurements into the comment; they go stale when the ADR gains a note. READMEs link
to ADRs rather than restating them.

## Before adding one, try

1. A better name for the variable, function or type.
2. Extracting a well-named function or constant.
3. A more precise type, so the constraint is checked instead of described.

If the comment is still needed after that, write it.

## Form

- Full sentences, present tense, plain words. State the fact; skip "Note that" and "This
  function".
- Put the comment on the line above what it explains, at the same indent.
- Python: a one-line docstring where possible; a module docstring when the module's purpose or
  rule is not clear from its name. `#` comments for reasons inside a body.
- TypeScript: `/** … */` on exported things that need a contract, `//` inside bodies.
- Keep to the line width the formatter uses; do not fight ruff or Prettier.

## When changing code

Update or delete every comment the change makes untrue, in the same commit. A wrong comment is
worse than none. Leave accurate existing comments alone; do not rewrite them for style.
