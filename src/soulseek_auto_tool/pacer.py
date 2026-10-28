from __future__ import annotations

import random
import time
from typing import Callable


class Pacer:
    """Spaces actions a random 3-4.5 s apart so searches don't look automated."""

    def __init__(
        self,
        min_delay: float = 3.0,
        max_delay: float = 4.5,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        if min_delay < 0 or max_delay < min_delay:
            raise ValueError("need 0 <= min_delay <= max_delay")
        self.min_delay, self.max_delay = min_delay, max_delay
        self._sleep, self._clock, self._uniform = sleep, clock, uniform
        self._last: float | None = None

    def wait(self) -> float:
        """Block until enough time has passed since the last call. Returns seconds slept."""
        slept = 0.0
        if self._last is not None:
            gap = self._uniform(self.min_delay, self.max_delay)
            remaining = gap - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)
                slept = remaining
        self._last = self._clock()
        return slept
