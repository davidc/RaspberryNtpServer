"""
GPS client module for connecting to gpsd and retrieving GPS data.
"""

import gps
import logging
import threading
import time
from typing import Optional


class GpsdClient:
    """Client for retrieving GPS data from gpsd daemon."""

    def __init__(
        self, host: Optional[str], port: Optional[int], update_interval: Optional[float] = None
    ):
        """
        Initialize the GPS client and start the background thread.

        Args:
            host: The gpsd host address
            port: The gpsd port number
            update_interval: Time in seconds between GPS data polls
        """
        self.host = host or "127.0.0.1"
        self.port = port or 2947
        self.update_interval = update_interval or 1.0
        self.log = logging.getLogger("chronotron.gpsd")

        self._lock = threading.Lock()
        self._mode: Optional[int] = None
        self._sats: Optional[int] = None
        self._sats_used: Optional[int] = None

        self._thread = threading.Thread(target=self._gpsd_thread, daemon=True)
        self._thread.start()

    def _gpsd_thread(self):
        """Background thread that maintains connection to gpsd and updates data."""
        session: Optional[gps.gps] = None

        while True:
            try:
                session = gps.gps(
                    host=self.host, port=str(self.port), mode=gps.WATCH_ENABLE
                )
                self.log.info(f"Connected to gpsd at {self.host}:{self.port}")
                while 0 == session.read():
                    self._update_gps_data(session)

                    time.sleep(self.update_interval)
            except Exception as e:
                self.log.warning(f"gpsd {self.host}:{self.port} connection error: {e}")
            finally:
                if session:
                    session.close()

                with self._lock:
                    self._mode = None
                    self._sats_used = None
                    self._sats = None

            self.log.info("Waiting 5 seconds before retrying gpsd connection...")
            time.sleep(5)

    def _update_gps_data(self, session: gps.gps) -> None:

        new_mode = session.fix.mode
        new_sats = len(session.satellites)
        new_sats_used = session.satellites_used

        # Log significant changes
        if new_mode != self._mode:
            old_mode_str = str(self._mode) if self._mode is not None else "None"
            new_mode_str = str(new_mode) if new_mode is not None else "None"
            self.log.info(
                f"GPS sync mode changed from {old_mode_str} to {new_mode_str}"
            )

        with self._lock:
            self._mode = new_mode
            self._sats = new_sats
            self._sats_used = new_sats_used

    @property
    def mode(self) -> Optional[int]:
        """Get the current GPS fix mode."""
        with self._lock:
            return self._mode

    @property
    def sats(self) -> Optional[int]:
        """Get the total number of visible satellites."""
        with self._lock:
            return self._sats

    @property
    def sats_used(self) -> Optional[int]:
        """Get the number of satellites used for the fix."""
        with self._lock:
            return self._sats_used
