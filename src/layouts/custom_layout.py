"""Custom configurable layout for Chronotron."""

from __future__ import annotations

import logging
import time
from typing import Any

from .layout import Layout


class CustomLayout(Layout):
    """Customizable layout with user-defined line formatting."""

    def __init__(self, lines_config: list[Any]) -> None:
        """
        Initialize custom layout.

        Args:
            lines_config: List of line configurations. Each can be:
                - A dict with 'left' and 'right' keys (strings with formatting)
                - A string with formatting (left-justified)
        """
        self.stats: dict[str, Any] = {}
        self.lines_config = lines_config
        self.log = logging.getLogger("chronotron.custom_layout")

    def update(self, stats: dict[str, Any]) -> None:
        self.stats = dict(stats)

    def get_line(self, line_number: int, cols: int) -> str:
        if line_number < 0 or line_number >= len(self.lines_config):
            return " " * cols

        config = self.lines_config[line_number]

        if isinstance(config, dict):
            # Left/right format
            left = config.get("left", "")
            right = config.get("right", "")
            left_str = self._format_string(left)
            right_str = self._format_string(right)
            return self._format_justified_line(left_str, right_str, cols)
        else:
            # Simple string format
            text = self._format_string(str(config))
            return self._pad_or_truncate(text, cols)
    

    def _format_string(self, template: str) -> str:
        """Format a template string with access to stats and common functions."""
        # Build the context with stats and useful functions
        context = dict(self.stats)
        context["time"] = time
        context["layout"] = self

        try:
            # Use eval with f-string to support complex expressions
            # Restrict builtins for safety
            safe_builtins = {
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
            }
            restricted_context = {**context, "__builtins__": safe_builtins}
            result = eval(f"f'{template}'", restricted_context)
            return str(result)
        except Exception as e:
            self.log.info(f"Error formatting line with template '{template}': {e}")
            return f"[ERROR]"
