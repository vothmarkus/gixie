from __future__ import annotations

from datetime import timedelta

DOMAIN = "gixie"

CONF_HOST = "host"

DEFAULT_PORT = 81

POLL_INTERVAL = timedelta(seconds=30)
AUTO_DST_INTERVAL = timedelta(hours=1)

# Gixie command numbers
CMD_RGB = 9
CMD_BRIGHTNESS = 14
CMD_POWER = 15
CMD_TIMEZONE = 16
CMD_MODE = 211
CMD_TIME_FORMAT = 213

# Read set
READ_CMDS = [CMD_RGB, CMD_BRIGHTNESS, CMD_POWER, CMD_TIMEZONE, CMD_MODE, CMD_TIME_FORMAT]

# Mode labels (user provided)
MODE_MAP = {
    0: "clock fixed color",
    1: "clock overall rainbow",
    2: "clock single rainbow",
    3: "number flash",
    4: "wordline",
    5: "custom number",
    6: "zero one random",
    7: "fan count",
}

MODE_LABEL_TO_VALUE = {v: k for k, v in MODE_MAP.items()}

DST_OFF = "off"
DST_ON = "on"
DST_AUTO = "auto"
DST_OPTIONS = [DST_OFF, DST_ON, DST_AUTO]
