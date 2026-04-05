"""Base Display class for different display hardware types"""

from abc import ABC, abstractmethod
from typing import Any

from layouts import Layout


class Display(ABC):
    """Abstract base class for display hardware implementations.

    All display classes must implement this interface to work with chronotron.

    The constructor should raise an exception if initialization fails (e.g. hardware not found).
    """

    def __init__(self):
        self._layout: Layout

    def set_layout(self, layout: Layout):
        self._layout = layout

    @abstractmethod
    def set_backlight(self, state: bool) -> None:
        """Set backlight on/off (or equivalent status indicator for non-LCD displays).

        Args:
            state: True to turn on, False to turn off
        """
        pass

    @abstractmethod
    def update(self) -> None:
        """Update the display."""
        pass
