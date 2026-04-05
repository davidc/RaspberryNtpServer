"""Default 4-line display layout for Chronotron."""

from __future__ import annotations

import time
from typing import Any

from .layout import Layout


class DefaultFourLineLayout(Layout):
    """Default 4-line display layout for Chronotron."""

    def __init__(self) -> None:
        self.stats: dict[str, Any] = {}

    def update(self, stats: dict[str, Any]) -> None:
        self.stats = dict(stats)

    def get_line(self, line_number: int, cols: int) -> str:
        line = ""
        if line_number == 0:
            line = self._format_time_line(cols)
        elif line_number == 1:
            line = self._format_tracking_line(cols)
        elif line_number == 2:
            line = self._format_source_line(cols)
        elif line_number == 3:
            line = self._format_footer_line(cols)

        return self._pad_or_truncate(line, cols)

    def _format_time_line(self, cols: int) -> str:
        current_time = self.stats.get("current_time")
        if current_time is None:
            return ""

        date_str = time.strftime("%Y-%m-%d", current_time) + " "
        time_str = time.strftime("%H:%M:%S", current_time)

        basic_width = len(date_str) + len(time_str)

        full_utc_offset = self._format_utc_offset(current_time.tm_gmtoff)

        if basic_width + 1 + len(full_utc_offset) <= cols:
            # We have space for full offset
            time_str += " " + full_utc_offset
        elif current_time.tm_gmtoff == 0 and basic_width + 1 <= cols:
            # We have space for a zulu marker and we're in UTC
            time_str += "Z"

        return self._format_justified_line(date_str, time_str, cols)

    def _format_tracking_line(self, cols: int) -> str:
        stratum = self.stats.get("stratum")
        if stratum is None:
            stratum_str = "S[?]"
        else:
            stratum_str = f"S[{stratum}]"

        offset = self.stats.get("system_time_offset")
        if offset is None:
            offset_str = "?"
        else:
            offset_str = self._format_signed_offset(offset)

        return self._format_justified_line(stratum_str + " ", offset_str, cols)

    def _format_source_line(self, cols: int) -> str:
        if self.stats.get("is_locked"):
            source_str = "L[*] "
        else:
            source_str = "L[ ] "

        source_str += self.stats.get("source") or ""

        return self._pad_or_truncate(source_str, cols)

    def _format_footer_line(self, cols: int) -> str:
        if self.stats.get("mode") is None:
            mode_str = "F[-]"
        else:
            mode_str = f"F[{self.stats.get('mode'):1}]"

        sats_used = self.stats.get("sats_used")
        sats_used_text = "--" if sats_used is None else f"{sats_used:02}"

        sats = self.stats.get("sats")
        sats_text = "--" if sats is None else f"{sats:02}"

        sats_str = f"{sats_used_text}/{sats_text}"

        adjusted_offset = self.stats.get("adjusted_offset")
        if adjusted_offset is None:
            dev_str = "?"
        else:
            dev_str = self._format_signed_offset(adjusted_offset)

        return self._format_justified_line(
            mode_str + " " + sats_str + " ", dev_str, cols
        )
