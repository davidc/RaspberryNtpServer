"""OLED display driver using luma.oled"""

import logging
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c as i2c_serial
from luma.core.device import device as luma_device
import luma.oled.device as oled_device

from .display import Display


class OledDisplay(Display):
    """Display driver for OLED screens using luma.oled"""

    MIN_COLUMNS = 20
    MIN_ROWS = 4

    def __init__(
        self,
        device: str,
        i2c: Optional[dict[str, Any]] = None,
        physical_width: Optional[int] = None,
        physical_height: Optional[int] = None,
        rotate: int = 0,
        font: Optional[str] = None,
        backlight_on_contrast: Optional[int] = None,
        backlight_off_contrast: Optional[int] = None,
    ):
        super().__init__()

        self.log: logging.Logger = logging.getLogger("OledDisplay")

        if not device:
            raise ValueError("OLED display configuration must include a 'device' field")

        self.device_name = str(device).lower()

        if rotate not in (0, 1, 2, 3):
            raise ValueError("OLED display 'rotate' configuration must be 0, 1, 2, or 3")

        self.backlight_on_contrast = backlight_on_contrast if backlight_on_contrast else 255
        self.backlight_off_contrast = backlight_off_contrast if backlight_off_contrast else 1

        serial_interface = self._create_serial_interface(i2c)
        self._device: luma_device = self._create_device(serial_interface, physical_width, physical_height, rotate)

        self.display_width = self._device.width
        self.display_height = self._device.height

        self._font = self._select_font(font)

        char_size = self._measure_character_size(self._font)
        self._line_height = int(char_size[1])  # Add some spacing between lines
        print(f"Measured character size: {char_size}, line height set to: {self._line_height}")

        self.cols = self.display_width // char_size[0]
        self.rows = self.MIN_ROWS  # .display_height // self._line_height

        self._line_spacing = (self.display_height - (self._line_height * self.rows)) // self.rows
        print(f"Calculated line spacing: {self._line_spacing}")
        self._fixed_width: bool = self._is_fixed_width(self._font)

        if not self._is_fixed_width(self._font):
            self.cols = None

        self.log.info(
            f"Selected {'fixed width' if self._fixed_width else 'variable width'} font {self._font_display_name(self._font)} will fit "
            f"{self.cols} cols and {self.rows} rows on the {self._device.width}x{self._device.height} display"
        )

        self.log.info(
            f"OLED display initialised: {self.device_name} {self._device.width}x{self._device.height} rotate={rotate} cols={self.cols} rows={self.rows}"
        )

    def _font_display_name(self, font) -> str:
        if isinstance(font, ImageFont.FreeTypeFont):
            return f"{font.getname()[0]} {font.getname()[1]} size {font.size}"
        else:
            return f"image font size {font.size}"

    def _create_serial_interface(self, config: dict[str, Any] | None):
        config = config or {}
        if not isinstance(config, dict):
            raise ValueError("OLED i2c configuration must be a dict")

        serial_kwargs: dict[str, Any] = {}
        if "bus" in config and config["bus"] is not None:
            serial_kwargs["port"] = config["bus"]
        if "address" in config and config["address"] is not None:
            serial_kwargs["address"] = config["address"]

        return i2c_serial(**serial_kwargs) if serial_kwargs else i2c_serial()

    def _create_device(self, serial_interface, physical_width, physical_height, rotate) -> luma_device:
        device_class = getattr(oled_device, self.device_name, None)
        if device_class is None:
            raise ValueError(
                f"Unsupported OLED device type '{self.device_name}'. "
                "Supported types are as defined in luma.oled.device, such as ssd1306, sh1106, ch1115"
            )

        device_kwargs: dict[str, Any] = {"serial_interface": serial_interface}
        if physical_width is not None:
            device_kwargs["width"] = physical_width
        if physical_height is not None:
            device_kwargs["height"] = physical_height
        if rotate is not None:
            device_kwargs["rotate"] = rotate

        return device_class(**device_kwargs)

    def _measure_character_size(self, font) -> tuple[int, int]:
        sample_text = "M"
        bbox = font.getbbox(sample_text)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        return max(1, width), max(1, height)

    def _is_fixed_width(self, font) -> bool:
        # Check if all characters have the same width
        widths = set()
        for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789":
            char_width = font.getlength(char)
            widths.add(char_width)

        return len(widths) == 1

    def _select_font(self, font_file: Optional[str]) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:

        def test_font(font):
            char_width, line_height = self._measure_character_size(font)
            cols = self.display_width // char_width
            rows = self.display_height // line_height
            return cols, rows

        largest_font = None

        test_size = 4
        while test_size < 32:
            try:
                if font_file is None:
                    font = ImageFont.load_default(test_size)
                else:
                    font = ImageFont.truetype(font_file, test_size)
            except OSError:
                self.log.warning(f"Unable to load {font_file} at size {test_size}")
                break

            cols, rows = test_font(font)
            if cols >= self.MIN_COLUMNS and rows >= self.MIN_ROWS:
                largest_font = font
            else:
                break
            test_size += 0.25

        if largest_font is None:
            raise RuntimeError(
                f"No suitable font size found for OLED displaying at {self.display_width}x{self.display_height}"
            )

        return largest_font

    def set_backlight(self, state: bool) -> None:
        try:
            contrast_value = self.backlight_on_contrast if state else self.backlight_off_contrast
            self._device.contrast(contrast_value)
        except Exception as e:
            self.log.warning(f"Failed to set OLED backlight state: {e}")

    def update(self) -> None:
        image = Image.new("1", (self.display_width, self.display_height))
        draw = ImageDraw.Draw(image)

        for row in range(self.rows):

            y = (self._line_spacing // 2) + row * (self._line_height + self._line_spacing)

            left_str = self._layout.get_line_left(row)

            if left_str:
                draw.text((0, y), left_str, font=self._font, fill=255)

            remaining_cols = None if self.cols is None else max(0, self.cols - len(left_str))

            right_str = self._layout.get_line_right(row, remaining_cols)
            if right_str:
                draw.text((self.display_width, y), right_str, anchor="ra", font=self._font, fill=255)

        try:
            self._device.display(image)
        except Exception as e:
            self.log.error(f"Failed to update OLED display: {e}")
            raise
