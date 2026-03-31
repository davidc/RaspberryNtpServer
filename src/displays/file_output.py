"""File output display for debugging and testing"""

import logging
from datetime import datetime
from .display import Display


class FileOutputDisplay(Display):
    """A dummy display that outputs to a file instead of physical hardware.
    
    Useful for debugging, testing, or running on non-Raspberry Pi systems.
    Each call to print_row appends a timestamped line to the configured file.
    """

    def __init__(self, file_path: str = "display_output.log", cols: int = 20, rows: int = 4):
        """
        Args:
            file_path: Path to the output file (created if it doesn't exist)
            cols: Display width in characters (for formatting)
            rows: Display height in characters (for reference)
        """
        self.log: logging.Logger = logging.getLogger("FileOutputDisplay")
        self.file_path: str = file_path
        self.cols: int = cols
        self.rows: int = rows
        self._backlight_on: bool = False

        try:
            # Try to open/create the file to verify write permissions
            with open(self.file_path, "a") as f:
                f.write(f"=== Display session started at {datetime.now().isoformat()} ===\n")
            self.log.info(f"FileOutputDisplay initialized, output to {self.file_path}")
        except Exception as e:
            self.log.error(f"Failed to initialize FileOutputDisplay with file {self.file_path}: {e}")
            raise

    def print_row(self, row: int, text: str) -> None:
        """Write a row to the output file.
        
        Args:
            row: Row number (0-based, logged for context)
            text: Text to write (will be truncated/padded to column width)
        """

        # Pad or truncate text to column width
        text = text[: self.cols].ljust(self.cols, " ")

        try:
            with open(self.file_path, "a") as f:
                backlight_status = "ON " if self._backlight_on else "OFF"
                f.write(f"[{datetime.now().isoformat()}] Row {row} | BL:{backlight_status} | {text}\n")
        except Exception as e:
            self.log.error(f"Failed to write to {self.file_path}: {e}")

    def set_backlight(self, state: bool) -> None:
        """Track backlight state (logged with each row output).
        
        Args:
            state: True to turn on, False to turn off
        """
        self._backlight_on = state
        try:
            with open(self.file_path, "a") as f:
                status = "ON" if state else "OFF"
                f.write(f"[{datetime.now().isoformat()}] Backlight {status}\n")
        except Exception as e:
            self.log.error(f"Failed to write to {self.file_path}: {e}")


if __name__ == "__main__":
    """Test the FileOutputDisplay"""
    logging.basicConfig(level=logging.INFO)
    
    display = FileOutputDisplay("test_display.log")
    if display.active:
        print(f"Writing test output to test_display.log...")
        display.set_backlight(True)
        display.print_row(0, "2024-03-31  12:34:56")
        display.print_row(1, "S[1]   +0.000123456sec")
        display.print_row(2, "L[*] localhost")
        display.print_row(3, "F[3] 12/15   +234ns")
        display.set_backlight(False)
        print("Test complete!")
    else:
        print("Failed to initialize display")
