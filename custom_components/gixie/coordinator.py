from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import websockets
from websockets.exceptions import WebSocketException
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AUTO_DST_INTERVAL,
    CMD_BRIGHTNESS,
    CMD_MODE,
    CMD_POWER,
    CMD_RGB,
    CMD_TIME_FORMAT,
    CMD_TIMEZONE,
    DEFAULT_PORT,
    DST_AUTO,
    DST_ON,
    POLL_INTERVAL,
    READ_CMDS,
)

_LOGGER = logging.getLogger(__name__)
_READ_ATTEMPTS = 2
_COMMAND_KEYS = {
    CMD_RGB: "rgb",
    CMD_BRIGHTNESS: "brightness",
    CMD_POWER: "power",
    CMD_TIMEZONE: "tz_index",
    CMD_MODE: "mode",
    CMD_TIME_FORMAT: "time_format",
}


def _validate_read_data(cmd_num: int, value: Any) -> Any:
    """Reject incomplete values before they can replace the last good state."""
    if value is None:
        raise UpdateFailed(f"Missing data for cmd {cmd_num}")

    def as_int(item: Any) -> int:
        if isinstance(item, bool) or not isinstance(item, (int, str)):
            raise ValueError("expected an integer")
        return int(item)

    try:
        if cmd_num == CMD_RGB:
            if not isinstance(value, list) or not value:
                raise ValueError("expected a non-empty RGB list")
            colors = []
            for color in value:
                if not isinstance(color, dict):
                    raise ValueError("expected an RGB object")
                channels = {
                    channel: as_int(color[channel])
                    for channel in ("red", "green", "blue")
                }
                if any(not 0 <= channel <= 255 for channel in channels.values()):
                    raise ValueError("RGB channel outside 0..255")
                colors.append({**color, **channels})
            return colors
        return as_int(value)
    except (KeyError, TypeError, ValueError) as err:
        raise UpdateFailed(f"Invalid data for cmd {cmd_num}: {err}") from err


