"""Regression tests for transient Gixie failures and retained coordinator state."""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
import pytest_asyncio
import websockets
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from websockets.exceptions import ConnectionClosedError

from custom_components.gixie.const import (
    CMD_BRIGHTNESS,
    CMD_MODE,
    CMD_POWER,
    CMD_RGB,
    CMD_TIME_FORMAT,
    CMD_TIMEZONE,
    DST_ON,
    READ_CMDS,
)
from custom_components.gixie.coordinator import (
    GixieClient,
    GixieCoordinator,
    GixieSettings,
)
from custom_components.gixie.light import GixieClockLight
from custom_components.gixie.switch import GixiePowerSwitch

pytestmark = pytest.mark.asyncio

RGB = [{"red": 10, "green": 20, "blue": 30}] * 4
VALUES = {
    CMD_RGB: RGB,
    CMD_BRIGHTNESS: 80,
    CMD_POWER: 1,
    CMD_TIMEZONE: 14,
    CMD_MODE: 2,
    CMD_TIME_FORMAT: 1,
}
KEYS = {
    CMD_RGB: "rgb",
    CMD_BRIGHTNESS: "brightness",
    CMD_POWER: "power",
    CMD_TIMEZONE: "tz_index",
    CMD_MODE: "mode",
    CMD_TIME_FORMAT: "time_format",
}


def response(value):
    return json.dumps({"resCode": 200, "data": value})


def connection(*replies):
    """A connection context manager, distinct from its non-awaitable socket."""
    ws = SimpleNamespace(recv=AsyncMock(side_effect=replies), send=AsyncMock())
    context = AsyncMock()
    context.__aenter__.return_value = ws
    return context, ws


@pytest.fixture
def client():
    return GixieClient(GixieSettings("clock.test"))


@pytest_asyncio.fixture
async def coordinator(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    device = Mock(spec=GixieClient)
    device.read = AsyncMock(side_effect=lambda cmd: VALUES[cmd])
    result = GixieCoordinator(hass, device, "test-entry")
    try:
        yield result
    finally:
        await hass.async_stop()


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " \t\n",
        b"",
        b"\xff",
        "{",
        "[]",
        "null",
        '{"resCode": 500}',
        '{"resCode": 200}',
        '{"resCode": 200, "data": null}',
        '{"resCode": 200, "data": "invalid"}',
        '{"resCode": 200, "data": {}}',
        '{"resCode": 200, "data": 1.5}',
        '{"resCode": 200, "cmdNum": 211, "data": 3}',
        asyncio.TimeoutError(),
        ConnectionClosedError(None, None),
    ],
)
async def test_read_retries_once_on_fresh_connection(client, monkeypatch, raw):
    first, first_ws = connection("ready", raw)
    second, second_ws = connection("ready", response(77))
    connect = Mock(side_effect=[first, second])
    monkeypatch.setattr(websockets, "connect", connect)

    assert await client.read(CMD_BRIGHTNESS) == 77
    assert connect.call_count == 2
    first.__aexit__.assert_awaited_once()
    second.__aexit__.assert_awaited_once()
    expected = {"cmdType": 0, "cmdNum": CMD_BRIGHTNESS}
    assert json.loads(first_ws.send.await_args.args[0]) == expected
    assert json.loads(second_ws.send.await_args.args[0]) == expected


@pytest.mark.parametrize("value", [[], {}, [None], [{}], [{"red": 1, "green": 2}], [
    {"red": 256, "green": 2, "blue": 3}
]])
async def test_invalid_rgb_is_retried(client, monkeypatch, value):
    first, _ = connection("ready", response(value))
    second, _ = connection("ready", response(RGB))
    monkeypatch.setattr(websockets, "connect", Mock(side_effect=[first, second]))
    assert await client.read(CMD_RGB) == RGB


@pytest.mark.parametrize("value", [0, "0"])
async def test_zero_is_valid_data(client, monkeypatch, value):
    context, _ = connection("ready", response(value).encode())
    connect = Mock(return_value=context)
    monkeypatch.setattr(websockets, "connect", connect)
    assert await client.read(CMD_POWER) == 0
    assert connect.call_count == 1


async def test_read_stops_after_two_failures(client, monkeypatch):
    first, _ = connection("ready", asyncio.TimeoutError())
    second, _ = connection("ready", asyncio.TimeoutError())
    connect = Mock(side_effect=[first, second])
    monkeypatch.setattr(websockets, "connect", connect)
    with pytest.raises(UpdateFailed, match="cmd 16 after 2 attempts: TimeoutError"):
        await client.read(CMD_TIMEZONE)
    assert connect.call_count == 2


async def test_connection_failure_is_retried(client, monkeypatch):
    context, _ = connection("ready", response(1))
    connect = Mock(side_effect=[ConnectionRefusedError(), context])
    monkeypatch.setattr(websockets, "connect", connect)
    assert await client.read(CMD_POWER) == 1
    assert connect.call_count == 2


async def test_missing_greeting_is_optional(client, monkeypatch):
    context, _ = connection(asyncio.TimeoutError(), response(1))
    connect = Mock(return_value=context)
    monkeypatch.setattr(websockets, "connect", connect)
    assert await client.read(CMD_POWER) == 1
    assert connect.call_count == 1


async def test_broken_greeting_connection_is_retried_before_send(client, monkeypatch):
    first, first_ws = connection(ConnectionClosedError(None, None))
    second, _ = connection("ready", response(1))
    monkeypatch.setattr(websockets, "connect", Mock(side_effect=[first, second]))
    assert await client.read(CMD_POWER) == 1
    first_ws.send.assert_not_awaited()


