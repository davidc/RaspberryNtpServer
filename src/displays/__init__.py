"""Display drivers for chronotron NTP/GPS status display"""
import logging

from .display import Display
from .hd44780 import HD44780Display
from .file_output import FileOutputDisplay
from .rich_terminal import RichTerminalDisplay

__all__ = ["Display", "HD44780Display", "FileOutputDisplay", "RichTerminalDisplay", "create_display"]

log: logging.Logger = logging.getLogger("displays")

def create_display(display_config: dict) -> Display | None:
    """Factory function to create the appropriate display based on configuration.
    
    Args:
        display_config: Display configuration dictionary with at minimum:
            {
                "type": "hd44780" | "file_output",
                // type-specific configuration
            }
    
    Returns:
        Initialized Display instance, or None if creation failed
    """
    display_type = display_config.get("type", "").lower()

    try:

        if display_type == "hd44780":
            return HD44780Display(
                sm_bus=display_config.get("sm_bus", 1),
                i2c_addr=display_config.get("i2c_address", 0x27),
                cols=display_config.get("cols", 20),
                rows=display_config.get("rows", 4),
                ada=display_config.get("adafruit_hardware", False),
                fast_lcd=display_config.get("fast_update", True),
            )

        elif display_type == "file_output":
            return FileOutputDisplay(
                file_path=display_config.get("file", "display_output.log"),
                cols=display_config.get("cols", 20),
                rows=display_config.get("rows", 4),
            )
        
        elif display_type == "rich_terminal":
            return RichTerminalDisplay(
                cols=display_config.get("cols", 20),
                rows=display_config.get("rows", 4),
                backlight_on_style=display_config.get(
                    "backlight_on_style", "bright_cyan on blue"
                ),
                backlight_off_style=display_config.get(
                    "backlight_off_style", "cyan on black"
                ),
            )

        else:
            log.error(f"Unknown display type: {display_type}")
            return None

    except Exception as e:
        log.error(f"Failed to create display of type {display_type}: {e}")
        log.exception(e)
        return None
