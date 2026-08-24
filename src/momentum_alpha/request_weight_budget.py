from __future__ import annotations

from dataclasses import dataclass, field


class RequestWeightLimitExceeded(RuntimeError):
    pass


@dataclass
class RequestWeightBudget:
    limit: int
    used: int = 0
    entries: list[tuple[str, int]] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def can_spend(self, weight: int) -> bool:
        return weight >= 0 and self.used + weight <= self.limit

    def spend(self, weight: int, *, operation: str) -> None:
        if weight < 0:
            raise ValueError("request weight must be non-negative")
        if not self.can_spend(weight):
            raise RequestWeightLimitExceeded(
                f"request weight budget exceeded: operation={operation} "
                f"used={self.used} requested={weight} limit={self.limit}"
            )
        self.used += weight
        self.entries.append((operation, weight))
