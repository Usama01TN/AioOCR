"""Human-readable routing explain traces."""
from __future__ import annotations

from typing import Any


class ExplainLog:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, msg: str) -> None:
        self.lines.append(msg)

    def extend(self, msgs: list[str]) -> None:
        self.lines.extend(msgs)

    def as_list(self) -> list[str]:
        return list(self.lines)


def summarize_filters(dropped: list[tuple[str, str]]) -> list[str]:
    return [f"skipped {name} ({reason})" for name, reason in dropped]