def _system_utc_offset_hours() -> int:
    off = datetime.now().astimezone().utcoffset()
    if off is None:
        return 0
    return int(off.total_seconds() // 3600)


def clamp_offset(offset_hours: int) -> int:
    return max(-12, min(12, int(offset_hours)))


def offset_to_index(offset_hours: int) -> int:
    return clamp_offset(offset_hours) + 12


def index_to_offset(index: int) -> int:
    return int(index) - 12


@dataclass
class GixieSettings:
    host: str
    port: int = DEFAULT_PORT


class GixieClient:
    def __init__(self, settings: GixieSettings) -> None:
        self._settings = settings

    @property
    def uri(self) -> str:
        return f"ws://{self._settings.host}:{self._settings.port}"

    def _connect(self, timeout: float):
        # Use the connect context manager, also supported by websockets 10.3.
        return websockets.connect(self.uri, open_timeout=timeout, close_timeout=1.0)

    async def _request(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Send one command on a fresh connection and validate its response."""
        async with self._connect(timeout) as ws:
            # Some firmware sends a greeting before accepting commands.
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.5)
            except asyncio.TimeoutError:
                pass

            await asyncio.wait_for(ws.send(json.dumps(payload)), timeout=timeout)
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            if not isinstance(raw, (str, bytes)) or not raw.strip():
                raise UpdateFailed("Empty WebSocket response")

            try:
                msg = json.loads(raw)
            except (ValueError, UnicodeDecodeError) as err:
                raise UpdateFailed("Invalid JSON in WebSocket response") from err

            if not isinstance(msg, dict):
                raise UpdateFailed("WebSocket response is not a JSON object")
            if msg.get("resCode") != 200:
                raise UpdateFailed(
                    f"Device rejected cmd {payload['cmdNum']}: resCode={msg.get('resCode')}"
                )
            if "cmdNum" in msg and str(msg["cmdNum"]) != str(payload["cmdNum"]):
                raise UpdateFailed(
                    f"Unexpected response cmd {msg['cmdNum']} for cmd {payload['cmdNum']}"
                )
            return msg

    async def read(self, cmd_num: int, timeout: float = 2.0) -> Any:
        """Read a value, retrying once with a new WebSocket connection."""
        payload = {"cmdType": 0, "cmdNum": cmd_num}

        for attempt in range(1, _READ_ATTEMPTS + 1):
            try:
                msg = await self._request(payload, timeout)
                return _validate_read_data(cmd_num, msg.get("data"))
            except (OSError, asyncio.TimeoutError, WebSocketException, UpdateFailed) as err:
                detail = str(err) or type(err).__name__
                if attempt == _READ_ATTEMPTS:
                    raise UpdateFailed(
                        f"WebSocket read error cmd {cmd_num} after "
                        f"{_READ_ATTEMPTS} attempts: {detail}"
                    ) from err
                _LOGGER.debug(
                    "Read cmd %s failed (%s); retrying with a new connection",
                    cmd_num,
                    detail,
                )

        raise AssertionError("Read attempts exhausted without a result")

    async def set_value(self, cmd_num: int, value: Any, timeout: float = 2.0) -> None:
        if cmd_num == CMD_RGB:
            cmd_ctx = value
        else:
            cmd_ctx = {"value": value}

        payload = {"cmdType": 1, "cmdNum": cmd_num, "cmdCtx": cmd_ctx}

        # Do not replay writes: a missing acknowledgement can follow a successful set.
        try:
            await self._request(payload, timeout)
        except (OSError, asyncio.TimeoutError, WebSocketException, UpdateFailed) as err:
            detail = str(err) or type(err).__name__
            raise UpdateFailed(f"WebSocket set error cmd {cmd_num}: {detail}") from err


class GixieCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, client: GixieClient, entry_id: str) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="Gixie",
            update_interval=POLL_INTERVAL,
        )
        self._client = client
        self.entry_id = entry_id

        self.dst_mode: str = DST_AUTO
        self.base_tz_offset: int | None = None
        self._last_tz_index_applied: int | None = None

    async def async_setup(self) -> None:
        from homeassistant.helpers.event import async_track_time_interval

        async def _auto_dst_tick(_now):
            if self.dst_mode == DST_AUTO:
                await self.async_apply_timezone(reason="auto_dst_tick")

        async_track_time_interval(self.hass, _auto_dst_tick, AUTO_DST_INTERVAL)

    def _push_update(self, **changes: Any) -> None:
        data = dict(self.data or {})
        data.update(changes)
        self.async_set_updated_data(data)

    def _compute_effective_offset(self) -> int | None:
        if self.base_tz_offset is None and self.data and "tz_index" in self.data:
            self.base_tz_offset = index_to_offset(int(self.data["tz_index"]))

        if self.dst_mode == DST_AUTO:
            return clamp_offset(_system_utc_offset_hours())

        if self.base_tz_offset is None:
            return None

        if self.dst_mode == DST_ON:
            return clamp_offset(self.base_tz_offset + 1)

        return clamp_offset(self.base_tz_offset)

    async def async_apply_timezone(self, reason: str = "") -> None:
        eff = self._compute_effective_offset()
        if eff is None:
            return

        tz_index = offset_to_index(eff)

        if self._last_tz_index_applied is not None and self._last_tz_index_applied == tz_index:
            return

        await self._client.set_value(CMD_TIMEZONE, tz_index)
        read_index = await self._client.read(CMD_TIMEZONE)
        if read_index is None:
            read_index = tz_index

        self._last_tz_index_applied = int(read_index)

        eff_offset = index_to_offset(int(read_index))
        if self.dst_mode == DST_ON:
            self.base_tz_offset = clamp_offset(eff_offset - 1)
        else:
            self.base_tz_offset = clamp_offset(eff_offset)

        self._push_update(
            tz_index=read_index,
            base_tz_offset=self.base_tz_offset,
            dst_mode=self.dst_mode,
        )

    async def async_set_base_timezone(self, base_offset: int) -> None:
        self.base_tz_offset = clamp_offset(base_offset)
        await self.async_apply_timezone(reason="set_base_timezone")

    async def async_set_dst_mode(self, mode: str) -> None:
        self.dst_mode = mode
        await self.async_apply_timezone(reason="set_dst_mode")

    async def async_set_power(self, on: bool) -> None:
        await self._client.set_value(CMD_POWER, 1 if on else 0)
        power = await self._client.read(CMD_POWER)
        self._push_update(power=power)

    async def async_set_brightness(self, brightness: int) -> None:
        await self._client.set_value(CMD_BRIGHTNESS, int(brightness))
        b = await self._client.read(CMD_BRIGHTNESS)
        self._push_update(brightness=b)

    async def async_set_mode(self, mode_value: int) -> None:
        await self._client.set_value(CMD_MODE, int(mode_value))
        m = await self._client.read(CMD_MODE)
        self._push_update(mode=m)

    async def async_set_time_format(self, value: int) -> None:
        # 0 = 12h, 1 = 24h  (FIXED)
        await self._client.set_value(CMD_TIME_FORMAT, int(value))
        tf = await self._client.read(CMD_TIME_FORMAT)
        self._push_update(time_format=tf)

    async def async_set_rgb(self, r: int, g: int, b: int) -> None:
        rgb_list = [{"red": r, "green": g, "blue": b}] * 4
        await self._client.set_value(CMD_RGB, rgb_list)
        rgb = await self._client.read(CMD_RGB)
        self._push_update(rgb=rgb)

    async def _async_update_data(self) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        failures: dict[int, str] = {}
        for cmd in READ_CMDS:
            try:
                updates[_COMMAND_KEYS[cmd]] = await self._client.read(cmd)
            except UpdateFailed as err:
                failures[cmd] = str(err)

        # Cached values must not hide a complete loss of communication.
        if not updates:
            details = "; ".join(f"cmd {cmd}: {error}" for cmd, error in failures.items())
            raise UpdateFailed(f"No Gixie values could be read: {details}")

        # Copy after polling so a successful write during the poll is also retained
        # for any command whose read failed. Never mutate the previous snapshot.
        data = dict(self.data or {})
        data.update(updates)

        if "tz_index" in updates:
            tz_index = updates["tz_index"]
            eff_offset = index_to_offset(tz_index)
            if self.dst_mode == DST_ON:
                self.base_tz_offset = clamp_offset(eff_offset - 1)
            else:
                self.base_tz_offset = clamp_offset(eff_offset)

            # Do not treat initial read as self-applied write.
            if self._last_tz_index_applied is None:
                self._last_tz_index_applied = tz_index

        data.update(base_tz_offset=self.base_tz_offset, dst_mode=self.dst_mode)
        if failures:
            _LOGGER.debug(
                "Partial Gixie update; retaining previous values for failed commands: %s",
                failures,
            )
        return data
