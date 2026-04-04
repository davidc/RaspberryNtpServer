#!/usr/bin/python

import time
from datetime import datetime, time as dt_time
import logging
import logging.handlers
from typing import Any, cast
import yaml
import os

from displays import Display, create_display
from gpsd import GpsdClient
from chrony import ChronyClient
from scrolling_buffer_handler import ScrollingBufferHandler

# from button import Button

CHRONOTRON_VERSION = "3.0.2"

######################################################
##                    ATTENTION                     ##
######################################################
##                                                  ##
##  As of v3, you no longer configure chronotron    ##
##  in this python file, but use a YAML file        ##
##  instead. Refer to README.md for documentation   ##
##  and chronotron.yaml for example configuration.  ##
##                                                  ##
######################################################


# Parsed Configuration with defaults (use chronotron.yaml to configure these)
backlight_mode: str = "on"  # "on", "off", or "timed"
backlight_start_time_obj: dt_time | None = None
backlight_end_time_obj: dt_time | None = None
display_utc_time: bool = False
display_refresh_interval: float = 0.25
gpsd_host: str
gpsd_port: int

# Runtime
log: logging.Logger
log_buffer: ScrollingBufferHandler

displays: list[Display] = []
gps_client: GpsdClient
chrony_client: ChronyClient


# ------- CONFIGURATION FROM YAML FILE -----------------------
def load_configuration(
    config_file: str = "chronotron.yaml",
) -> dict[str, Any]:  # pyright:ignore[reportExplicitAny]
    """
    Load configuration from YAML file.
    If the file doesn't exist in the current directory, a basic default will be used.
    TODO add a command line arg -f to specify the config file location
    """
    default_config = {
        "options": {
            "backlight": {
                "start_time": "07:00",
                "end_time": "21:00",
            },
            "display_utc_time": False,
        },
        "displays": [
            {
                "type": "hd44780",
                "sm_bus": 1,
                "i2c_address": 0x27,
                "adafruit_hardware": False,
                "fast_update": True,
                "cols": 20,
                "rows": 4,
            }
        ],
    }

    # Check if config file exists
    if not os.path.exists(config_file):
        # TODO this should be fatal if the user specified the file using -f
        log.warning(f"Config file {config_file} not found, using defaults")
        return default_config

    try:
        with open(config_file, "r") as f:
            loaded_config = yaml.safe_load(f)
            if loaded_config is None:
                return default_config
            return loaded_config
    except Exception as e:
        log.error(f"Error parsing config file {config_file}: {e}")
        raise


def parse_configuration(config: dict[str, Any]):
    # Extract global options configuration
    options = config.get("options", {})
    backlight_config = options.get("backlight", True)  # Default to always on

    global display_utc_time
    display_utc_time = options.get("display_utc_time", False)

    global display_refresh_interval
    display_refresh_interval = options.get("display_refresh_interval", 0.25)

    global backlight_mode
    # Parse backlight configuration
    if isinstance(backlight_config, bool):
        backlight_mode = "on" if backlight_config else "off"
    elif isinstance(backlight_config, dict):
        if "start_time" not in backlight_config or "end_time" not in backlight_config:
            raise ValueError(
                "Backlight configuration dictionary must contain both 'start_time' and 'end_time' keys."
            )

        backlight_mode = "timed"
        try:
            backlight_start_time_obj = datetime.strptime(
                backlight_config["start_time"], "%H:%M"
            ).time()
            backlight_end_time_obj = datetime.strptime(
                backlight_config["end_time"], "%H:%M"
            ).time()
        except ValueError as e:
            raise ValueError(f"Invalid time format in backlight configuration: {e}")
    else:
        raise ValueError(
            f"Invalid backlight configuration type: {type(backlight_config)}. Must be boolean or dictionary."
        )

    # Initialise displays from configuration
    displays_config = config.get("displays", [])

    for display_config in displays_config:
        display = create_display(display_config, log_buffer)
        if display is not None:
            displays.append(display)
            # log.info(f"Initialised display: {display_config.get('type', 'unknown')}")
        else:
            log.warning(
                f"Failed to initialise display: {display_config.get('type', 'unknown')}"
            )

    if not displays:
        log.error("No displays were successfully initialised, exiting")
        exit(-1)

    log.info(
        "Initialised %d display%s" % (len(displays), "" if len(displays) == 1 else "s")
    )

    # gpsd config
    global gpsd_client
    global chrony_client
    gpsd_config = config.get("gpsd", {})
    gpsd_host = gpsd_config.get("host", None)
    gpsd_port = gpsd_config.get("port", None)
    gpsd_update_interval = gpsd_config.get("data_update_interval", None)
    gpsd_client = GpsdClient(host=gpsd_host, port=gpsd_port, update_interval=gpsd_update_interval)

    # chrony config
    chrony_config = config.get("chrony", {})
    chrony_update_interval = chrony_config.get("data_update_interval", None)
    chrony_client = ChronyClient(update_interval=chrony_update_interval)

    if backlight_mode != "timed":
        log.info("Backlight will be always " + backlight_mode.upper())
    else:
        log.info(
            "Backlight will be on between "
            + backlight_start_time_obj.strftime("%H:%M") # pyright: ignore[reportPossiblyUnboundVariable]
            + " and "
            + backlight_end_time_obj.strftime("%H:%M") # pyright: ignore[reportPossiblyUnboundVariable]
        )


