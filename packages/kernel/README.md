# scopesteps-kernel

The shared kernel: the small set of types every module agrees on.

- `ids` — UUID-based identifiers.
- `errors` — `DomainError`, the base for errors that map to the API error envelope.
- `events` — `DomainEvent`, the base for events modules publish to each other.

Keep this package tiny. Anything domain-specific belongs in a module, not here.
