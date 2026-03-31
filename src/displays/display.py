"""Base Display class for different display hardware types"""

from abc import ABC, abstractmethod
from typing import Any


class Display(ABC):
    """Abstract base class for display hardware implementations.

    All display classes must implement this interface to work with chronotron.

    The constructor should raise an exception if initialization fails (e.g. hardware not found).
    """

    @abstractmethod
    def print_row(self, row: int, text: str) -> None:
        """Print text to a specific row on the display.

        Args:
            row: Row number (0-based indexing)
            text: Text to display (should be padded/truncated to display width)
        """
        pass

    @abstractmethod
    def set_backlight(self, state: bool) -> None:
        """Set backlight on/off (or equivalent status indicator for non-LCD displays).

        Args:
            state: True to turn on, False to turn off
        """
        pass
