"""Display drivers for chronotron NTP/GPS status display"""

import logging
from typing import Optional

from scrolling_buffer_handler import ScrollingBufferHandler

from .display import Display

__all__ = [
    "Display",
    "create_display",
]

log: logging.Logger = logging.getLogger("displays")


def create_display(
    display_config: dict, log_buffer: Optional[ScrollingBufferHandler] = None
) -> Display | None:
    """Factory function to create the appropriate display based on configuration.

    Args:
        display_config: Display configuration dictionary with at minimum:
            {
                "type": "hd44780" | "file_output",
                // type-specific configuration
            }

    Returns:
        An initialised Display instance, or None if creation failed
    """
    display_type = display_config.get("type", "").lower()

    try:

        if display_type == "hd44780":
            from .hd44780 import HD44780Display

            return HD44780Display(
                sm_bus=display_config.get("sm_bus", None),
                i2c_addr=display_config.get("i2c_address", None),
                cols=display_config.get("cols", None),
                rows=display_config.get("rows", None),
                ada=display_config.get("adafruit_hardware", None),
                fast_lcd=display_config.get("fast_update", None),
            )

        elif display_type == "file_output":
            from .file_output import FileOutputDisplay

            return FileOutputDisplay(
                file_path=display_config.get("file", None),
                cols=display_config.get("cols", None),
                rows=display_config.get("rows", None),
            )

        elif display_type == "rich_terminal":
            from .rich_terminal import RichTerminalDisplay

            return RichTerminalDisplay(
                cols=display_config.get("cols", None),
                rows=display_config.get("rows", None),
                backlight_on_style=display_config.get("backlight_on_style", None),
                backlight_off_style=display_config.get("backlight_off_style", None),
                log_buffer=log_buffer,
            )

        else:
            log.error(f"Unknown display type: {display_type}")
            return None

    except Exception as e:
        log.error(f"Failed to create display of type {display_type}: {e}")
        return None
