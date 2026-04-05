"""Base Layout class for display formatting."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Layout(ABC):
    """Abstract base class for display layouts."""

    @abstractmethod
    def update(self, stats: dict[str, Any]) -> None:
        """Update the layout with the latest stats."""
        pass

    @abstractmethod
    def get_line(self, line_number: int, cols: int) -> str:
        """Return the formatted line for a given line number and width."""
        pass

    def _format_utc_offset(self, seconds: int) -> str:
        sign = "+" if seconds >= 0 else "-"
        seconds = abs(seconds)

        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60

        return f"{sign}{hours:02d}{minutes:02d}"

    def _format_justified_line(self, left: str, right: str, cols: int) -> str:
        spacing = max(0, cols - len(left) - len(right))
        return (left + (" " * spacing) + right)[:cols]

    def _pad_or_truncate(self, text: str, cols: int) -> str:
        if cols < 0:
            cols = 0
        return str(text)[:cols].ljust(cols, " ")