def is_backlight_wanted() -> bool:
    """Determine if backlight should be on based on configuration and current time."""
    if backlight_mode == "on":
        return True
    elif backlight_mode == "off":
        return False
    else:  # timed mode
        # Get the current local time
        current_time = datetime.now().time()
        # Check if the interval spans across midnight
        if backlight_start_time_obj > backlight_end_time_obj: # pyright: ignore[reportOperatorIssue]
            return (
                current_time >= backlight_start_time_obj or current_time < backlight_end_time_obj # pyright: ignore[reportOperatorIssue]
            )
        else:
            return backlight_start_time_obj <= current_time <= backlight_end_time_obj # pyright: ignore[reportOptionalOperand, reportOperatorIssue]


def init():
    # Initialise logging
    logging.basicConfig(level=logging.INFO)
    global log
    log = logging.getLogger("chronotron")
    # log.setLevel("INFO")

    # Store initial log messages in a buffer until displays are initialised, so they can be available to rich_terminal
    global log_buffer
    log_buffer = ScrollingBufferHandler(capacity=128)
    root_logger = logging.getLogger()
    root_logger.addHandler(log_buffer)

    log.info(f"Chronotron version {CHRONOTRON_VERSION} starting")

    # Load and parse configuration
    config = load_configuration()
    parse_configuration(config)

    # Now displays are initialised, remove our log buffer if nobody wants it
    if not log_buffer.is_wanted:
        root_logger.removeHandler(log_buffer)
        log_buffer.close()

    log.info(f"Chronotron version {CHRONOTRON_VERSION} started with {len(displays)} display{len(displays) != 1 and 's' or ''}")

def main_loop():
    last_time = ""
    last_backlight = False
    last_offset = ""
    select_state = 0
    select_states = 2
    trigger_time = 0
    main_state = 0
    main_states = 2

    def select_button():  # pyright:ignore[reportUnusedFunction]
        nonlocal select_state
        nonlocal select_states
        nonlocal trigger_time
        trigger_time = time.time()
        select_state = (select_state + 1) % select_states

    def main_button():  # pyright:ignore[reportUnusedFunction]
        nonlocal main_state
        nonlocal main_states
        nonlocal trigger_time
        trigger_time = time.time()
        main_state = (main_state + 1) % main_states

    # bt = Button([(27, "blue", select_button), (22, "black", main_button)])

    while True:
        if display_utc_time is True:
            time_str: str = time.strftime("%Y-%m-%d  %H:%M:%S", time.gmtime())
        else:
            time_str = time.strftime("%Y-%m-%d  %H:%M:%S")
        if time_str != last_time:
            # Set backlight state for all displays
            want_backlight = is_backlight_wanted()
            if (
                want_backlight != last_backlight or last_time == ""
            ):  # last_time is "" at startup, so always set initial state
                last_backlight = want_backlight
                log.info("Turning backlight " + ("ON" if want_backlight else "OFF"))
                for display in displays:
                    display.set_backlight(want_backlight)

            last_time = time_str

            # Get statistics from both clients
            stats: dict[str, Any] = {}  # pyright:ignore[reportExplicitAny]
            stats["mode"] = gpsd_client.mode
            stats["sats"] = gpsd_client.sats
            stats["sats_used"] = gpsd_client.sats_used
            stats["stratum"] = chrony_client.stratum
            stats["system_time_offset"] = chrony_client.system_time_offset
            stats["is_locked"] = chrony_client.is_locked
            stats["is_pps"] = chrony_client.is_pps
            stats["source"] = chrony_client.source
            stats["adjusted_offset"] = chrony_client.adjusted_offset

            # if select_state == 0:
            #     lcd.print_row(0, time_str)
            # else:
            #     if time.time() - trigger_time > 10:
            #         select_state = 0
            #     lcd.print_row(0, "Select 1")

            offset: str | None = cast(str | None, stats["system_time_offset"])
            offs = "            "
            if offset is not None:
                if stats["stratum"] is None:
                    offs = "S[?]"
                else:
                    offs = f"S[{stats['stratum']}]"
                offs += " {:+12.9f}sec".format(offset)
                if offs != last_offset:
                    last_offset = offs

            if stats["sats"] is None:
                sats = "--"
            else:
                sats = f"{stats['sats']:02}"
            if stats["sats_used"] is None:
                sats_used = "--"
            else:
                sats_used = f"{stats['sats_used']:02}"
            if stats["mode"] is None:
                mode = "-"
            else:
                mode = f"{stats['mode']:01}"
            if stats["is_locked"]:
                source_str = "L[*] "
            else:
                source_str = "L[ ] "
            if stats["source"] is None:
                source_str += "                    "
            else:
                source_str += cast(str, stats["source"])
            if stats["adjusted_offset"] is None:
                dev_str = "       "
            else:
                dev_str = f"{stats['adjusted_offset']:>7}"
            last_str = f"F[{mode}] {sats_used}/{sats}   {dev_str}"

            # Send display output to all configured displays
            for display in displays:
                display.print_row(0, time_str)
                display.print_row(1, offs)
                display.print_row(2, source_str)
                display.print_row(3, last_str)
        time.sleep(display_refresh_interval)


init()

main_loop()
