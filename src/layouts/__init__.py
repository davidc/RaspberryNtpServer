"""Layout drivers for chronotron display formatting."""

import logging
from typing import Optional

from .layout import Layout

__all__ = [
    "Layout",
    "create_layout",
]

log: logging.Logger = logging.getLogger("layouts")


def create_layout(
    layout_config: dict,
) -> Layout | None:
    """Factory function to create the appropriate layout based on configuration.

    Args:
        layout_config: Layout configuration dictionary with:
            {
                "type": "DefaultFourLineLayout" | "CustomLayout",
                // type-specific configuration
            }

    Returns:
        An initialised Layout instance, or None if creation failed
    """
    layout_type = layout_config.get("type", "").lower()

    try:
        if layout_type == "defaultfourlinelayout":
            from .default_four_line import DefaultFourLineLayout

            return DefaultFourLineLayout()

        elif layout_type == "customlayout":
            from .custom_layout import CustomLayout

            lines_config = layout_config.get("lines", [])
            return CustomLayout(lines_config)

        else:
            log.error(f"Unknown layout type: {layout_type}")
            return None

    except Exception as e:
        log.error(f"Failed to create layout of type {layout_type}: {e}")
        return None