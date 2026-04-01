"""
Scrolling buffer handler for logging that maintains a fixed-size buffer by removing old entries.
"""

import logging
import logging.handlers
from typing import List, Callable


class ScrollingBufferHandler(logging.handlers.BufferingHandler):
    """A logging handler that buffers log records in a scrolling fashion.

    Unlike the standard BufferingHandler, this maintains the buffer at a fixed
    size by removing the oldest entries when new ones are added if necessary.

    The buffer can be accessed via the 'buffer' attribute, and a 'wanted' flag
    indicates if any component wants to keep this buffer beyond startup.
    """

    def __init__(self, capacity: int):
        """Initialize the scrolling buffer handler.

        Args:
            capacity: Maximum number of log records to keep in the buffer.
        """
        super().__init__(capacity)
        self._wanted = False
        self._listeners: List[Callable[[], None]] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a record by adding it to the buffer, removing old entries if necessary."""
        if len(self.buffer) >= self.capacity:
            # Remove the oldest entry
            self.buffer.pop(0)
        self.buffer.append(record)

        # Notify all listeners that the buffer has been updated
        for listener in self._listeners:
            listener()

    def flush(self) -> None:
        """Flush method - does nothing ."""
        pass

    def close(self):
        """
        Close the handler: clear the buffer and chain to parent class.
        """
        try:
            self.buffer.clear()
        finally:
            logging.Handler.close(self)

    def wanted(self) -> None:
        """Mark that this buffer is wanted by some component."""
        self._wanted = True

    @property
    def is_wanted(self) -> bool:
        """Check if this buffer is wanted."""
        return self._wanted

    def add_listener(self, callback: Callable[[], None]) -> None:
        """Add a listener to be notified when the buffer is updated.

        Args:
            callback: A callable that takes no arguments, called when buffer updates.
        """
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        """Remove a listener.

        Args:
            callback: The callback to remove.
        """
        if callback in self._listeners:
            self._listeners.remove(callback)

    def get_recent_records(self, count: int) -> List[logging.LogRecord]:
        """Get the most recent 'count' records from the buffer.

        Args:
            count: Number of recent records to return.

        Returns:
            List of the most recent log records, up to 'count' items.
        """
        return self.buffer[-count:] if self.buffer else []
