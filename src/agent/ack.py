from __future__ import annotations

import random
from collections import deque
from collections.abc import Sequence

DEFAULT_PHRASES: tuple[str, ...] = (
    "Sure, I'll check that.",
    "Got it, let me look into it.",
    "Understood, I'll work through that.",
    "Okay, looking at that now.",
)


class AckPicker:
    """Returns a canned acknowledgement phrase, avoiding immediate repeats.

    Cheap and synchronous so it can fire before any I/O on a turn.
    """

    def __init__(
        self,
        phrases: Sequence[str] = DEFAULT_PHRASES,
        recent_window: int = 2,
        rng: random.Random | None = None,
    ) -> None:
        if not phrases:
            raise ValueError("AckPicker needs at least one phrase")
        self._phrases = tuple(phrases)
        self._recent: deque[str] = deque(maxlen=max(0, recent_window))
        self._rng = rng or random.Random()

    def pick(self) -> str:
        candidates = [p for p in self._phrases if p not in self._recent] or list(self._phrases)
        choice = self._rng.choice(candidates)
        self._recent.append(choice)
        return choice
