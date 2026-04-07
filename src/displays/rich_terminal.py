"""Rich terminal-based LCD-style display"""

import logging
import sys
import time
import signal
import atexit
from typing import Optional
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout as RichLayout
from rich.live import Live
from rich.align import Align

from .display import Display

STYLE_TABLE_HEADER = "bold magenta"
STYLE_PANEL = "bright_blue"

HELP_TEXT = [
    "Keyboard commands:",
    "  q - Quit",
    "  b - Cycle backlight AUTO/OFF/ON",
    "  h - Show/hide this help",
]


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
        super().__init__()

        # Prevent multiple instances
        RichTerminalDisplay._instance_count += 1
        if RichTerminalDisplay._instance_count > 1:
            raise RuntimeError("Only one RichTerminalDisplay instance is allowed")

        # Defaults:
        cols = cols or 20
        rows = rows or 4
        backlight_on_style = backlight_on_style or "bright_cyan on blue"
        backlight_off_style = backlight_off_style or "cyan on black"

        if not sys.stdout.isatty():
            raise RuntimeError("RichTerminalDisplay requires an interactive terminal (stdout is not a tty)")

        self.log: logging.Logger = logging.getLogger("RichTerminalDisplay")
        self.cols: int = cols
        self.rows: int = rows
        self._backlight_on: bool = True
        self.backlight_on_style: str = backlight_on_style
        self.backlight_off_style: str = backlight_off_style
        self.buffer: list[str] = [" " * cols for _ in range(rows)]
        self.help_overlay: bool = False

        self.console = Console()
        self._lcd_dirty = True
        self._logs_dirty = True

        # Set up Rich layout
        self.rich_layout = RichLayout()
        self.rich_layout.split_column(
            RichLayout(name="lcd_container", size=self.rows + 2),  # Fixed height for LCD
            RichLayout(name="logs"),  # Logs take remaining space
        )

        self._lcd_panel: Panel = self._create_lcd_panel()

        # Set up LCD container with horizontal centering
        self.rich_layout["lcd_container"].split_row(
            RichLayout(name="lcd_left", ratio=1),  # Flexible space
            RichLayout(self._lcd_panel, name="lcd", size=self.cols + 4),  # LCD panel width
            RichLayout(name="lcd_right", ratio=1),  # Flexible space
        )

        self.rich_layout["lcd_left"].update("")  # Empty left space
        self.rich_layout["lcd_right"].update("")  # Empty right space

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

        # Register cleanup
        atexit.register(self._cleanup)

        # if Unix, set stdin to cbreak mode

        if not sys.platform.startswith("win"):
            try:
                import termios
                import tty

                fd = sys.stdin.fileno()
                self._orig_term_settings = termios.tcgetattr(fd)
                tty.setcbreak(fd)
            except ImportError:
                self.log.warning("Unable to register keyboard handling")
                return None

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

    def _handle_resize(self, signum: int, frame) -> None:
        """Handle terminal resize by redrawing the display."""
        logging.debug("Display resized to {}x{}".format(self.console.size.width, self.console.size.height))
        self._update_display(force=True)

    def _cleanup(self) -> None:
        """Clean up resources and restore terminal state."""
        if hasattr(self, "console"):
            self.console.set_alt_screen(False)
            self.console.show_cursor(True)

        if not sys.platform.startswith("win") and self._orig_term_settings:
            try:
                import termios

                fd = sys.stdin.fileno()
                termios.tcsetattr(fd, termios.TCSADRAIN, self._orig_term_settings)
            except ImportError:
                pass

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

        panel = Panel(
            self._create_lcd_text(),
            title="[bold]LCD (h for help)[/bold]",
            border_style=STYLE_PANEL,
            padding=(0, 1),
            width=self.cols + 4,
            height=self.rows + 2,
            expand=False,
        )

        return panel

    def _create_lcd_text(self) -> Text:
        style = self.backlight_on_style if self._backlight_on else self.backlight_off_style
        lcd_lines = []
        for row_text in self.buffer:
            # Pad/truncate each row to exactly cols characters
            padded_row = row_text[: self.cols].ljust(self.cols, " ")
            lcd_lines.append(padded_row)

        lcd_content = "\n".join(lcd_lines)

        # Create styled text
        return Text(lcd_content, style=style)

    def _create_help_panel(self) -> Panel:
        help_content = "\n".join(HELP_TEXT)

        help_panel = Panel(
            help_content,
            title="[bold]Help (h again to close)[/bold]",
            border_style=STYLE_PANEL,
            padding=(0, 1),
            expand=False,
        )

        return help_panel

    def _create_log_panel(self) -> Panel:
        """Create the log messages panel."""

        table = self._create_log_table()

        panel = Panel(
            table,
            title="[bold]Log Messages (latest first)[/bold]",
            border_style=STYLE_PANEL,
        )
        return panel

    def _create_log_table(self):
        table = Table(show_header=True, header_style=STYLE_TABLE_HEADER, box=None, show_edge=False)
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

        if self.help_overlay:
            help_panel = self._create_help_panel()
            live_display = RichLayout(Align.center(help_panel, vertical="middle"))
        else:
            live_display = self.rich_layout

        # Update only the panels that have changed
        updated = False
        if self._lcd_dirty:
            self.rich_layout["lcd"].update(self._create_lcd_panel())
            self._lcd_dirty = False
            updated = True

        if self._logs_dirty:
            self.rich_layout["logs"].update(self._create_log_panel())
            self._logs_dirty = False
            updated = True

        # Only refresh the display if something changed
        if updated or force:
            # Start Live display if not already started
            if self.live is None:
                self.live = Live(live_display, console=self.console, screen=True, auto_refresh=False)
                self.live.start()
            else:
                # Refresh the existing live display
                self.live.update(live_display)
                self.live.refresh()

    def update(self) -> None:
        for row in range(self.rows):
            text_line = self._layout.get_line(row, self.cols)

            # Only update if the row has actually changed
            if self.buffer[row] != text_line:
                self.buffer[row] = text_line
                self._lcd_dirty = True

        # Update all rows at once
        if self._lcd_dirty:
            self._update_display()

    def set_backlight(self, state: bool) -> None:
        if self._backlight_on != state:
            self._backlight_on = state
            self._update_display(force=True)  # Force full update to apply new style

    def _read_keypress(self) -> Optional[str]:
        """Read a single keypress without blocking."""
        if not sys.stdin.isatty():
            return None

        if sys.platform.startswith("win"):
            try:
                import msvcrt

                if msvcrt.kbhit():
                    return msvcrt.getwch()
            except (ImportError, OSError):
                return None

        import select

        try:
            dr, _, _ = select.select([sys.stdin], [], [], 0)
        except (ValueError, OSError):
            return None

        if not dr:
            return None

        return sys.stdin.read(1)

    def poll_interactive(self) -> Optional[str]:
        """Handle a keypress and return action plus optional backlight override.
        TODO this should be interrupt-driven so it doesn't need to wait for the next main_loop iteration"""
        key = self._read_keypress()
        if key is None:
            return None

        if key.lower() == "q":
            return "quit"

        if key.lower() == "b":
            return "backlight_state"

        if key.lower() == "h":
            self.help_overlay = not self.help_overlay
            self._update_display(force=True)
            return None

        return None

    def __del__(self):
        # Stop live display if running
        if hasattr(self, "live") and self.live is not None:
            try:
                self.live.stop()
            except Exception:
                pass  # Ignore errors during cleanup

        # Decrement instance count
        RichTerminalDisplay._instance_count = max(0, RichTerminalDisplay._instance_count - 1)
        self._cleanup()
        atexit.unregister(self._cleanup)