async def test_cancellation_propagates_without_retry(client, monkeypatch):
    context, _ = connection("ready", asyncio.CancelledError())
    connect = Mock(return_value=context)
    monkeypatch.setattr(websockets, "connect", connect)
    with pytest.raises(asyncio.CancelledError):
        await client.read(CMD_POWER)
    assert connect.call_count == 1
    context.__aexit__.assert_awaited_once()


async def test_write_is_not_replayed_on_bad_acknowledgement(client, monkeypatch):
    context, ws = connection("ready", "")
    connect = Mock(return_value=context)
    monkeypatch.setattr(websockets, "connect", connect)
    with pytest.raises(UpdateFailed, match="Empty WebSocket response"):
        await client.set_value(CMD_POWER, 1)
    assert connect.call_count == 1
    ws.send.assert_awaited_once()


@pytest.mark.parametrize("cmd,value", [(CMD_POWER, 0), (CMD_RGB, RGB)])
async def test_write_payload_and_ack_without_data(client, monkeypatch, cmd, value):
    context, ws = connection("ready", '{"resCode": 200}')
    monkeypatch.setattr(websockets, "connect", Mock(return_value=context))
    await client.set_value(cmd, value)
    assert json.loads(ws.send.await_args.args[0]) == {
        "cmdType": 1,
        "cmdNum": cmd,
        "cmdCtx": value if cmd == CMD_RGB else {"value": value},
    }


async def test_actual_websocket_reconnects_after_empty_response():
    """Exercise the real connect context manager and socket cleanup."""
    requests = []

    async def clock(ws):
        await ws.send("ready")
        requests.append(json.loads(await ws.recv()))
        await ws.send("" if len(requests) == 1 else response(14))

    async with websockets.serve(clock, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        device = GixieClient(GixieSettings("127.0.0.1", port))
        assert await device.read(CMD_TIMEZONE) == 14
    assert requests == [{"cmdType": 0, "cmdNum": CMD_TIMEZONE}] * 2


async def test_all_values_refresh(coordinator):
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    for cmd, value in VALUES.items():
        assert coordinator.data[KEYS[cmd]] == value
    assert coordinator.data["base_tz_offset"] == 2
    assert coordinator._client.read.await_args_list == [call(cmd) for cmd in READ_CMDS]


@pytest.mark.parametrize("failed_cmd", READ_CMDS)
async def test_single_failure_retains_value_and_refreshes_others(
    coordinator, failed_cmd, caplog
):
    await coordinator.async_refresh()
    previous = coordinator.data
    changed = dict(VALUES)
    changed.update({
        CMD_RGB: [{"red": 40, "green": 50, "blue": 60}] * 4,
        CMD_BRIGHTNESS: 23,
        CMD_POWER: 0,
        CMD_TIMEZONE: 13,
        CMD_MODE: 4,
        CMD_TIME_FORMAT: 0,
    })

    async def read(cmd):
        if cmd == failed_cmd:
            raise UpdateFailed("temporary failure")
        return changed[cmd]

    coordinator._client.read.reset_mock()
    coordinator._client.read.side_effect = read
    caplog.set_level(logging.WARNING)
    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data is not previous
    for cmd in READ_CMDS:
        key = KEYS[cmd]
        assert previous[key] == VALUES[cmd]
        assert coordinator.data[key] == (
            VALUES[cmd] if cmd == failed_cmd else changed[cmd]
        )
    assert coordinator.data["base_tz_offset"] == (
        2 if failed_cmd == CMD_TIMEZONE else 1
    )
    assert coordinator._client.read.await_args_list == [call(cmd) for cmd in READ_CMDS]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


async def test_partial_first_refresh_leaves_missing_power_unknown(coordinator):
    async def read(cmd):
        if cmd == CMD_POWER:
            raise UpdateFailed("power not read yet")
        return VALUES[cmd]

    coordinator._client.read.side_effect = read
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.last_update_success
    assert coordinator.data.get("power") is None
    assert GixieClockLight(coordinator, "test").is_on is None
    assert GixiePowerSwitch(coordinator, "test").is_on is None


async def test_total_failure_marks_unavailable_and_then_recovers(coordinator):
    await coordinator.async_refresh()
    previous = coordinator.data
    coordinator._client.read.side_effect = UpdateFailed("clock offline")
    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert coordinator.data is previous
    assert not GixiePowerSwitch(coordinator, "test").available
    assert "No Gixie values could be read" in str(coordinator.last_exception)

    async def read(cmd):
        if cmd != CMD_BRIGHTNESS:
            raise UpdateFailed("still unavailable")
        return 0

    coordinator._client.read.side_effect = read
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert GixiePowerSwitch(coordinator, "test").available
    assert coordinator.data["brightness"] == 0
    assert coordinator.data["rgb"] == RGB


async def test_total_first_failure_does_not_create_default_values(coordinator):
    coordinator._client.read.side_effect = UpdateFailed("clock offline")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.data is None
    assert coordinator._client.read.await_args_list == [call(cmd) for cmd in READ_CMDS]


async def test_dst_base_timezone_is_retained_when_timezone_read_fails(coordinator):
    coordinator.dst_mode = DST_ON
    await coordinator.async_refresh()
    assert coordinator.base_tz_offset == 1

    async def read(cmd):
        if cmd == CMD_TIMEZONE:
            raise UpdateFailed("timezone unavailable")
        return VALUES[cmd]

    coordinator._client.read.side_effect = read
    await coordinator.async_refresh()
    assert coordinator.data["tz_index"] == 14
    assert coordinator.data["base_tz_offset"] == 1
    assert coordinator.data["dst_mode"] == DST_ON
