#!/usr/bin/python

import time
from datetime import datetime, time as dt_time
import subprocess
import gps  # from python3-gps  # pyright:ignore[reportMissingTypeStubs]
import logging
import threading
from typing import Any, cast
import yaml
import os

from displays import Display, create_display

# from button import Button

CHRONOTRON_VERSION = "3.0.0"

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
gpsd_host: str
gpsd_port: int

# Runtime
displays: list[Display] = []
log: logging.Logger

# Global Variables for GPS data from background thread
gps_lock: threading.Lock = threading.Lock()
gps_mode: int | None = None
gps_sats_used: int | None = None
gps_sats: int | None = None


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
        display = create_display(display_config)
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

    options = config.get("gpsd", {})
    global gpsd_host
    global gpsd_port
    gpsd_host = options.get("host", "localhost")
    gpsd_port = options.get("port", 2947)

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


def exec_cmd(cmd: list[str]) -> list[str]:
    ret: list[str] = []
    p = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=-1
    )
    if p.stdout is None:
        log.error(f"Failed to execute {cmd}")
        return []
    for line in p.stdout:
        ret.append(line.decode("utf-8").strip())
    _ = p.wait()
    if p.returncode != 0:
        cm = ""
        for c in cmd:
            cm = cm + c + " "
        print("Warning: " + cm + "failed: " + str(p.returncode))
    return ret


def get_statistics(
    _host: str = "localhost",
) -> dict[str, Any]:  # pyright:ignore[reportExplicitAny]
    # return {
    #     "mode": "?",
    #     "sats": "?",
    #     "sats_used": "?",
    #     "stratum": "?",
    #     "system_time_offset": None,
    #     "is_locked": False,
    #     "is_pps": False,
    #     "source": None,
    #     "adjusted_offset": None,
    # }
    # Get number of active satellites from gpsd
    n = 0
    stats: dict[str, Any] = {}  # pyright:ignore[reportExplicitAny]
    with gps_lock:
        stats["mode"] = gps_mode
        stats["sats"] = gps_sats
        stats["sats_used"] = gps_sats_used

    # Get chrony tracking information
    cmd = ["chronyc", "tracking"]
    ret = exec_cmd(cmd)
    stats["stratum"] = None
    stats["system_time_offset"] = None
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
                    stats["system_time_offset"] = val
            elif parm == "Stratum":
                try:
                    n = int(pars[1])
                    stats["stratum"] = n
                except:
                    stats["stratum"] = None

    # Get current time source
    cmd = ["chronyc", "sources"]
    ret = exec_cmd(cmd)
    stats["is_locked"] = False
    stats["is_pps"] = False
    stats["source"] = None
    stats["adjusted_offset"] = None
    for line in ret:
        if "#* PPS" in line:
            stats["is_locked"] = True
            stats["is_pps"] = True
            stats["source"] = "PPS"
            # #* PPS0                          0   4   377    22   +271ns[ +385ns] +
            try:
                stats["adjusted_offset"] = line[50:59].strip()
            except:
                pass
        else:
            if "^*" in line:
                stats["is_locked"] = True
                stats["is_pps"] = False
                try:
                    stats["source"] = line[3:33].strip()
                except:
                    pass
                try:
                    stats["adjusted_offset"] = line[50:59].strip()
                except:
                    pass

    return stats


def init():
    logging.basicConfig(level=logging.INFO)
    global log
    log = logging.getLogger("chronotron")
    log.setLevel("INFO")

    # TODO temporarily store the initial log messages in a buffer so they can be available to rich_terminal.
    # if they haven't been collected by the time initialisation is complete, discard them and restore the original log handler.

    log.info(f"Chronotron version {CHRONOTRON_VERSION} starting")

    # Load and parse configuration
    config = load_configuration()
    parse_configuration(config)

    gps_thread = threading.Thread(target=gps_client)
    gps_thread.daemon = True
    gps_thread.start()


def main_loop():
    last_time = ""
    last_backlight = False
    last_offset = ""
    select_state = 0
    select_states = 2
    trigger_time = 0
    main_state = 0
    main_states = 2
    old_lock = False
    old_pps = False
    old_stratum = None
    old_src = None

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
            should_backlight = is_backlight_wanted()
            if (
                should_backlight != last_backlight or last_time == ""
            ):  # last_time is "" at startup, so always set initial state
                last_backlight = should_backlight
                log.info("Turning backlight " + ("ON" if should_backlight else "OFF"))
                for display in displays:
                    display.set_backlight(should_backlight)

            last_time = time_str
            stats = get_statistics()

            if stats["is_locked"] != old_lock:
                old_lock: bool = cast(bool, stats["is_locked"])
                if old_lock is True:
                    log.info("Chrony aquired lock to time source")

            if old_src != stats["source"]:
                old_src: str | None = cast(str | None, stats["source"])
                if old_src is None:
                    src = "None"
                else:
                    src = old_src
                log.info(f"Chrony receiving time source from {src}")

            if old_stratum != stats["stratum"]:
                old_stratum: str | None = cast(str | None, stats["stratum"])
                if old_stratum is None:
                    strat: str = "?"
                else:
                    strat = old_stratum
                log.info(f"Chrony stratum level changed to {strat}")

            if old_pps != stats["is_pps"]:
                old_pps: bool = cast(bool, stats["is_pps"])
                if old_pps is True:
                    log.info("Chrony locked to high precision GPS PPS signal")
                else:
                    log.info("Chrony lost PPS signal")

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
        time.sleep(1)  # 0.05 - TODO, config update_interval in config file
        # log.info("Just saying hi.")


def gps_client():
    global gps_mode
    global gps_sats
    global gps_sats_used

    session: gps.gps | None = None

    while True:

        try:
            session = gps.gps(
                host=gpsd_host, port=str(gpsd_port), mode=gps.WATCH_ENABLE
            )
            log.info(f"Connected to gpsd at {gpsd_host}:{gpsd_port}")
            while 0 == session.read():
                with gps_lock:
                    log.info(
                        f"data fix {len(session.satellites)} used {session.satellites_used} mode {session.fix.mode}"
                    )
                    gps_mode = session.fix.mode
                    gps_sats = len(session.satellites)
                    gps_sats_used = session.satellites_used
                time.sleep(1)  # TODO make this the same as our refresh rate.
        except Exception as e:
            log.warning(f"gpsd {gpsd_host}:{gpsd_port} connection error: {e}")
        finally:
            if session:
                session.close()

        with gps_lock:
            gps_mode = None
            gps_sats_used = None
            gps_sats = None

        log.info("Waiting 5 seconds before retrying gpsd connection...")
        time.sleep(5)


init()

main_loop()
