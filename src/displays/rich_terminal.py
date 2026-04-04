"""Rich terminal-based LCD-style display"""

import logging
import sys
import time
import signal
import atexit
from typing import Optional, List, Tuple
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.align import Align

from .display import Display

STYLE_TABLE_HEADER = "bold magenta"
STYLE_PANEL = "bright_blue"


class RichTerminalDisplay(Display):
    """A terminal LCD-style display implemented with rich."""

    _instance_count = 0  # Class variable to track instances

    def __init__(
        self,
        cols: int | None = None,
        rows: int | None = None,
        backlight_on_style: str | None = None,
        backlight_off_style: str | None = None,
        log_buffer=None,
    ):
        """Initialise the Rich terminal display."""
        # Prevent multiple instances
        RichTerminalDisplay._instance_count += 1
        if RichTerminalDisplay._instance_count > 1:
            raise RuntimeError("Only one RichTerminalDisplay instance is allowed")

        # Defaults:
        cols = cols or 20
        rows = rows or 4
        backlight_on_style = backlight_on_style or "bright_cyan on blue"
        backlight_off_style = backlight_off_style or "cyan on black"

        self.log: logging.Logger = logging.getLogger("RichTerminalDisplay")
        self.cols: int = cols
        self.rows: int = rows
        self._backlight_on: bool = True
        self.backlight_on_style: str = backlight_on_style
        self.backlight_off_style: str = backlight_off_style
        self.buffer: list[str] = [" " * cols for _ in range(rows)]

        self.console = Console()
        # Track if LCD needs redraw
        self._lcd_dirty = True
        self._logs_dirty = True

        # Set up Rich layout
        self.layout = Layout()
        self.layout.split_column(
            Layout(name="lcd_container", size=self.rows + 2),  # Fixed height for LCD
            Layout(name="logs"),  # Logs take remaining space
        )

        self._lcd_panel: Panel = self._create_lcd_panel()

        # Set up LCD container with horizontal centering
        self.layout["lcd_container"].split_row(
            Layout(name="lcd_left", ratio=1),  # Flexible space
            Layout(self._lcd_panel, name="lcd", size=self.cols + 4),  # LCD panel width
            Layout(name="lcd_right", ratio=1),  # Flexible space
        )

        self.layout["lcd_left"].update("")  # Empty left space
        self.layout["lcd_right"].update("")  # Empty right space

        self.live: Optional[Live] = None

        try:
            # Set up signal handler for terminal resize, so we react immediately rather than wait for next update
            signal.signal(
                signal.SIGWINCH,  # pyright: ignore[reportAttributeAccessIssue] - signal doesn't exist on Windows
                self._handle_resize,
            )
        except (OSError, ValueError, AttributeError):
            # Signal handling not available on this platform
            pass

        try:
            # Register cleanup
            atexit.register(self._cleanup)

            self.log_buffer = log_buffer
            if self.log_buffer:
                self.log_buffer.wanted()
                self.log_buffer.add_listener(self._on_log_update)

            # Remove existing StreamHandlers to prevent printing over our terminal
            root_logger = logging.getLogger()
            for handler in root_logger.handlers.copy():
                if isinstance(handler, logging.StreamHandler):
                    root_logger.removeHandler(handler)

            # Update initial display
            self._update_display()

            self.log.info("RichTerminalDisplay initialised")
        except Exception as e:
            self.log.error(f"Failed to initialise RichTerminalDisplay: {e}")
            raise

    def _handle_resize(self, signum: int, frame) -> None:
        """Handle terminal resize by redrawing the display."""
        logging.debug(
            "Display resized to {}x{}".format(
                self.console.size.width, self.console.size.height
            )
        )
        self._update_display(force=True)

    def _cleanup(self) -> None:
        """Clean up resources and restore terminal state."""
        if hasattr(self, "console"):
            self.console.set_alt_screen(False)
            self.console.show_cursor(True)

    def _on_log_update(self) -> None:
        """Called when the log buffer is updated."""
        self._logs_dirty = True
        self._update_display()

    def _calculate_max_log_messages(self) -> int:
        """Calculate maximum log messages that can fit based in terminal height."""
        terminal_height = self.console.size.height

        # LCD takes self.rows + 2 (borders), logs take the rest
        # Log panel has borders (2) + table header (1) = 3 lines overhead
        available_log_height = terminal_height - (self.rows + 2) - 3

        return max(1, available_log_height)

    def _get_log_level_color(self, level: str) -> str:
        """Get color for log level."""
        colors = {
            "DEBUG": "dim cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold red",
        }
        return colors.get(level, "white")

    def _create_lcd_panel(self) -> Panel:
        """Create the LCD panel."""

        # Create panel with border matching log panel
        panel = Panel(
            self._create_lcd_text(),
            title="[bold]LCD Display[/bold]",
            border_style=STYLE_PANEL,  # Same as log panel
            padding=(0, 1),
            width=self.cols + 4,  # Content width + padding + borders
            height=self.rows + 2,  # Content height + borders
            expand=False,  # Don't expand to fill available space
        )

        return panel

    def _create_lcd_text(self) -> Text:
        style = (
            self.backlight_on_style if self._backlight_on else self.backlight_off_style
        )
        lcd_lines = []
        for row_text in self.buffer:
            # Pad/truncate each row to exactly cols characters
            padded_row = row_text[: self.cols].ljust(self.cols, " ")
            lcd_lines.append(padded_row)

        lcd_content = "\n".join(lcd_lines)

        # Create styled text
        return Text(lcd_content, style=style)

    def _create_log_panel(self) -> Panel:
        """Create the log messages panel."""

        table = self._create_log_table()

        panel = Panel(
            table, title="[bold]Log Messages (latest first)[/bold]", border_style=STYLE_PANEL
        )
        return panel

    def _create_log_table(self):
        table = Table(
            show_header=True, header_style=STYLE_TABLE_HEADER, box=None, show_edge=False
        )
        table.add_column("Time", style="dim", width=8, no_wrap=True)
        table.add_column("Level", width=8, no_wrap=True)
        table.add_column("Message", style="white")

        if self.log_buffer:
            # If individual log entries wrap over multiple lines, we need fewer than max_messages; rich does not let us scroll the table
            # to the bottom which is why we're displaying messages backwards
            max_messages = self._calculate_max_log_messages()
            recent_records = self.log_buffer.get_recent_records(max_messages)

            for record in reversed(recent_records):
                level = record.levelname
                message = record.getMessage()
                timestamp = time.strftime("%H:%M:%S", time.localtime(record.created))

                table.add_row(
                    timestamp,
                    Text(level, style=self._get_log_level_color(level)),
                    message,
                )

        return table

    def _update_display(self, force: bool = False) -> None:
        """Update the changed parts of the display layout."""

        # Update only the panels that have changed
        updated = False
        if self._lcd_dirty:
            self.layout["lcd"].update(self._create_lcd_panel())
            self._lcd_dirty = False
            updated = True

        if self._logs_dirty:
            self.layout["logs"].update(self._create_log_panel())
            self._logs_dirty = False
            updated = True

        # Only refresh the display if something changed
        if updated or force:
            # Start Live display if not already started
            if self.live is None:
                self.live = Live(
                    self.layout, console=self.console, screen=True, auto_refresh=False
                )
                self.live.start()
            else:
                # Refresh the existing live display
                self.live.refresh()

    def print_row(self, row: int, text: str) -> None:
        if row < 0 or row >= self.rows:
            return

        text_line = text[: self.cols].ljust(self.cols, " ")

        # Only update if the row has actually changed
        if self.buffer[row] != text_line:
            self.buffer[row] = text_line
            self._lcd_dirty = True
            self._update_display()

    def set_backlight(self, state: bool) -> None:
        if self._backlight_on != state:
            self._backlight_on = state
            self._update_display(force=True)  # Force full update to apply new style

    def __del__(self):
        # Stop live display if running
        if hasattr(self, "live") and self.live is not None:
            try:
                self.live.stop()
            except Exception:
                pass  # Ignore errors during cleanup

        # Decrement instance count
        RichTerminalDisplay._instance_count = max(
            0, RichTerminalDisplay._instance_count - 1
        )
        self._cleanup()
        atexit.unregister(self._cleanup)
