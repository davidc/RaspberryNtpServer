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

    def _format_signed_offset(self, s: Optional[float]) -> Optional[str]:
        if s is None:
            return None

        x = abs(s)

        if x < 9999.5e-9:
            return f"{s * 1e9:+.0f}ns"
        elif x < 9999.5e-6:
            return f"{s * 1e6:+.0f}us"
        elif x < 9999.5e-3:
            return f"{s * 1e3:+.0f}ms"
        elif x < 999.5:
            return f"{s:+.1f}s"
        elif x < 99999.5:
            return f"{s:+.0f}s"
        elif x < 99999.5 * 60:
            return f"{s / 60:+.0f}m"
        elif x < 99999.5 * 3600:
            return f"{s / 3600:+.0f}h"
        elif x < 99999.5 * 3600 * 24:
            return f"{s / (3600 * 24):+.0f}d"
        else:
            return f"{s / (3600 * 24 * 365):+.0f}y"

    def _format_justified_line(self, left: str, right: str, cols: int) -> str:
        spacing = max(0, cols - len(left) - len(right))
        return (left + (" " * spacing) + right)[:cols]

    def _pad_or_truncate(self, text: str, cols: int) -> str:
        if cols < 0:
            cols = 0
        return str(text)[:cols].ljust(cols, " ")
