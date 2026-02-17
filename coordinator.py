from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import websockets
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
    DST_OFF,
    DST_ON,
    POLL_INTERVAL,
    READ_CMDS,
)


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

    async def _connect(self):
        return await websockets.connect(self.uri)

    async def read(self, cmd_num: int, timeout: float = 2.0) -> Any:
        payload = {"cmdType": 0, "cmdNum": cmd_num}

        try:
            async with await self._connect() as ws:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=0.5)
                except Exception:
                    pass

                await ws.send(__import__("json").dumps(payload))
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg = __import__("json").loads(raw)

                if msg.get("resCode") != 200:
                    raise UpdateFailed(f"Read failed cmd {cmd_num}: {msg}")

                return msg.get("data")
        except Exception as e:
            raise UpdateFailed(f"WebSocket read error cmd {cmd_num}: {e}") from e

    async def set_value(self, cmd_num: int, value: Any, timeout: float = 2.0) -> None:
        if cmd_num == CMD_RGB:
            cmd_ctx = value
        else:
            cmd_ctx = {"value": value}

        payload = {"cmdType": 1, "cmdNum": cmd_num, "cmdCtx": cmd_ctx}

        try:
            async with await self._connect() as ws:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=0.5)
                except Exception:
                    pass

                await ws.send(__import__("json").dumps(payload))
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg = __import__("json").loads(raw)

                if msg.get("resCode") != 200:
                    raise UpdateFailed(f"Set failed cmd {cmd_num}: {msg}")
        except Exception as e:
            raise UpdateFailed(f"WebSocket set error cmd {cmd_num}: {e}") from e


class GixieCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, client: GixieClient, entry_id: str) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
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
        try:
            results: dict[str, Any] = {}
            for cmd in READ_CMDS:
                results[cmd] = await self._client.read(cmd)

            rgb = results.get(CMD_RGB)
            brightness = results.get(CMD_BRIGHTNESS)
            power = results.get(CMD_POWER)
            tz_index = results.get(CMD_TIMEZONE)
            mode = results.get(CMD_MODE)
            time_format = results.get(CMD_TIME_FORMAT)

            if tz_index is not None:
                eff_offset = index_to_offset(int(tz_index))

                if self.dst_mode == DST_ON:
                    self.base_tz_offset = clamp_offset(eff_offset - 1)
                else:
                    self.base_tz_offset = clamp_offset(eff_offset)

                # Do not treat initial read as self-applied write
                if self._last_tz_index_applied is None:
                    self._last_tz_index_applied = int(tz_index)

            return {
                "rgb": rgb,
                "brightness": brightness,
                "power": power,
                "tz_index": tz_index,
                "base_tz_offset": self.base_tz_offset,
                "mode": mode,
                "time_format": time_format,
                "dst_mode": self.dst_mode,
            }

        except Exception as e:
            raise UpdateFailed(str(e)) from e
