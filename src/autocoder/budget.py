"""Reserve allowances before operations; reconcile measured inference usage afterward."""

import time

from autocoder.protocol import Limits, Usage


class BudgetExhausted(RuntimeError):
    pass


class Budget:
    def __init__(self, limits: Limits):
        self.limits = limits
        self.started = time.monotonic()
        self._used = dict(request_tokens=0, output_tokens=0, tool_calls=0, repairs=0)

    @property
    def remaining_seconds(self) -> float:
        remaining = self.limits.wall_seconds - (time.monotonic() - self.started)
        if remaining <= 0:
            raise BudgetExhausted("wall_seconds")
        return remaining

    def consume(self, **amounts: int) -> None:
        _ = self.remaining_seconds
        for name, amount in amounts.items():
            if name not in self._used or amount < 0:
                raise ValueError(f"Invalid usage: {name}={amount}")
            if self._used[name] + amount > getattr(self.limits, name):
                raise BudgetExhausted(name)
        for name, amount in amounts.items():
            self._used[name] += amount

    def snapshot(self) -> Usage:
        return Usage(elapsed_seconds=time.monotonic() - self.started, **self._used)
