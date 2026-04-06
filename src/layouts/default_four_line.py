"""Default 4-line display layout for Chronotron."""

from __future__ import annotations

import time
from typing import Any, Optional

from .layout import Layout


class DefaultFourLineLayout(Layout):
    """Default 4-line display layout for Chronotron."""

    def __init__(self) -> None:
        self.stats: dict[str, Any] = {}

    def update(self, stats: dict[str, Any]) -> None:
        self.stats = dict(stats)

    def _format_date(self) -> str:
        current_time = self.stats.get("current_time")
        if current_time is None:
            return ""

        return time.strftime("%Y-%m-%d", current_time) + " "

    def _format_time(self, remaining_cols: Optional[int]) -> str:
        current_time = self.stats.get("current_time")
        if current_time is None:
            return ""

        time_str = time.strftime("%H:%M:%S", current_time)

        # If we're on a 
        full_utc_offset = self._format_utc_offset(current_time.tm_gmtoff)

        # If we're on a fixed-width display, see if we can in an offset
        if remaining_cols is not None:
            if len(time_str) + 1 + len(full_utc_offset) <= remaining_cols:
                # We have space for full offset
                time_str += " " + full_utc_offset
            elif  current_time.tm_gmtoff == 0 and len(time_str) + 1 <= remaining_cols:
                # We have space for a zulu marker and we're in UTC
                time_str += "Z"
        else:
            # Variable width display, assume that we have space
            time_str += " " + full_utc_offset

        return time_str

    # TODO test with descending fileoutput width again, think I need a " " on time_str

    def _format_stratum(self) -> str:
        stratum = self.stats.get("stratum")
        if stratum is None:
            return "S[?]"
        else:
            return f"S[{stratum}]"

    def _format_system_time_offset(self, remaining_cols: Optional[int]) -> str:
        offset = self.stats.get("system_time_offset")
        if offset is None:
            return "?"
        else:
            return str(self._format_signed_offset(offset))

    def _format_source(self) -> str:
        if self.stats.get("is_locked"):
            source_str = "L[*] "
        else:
            source_str = "L[ ] "

        source_str += self.stats.get("source") or ""

        return source_str

    def _format_gps_fix(self) -> str:
        if self.stats.get("mode") is None:
            mode_str = "F[-]"
        else:
            mode_str = f"F[{self.stats.get('mode'):1}]"

        sats_used = self.stats.get("sats_used")
        sats_used_text = "--" if sats_used is None else f"{sats_used:02}"

        sats = self.stats.get("sats")
        sats_text = "--" if sats is None else f"{sats:02}"

        sats_str = f"{sats_used_text}/{sats_text}"

        return mode_str + " " + sats_str + " "

    def _format_adjusted_offset(self, remaining_cols: Optional[int]) -> str:
        adjusted_offset = self.stats.get("adjusted_offset")
        if adjusted_offset is None:
            return "?"
        else:
            return str(self._format_signed_offset(adjusted_offset))

        return self._format_justified_line(mode_str + " " + sats_str + " ", dev_str, cols)

    def get_line_left(self, line_number: int) -> str:
        if line_number == 0:
            return self._format_date()
        elif line_number == 1:
            return self._format_stratum()
        elif line_number == 2:
            return self._format_source()
        elif line_number == 3:
            return self._format_gps_fix()
        return ""

    def get_line_right(self, line_number: int, remaining_cols: Optional[int] = None) -> str:
        if line_number == 0:
            return self._format_time(remaining_cols)
        elif line_number == 1:
            return self._format_system_time_offset(remaining_cols)
        elif line_number == 2:
            return ""
        elif line_number == 3:
            return self._format_adjusted_offset(remaining_cols)
        return ""

    def get_line(self, line_number: int, cols: int) -> str:

        left_str = self.get_line_left(line_number)
        right_str = self.get_line_right(line_number, max(0, cols - len(left_str)))

        return self._format_justified_line(left_str, right_str, cols)
