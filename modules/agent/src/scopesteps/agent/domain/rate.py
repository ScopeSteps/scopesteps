"""Client-side pacing for per-minute token limits, so callers wait before a call instead of
spending it on a 429."""

from collections import deque
from dataclasses import dataclass, field

WINDOW_SECONDS = 60.0


@dataclass
class TokenWindow:
    """Tokens used in the last minute. Providers count actual usage, so callers record what each
    call reported."""

    tokens_per_minute: int
    _used: deque[tuple[float, int]] = field(default_factory=deque[tuple[float, int]])

    def record(self, now: float, tokens: int) -> None:
        self._used.append((now, tokens))

    def wait_seconds(self, now: float, upcoming: int) -> float:
        """How long to wait before a call expected to use `upcoming` tokens. A call larger than
        the whole allowance waits for an empty window."""
        while self._used and self._used[0][0] <= now - WINDOW_SECONDS:
            self._used.popleft()
        budget = self.tokens_per_minute - min(upcoming, self.tokens_per_minute)
        used = sum(tokens for _, tokens in self._used)
        wait = 0.0
        for started, tokens in self._used:
            if used <= budget:
                break
            used -= tokens
            wait = started + WINDOW_SECONDS - now
        return max(wait, 0.0)
