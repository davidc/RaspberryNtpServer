"""Rich terminal-based LCD-style display"""

import logging
import sys
import signal
import atexit
from typing import Optional, List, Tuple
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live

from .display import Display


class RichLogHandler(logging.Handler):
    """Custom log handler that displays messages in the rich terminal display."""

    def __init__(self, display: 'RichTerminalDisplay'):
        super().__init__()
        self.display = display
        self.messages: List[Tuple[str, str, str]] = []  # (level, message, timestamp)

    def emit(self, record: logging.LogRecord) -> None:
        """Add a log message to the display."""
        level = record.levelname
        message = record.getMessage()
        
        # Format timestamp
        import time
        time_str = time.strftime("%H:%M:%S", time.localtime(record.created))

        self.messages.append((level, message, time_str))

        # Keep only the latest messages that fit
        max_messages = self.display._calculate_max_log_messages()
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

        # Mark logs as dirty for selective update
        self.display._logs_dirty = True
        self.display._update_display()


class RichTerminalDisplay(Display):
    """A terminal LCD-style display implemented with rich."""

    _instance_count = 0  # Class variable to track instances

    def __init__(
        self,
        cols: int = 20,
        rows: int = 4,
        backlight_on_style: str = "bright_cyan on blue",
        backlight_off_style: str = "cyan on black",
    ):
        """Initialize the Rich terminal display."""
        # Prevent multiple instances
        RichTerminalDisplay._instance_count += 1
        if RichTerminalDisplay._instance_count > 1:
            raise RuntimeError("Only one RichTerminalDisplay instance is allowed")

        self.log: logging.Logger = logging.getLogger("RichTerminalDisplay")
        self.cols: int = cols
        self.rows: int = rows
        self._backlight_on: bool = True
        self.backlight_on_style: str = backlight_on_style
        self.backlight_off_style: str = backlight_off_style
        self.buffer: list[str] = [" " * cols for _ in range(rows)]

        self.console = Console()
        self.log_handler: Optional[RichLogHandler] = None

        # Track if LCD needs redraw
        self._lcd_dirty = True
        self._logs_dirty = True

        # Signal handler backup
        self._old_sigwinch_handler = None

        # Set up Rich layout
        self.layout = Layout()
        self.layout.split_column(
            Layout(name="lcd_container", size=self.rows + 2),  # Fixed height for LCD
            Layout(name="logs")  # Logs take remaining space
        )
        
        # Set up LCD container with horizontal centering
        self.layout["lcd_container"].split_row(
            Layout(name="lcd_left", ratio=1),  # Flexible space
            Layout(name="lcd", size=self.cols + 4),  # LCD panel width
            Layout(name="lcd_right", ratio=1)  # Flexible space
        )

        self.layout["lcd_left"].update("")  # Empty left space
        self.layout["lcd_right"].update("")  # Empty right space

        self.log.info(self.layout["logs"])

        self.live: Optional[Live] = None

        try:
            # Set up signal handler for terminal resize
            self._old_sigwinch_handler = signal.signal(signal.SIGWINCH, self._handle_resize)
        except (OSError, ValueError):
            # Signal handling not available on this platform
            self._old_sigwinch_handler = None

        try:
            # Register cleanup
            atexit.register(self._cleanup)

            # Replace root logger handlers with our custom handler
            self._setup_logging()

            # Update initial display
            self._update_display()

            self.log.info("RichTerminalDisplay initialized")
        except Exception as e:
            self.log.error(f"Failed to initialize RichTerminalDisplay: {e}")
            raise

    def _handle_resize(self, signum: int, frame) -> None:
        """Handle terminal resize by redrawing the display."""
        logging.info("Display resized to {}x{}".format(self.console.size.width, self.console.size.height))
        self._update_display()

    def _cleanup(self) -> None:
        """Clean up resources and restore terminal state."""
        if hasattr(self, 'console'):
            self.console.show_cursor(True)
        
        # Restore original signal handler
        if self._old_sigwinch_handler is not None:
            signal.signal(signal.SIGWINCH, self._old_sigwinch_handler)

    def _setup_logging(self) -> None:
        """Set up Python logging to use our custom handler."""

        # Create our log handler
        self.log_handler = RichLogHandler(self)
        self.log_handler.setLevel(logging.INFO)

        root_logger = logging.getLogger()

        # Remove all existing handlers to prevent printing over our terminal
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Add our custom handler
        root_logger.addHandler(self.log_handler)
        root_logger.setLevel(logging.INFO)

    def _calculate_max_log_messages(self) -> int:
        """Calculate maximum log messages that can fit based on terminal height."""
        terminal_height = self.console.size.height
        
        # LCD takes self.rows + 2 (borders), logs take the rest
        # Log panel has header (1) + borders (2) + table header (1) = 4 lines overhead
        # Available height for log rows = terminal_height - (self.rows + 2) - 4
        available_log_height = terminal_height - (self.rows + 2) - 4
        
        return max(1, available_log_height)

    def _get_log_level_color(self, level: str) -> str:
        """Get color for log level."""
        colors = {
            'DEBUG': 'dim cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold red',
        }
        return colors.get(level, 'white')

    def _create_lcd_panel(self) -> Panel:
        """Create the LCD panel."""
        style = self.backlight_on_style if self._backlight_on else self.backlight_off_style
        
        # Create LCD content as centered lines
        lcd_lines = []
        for row_text in self.buffer:
            # Pad/truncate each row to exactly cols characters
            padded_row = row_text[:self.cols].ljust(self.cols, " ")
            lcd_lines.append(padded_row)
        
        lcd_content = "\n".join(lcd_lines)
        
        # Create styled text
        text = Text(lcd_content)
        text.stylize(style)
        
        # Create panel with border matching log panel
        panel = Panel(
            text,
            title="[bold]LCD Display[/bold]",
            border_style="blue",  # Same as log panel
            padding=(0, 1),
            width=self.cols + 4  # Content width + padding + borders
        )
        
        return panel

    def _create_log_panel(self) -> Panel:
        """Create the log messages panel."""
        # Calculate available height for the log panel
        terminal_height = self.console.size.height
        log_panel_height = terminal_height - (self.rows + 2)  # LCD height + borders
        
        table = Table(show_header=True, header_style="bold magenta", box=None, show_edge=False)
        table.add_column("Time", style="dim", width=8, no_wrap=True)
        table.add_column("Level", width=8, no_wrap=True)
        table.add_column("Message", style="white")

        if self.log_handler and self.log_handler.messages:
            # Add actual log messages TODO check for wrapping and check we don't have too many, only use the latest
            for level, message, timestamp in self.log_handler.messages:
                table.add_row(
                    timestamp,
                    Text(level, style=self._get_log_level_color(level)),
                    message
                )
            
            current_rows = len(self.log_handler.messages) + 1  # +1 for header
        else:
            current_rows = 0

        # Add empty rows to fill the space (header + borders + table header = 4, so subtract 4)
        empty_rows = max(0, log_panel_height - 4 - current_rows)
        for _ in range(empty_rows):
            table.add_row("x", "", "")

        panel = Panel(
            table, 
            title="[bold]Log Messages[/bold]", 
            border_style="blue"
        )
        return panel

    def _update_display(self) -> None:
        """Update only the changed parts of the display layout."""
        
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
        if updated:
            # Start Live display if not already started
            if self.live is None:
                self.live = Live(self.layout, console=self.console, screen=False, auto_refresh=False)
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
            self._update_display()

    def __del__(self):
        # Stop live display if running
        if hasattr(self, 'live') and self.live is not None:
            try:
                self.live.stop()
            except Exception:
                pass  # Ignore errors during cleanup
        
        # Decrement instance count
        RichTerminalDisplay._instance_count = max(0, RichTerminalDisplay._instance_count - 1)
        self._cleanup()
        atexit.unregister(self._cleanup)
