"""Unified token-usage accounting.

Every token-spending call (question embedding + LLM completion) returns a
``TokenUsage`` alongside its payload, so the request handler can sum them and
charge the vendor a single total. ``TokenUsage`` is immutable and addable;
``UsageAccumulator`` is the mutable request-level tally threaded through the
pipeline so partial usage is still recorded if a later stage fails.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenUsage:
    embedding: int = 0
    completion: int = 0

    @property
    def total(self) -> int:
        return self.embedding + self.completion

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            embedding=self.embedding + other.embedding,
            completion=self.completion + other.completion,
        )


class UsageAccumulator:
    """Mutable running total for one request.

    The endpoint owns it and records ``.total`` in a ``finally`` block, so tokens
    already spent are billed even if the request fails after the paid call.
    """

    def __init__(self) -> None:
        self.usage = TokenUsage()

    def add(self, usage: TokenUsage) -> None:
        self.usage = self.usage + usage

    @property
    def total(self) -> int:
        return self.usage.total
