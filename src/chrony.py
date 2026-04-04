"""
Chrony client module for retrieving NTP synchronisation data.
"""

import subprocess
import logging
import threading
import time
from typing import Any, Optional


class ChronyClient:
    """Client for retrieving NTP synchronisation data from Chrony."""

    def __init__(self, update_interval: Optional[float]):
        """Initialize the Chrony client."""
        self.update_interval = update_interval or 1.0
        self.log = logging.getLogger("chronotron.chrony")

        self._lock = threading.Lock()
        self._stratum: Optional[int] = None
        self._system_time_offset: Optional[float] = None
        self._is_locked: bool = False
        self._is_pps: bool = False
        self._source: Optional[str] = None
        self._adjusted_offset: Optional[str] = None

        self._thread = threading.Thread(target=self._chrony_thread, daemon=True)
        self._thread.start()

    def _chrony_thread(self):
        """Background thread that periodically updates Chrony statistics."""
        while True:

            try:
                while True:
                    self._update_statistics()
                    time.sleep(self.update_interval)
            except Exception as e:
                self.log.warning(f"Error updating Chrony statistics: {e}")
            finally:
                with self._lock:
                    self._stratum = None
                    self._system_time_offset = None
                    self._is_locked = False
                    self._is_pps = False
                    self._source = None
                    self._adjusted_offset = None

            self.log.info("Waiting 5 seconds before retrying chronyc...")
            time.sleep(5)

    def _update_statistics(self) -> None:
        """
        Use chronyc to get current statistics and update internal state.
        """
        # Get chrony tracking information
        cmd = ["chronyc", "tracking"]
        ret = self._exec_cmd(cmd)
        new_stratum = None
        new_system_time_offset = None
        for line in ret:
            pars = line.split(":", 1)
            if len(pars) == 2:
                parm = pars[0].strip()
                if parm == "System time":
                    sub_pars = pars[1].strip().split(" ")
                    if len(sub_pars) > 2:
                        val = float(sub_pars[0])
                        if "slow" == sub_pars[2]:
                            val = -1.0 * val
                        new_system_time_offset = val
                elif parm == "Stratum":
                    try:
                        n = int(pars[1])
                        new_stratum = n
                    except (ValueError, IndexError):
                        new_stratum = None

        # Get current time source
        cmd = ["chronyc", "sources"]
        ret = self._exec_cmd(cmd)
        new_is_locked = False
        new_is_pps = False
        new_source = None
        new_adjusted_offset = None
        for line in ret:
            if "#* PPS" in line:
                new_is_locked = True
                new_is_pps = True
                new_source = "PPS"
                # #* PPS0                          0   4   377    22   +271ns[ +385ns] +
                try:
                    new_adjusted_offset = line[50:59].strip()
                except IndexError:
                    pass
            else:
                if "^*" in line:
                    new_is_locked = True
                    new_is_pps = False
                    try:
                        new_source = line[3:33].strip()
                    except IndexError:
                        pass
                    try:
                        new_adjusted_offset = line[50:59].strip()
                    except IndexError:
                        pass

        # Log significant changes
        if new_stratum != self._stratum:
            old_stratum_str = self._stratum if self._stratum is not None else "None"
            new_stratum_str = str(new_stratum) if new_stratum is not None else "None"
            self.log.info(
                f"Chrony stratum changed from {old_stratum_str} to {new_stratum_str}"
            )

        if new_is_locked != self._is_locked:
            if new_is_locked:
                self.log.info("Chrony aquired lock to time source")
            else:
                self.log.info("Chrony lost lock to time source")

        if new_is_pps != self._is_pps:
            if new_is_pps:
                self.log.info("Chrony locked to high precision GPS PPS signal")
            else:
                self.log.info("Chrony lost PPS signal")

        if new_source != self._source:
            self.log.info(f"Chrony source changed to {new_source}")

        # Update internal state with lock
        with self._lock:
            self._stratum = new_stratum
            self._system_time_offset = new_system_time_offset
            self._is_locked = new_is_locked
            self._is_pps = new_is_pps
            self._source = new_source
            self._adjusted_offset = new_adjusted_offset

    def _exec_cmd(self, cmd: list[str]) -> list[str]:
        """
        Execute a shell command and return output lines.

        Args:
            cmd: List of command arguments

        Returns:
            List of output lines, stripped of trailing whitespace
        """
        ret: list[str] = []
        p = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=-1
        )
        if p.stdout is None:
            self.log.error(f"Failed to execute {cmd}")
            return []
        for line in p.stdout:
            ret.append(line.decode("utf-8").strip())
        _ = p.wait()
        if p.returncode != 0:
            cm = " ".join(cmd)
            self.log.warning(f"Warning: {cm} failed: {p.returncode}")
        return ret

    @property
    def stratum(self) -> Optional[int]:
        """Get the stratum level."""
        with self._lock:
            return self._stratum

    @property
    def system_time_offset(self) -> Optional[float]:
        """Get the system time offset in seconds."""
        with self._lock:
            return self._system_time_offset

    @property
    def is_locked(self) -> bool:
        """Get whether Chrony is locked to a time source."""
        with self._lock:
            return self._is_locked

    @property
    def is_pps(self) -> bool:
        """Get whether Chrony is locked to PPS signal."""
        with self._lock:
            return self._is_pps

    @property
    def source(self) -> Optional[str]:
        """Get the current time source."""
        with self._lock:
            return self._source

    @property
    def adjusted_offset(self) -> Optional[str]:
        """Get the adjusted offset."""
        with self._lock:
            return self._adjusted_offset
