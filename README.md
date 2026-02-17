# Gixie Clock Mini -- Home Assistant Integration
![Logo](logo.png)
<img src="logo.png" alt="Projektlogo" width="150"/>

Custom integration for controlling the Gixie Clock Mini (AliExpress
variant) via WebSocket from Home Assistant.

This integration was reverse-engineered from the official mobile app
using network analysis and implements the complete read/write API of the
clock.

------------------------------------------------------------------------

## Features

-   Full local control (no cloud required)
-   Config Flow (IP-based setup)
-   RGB control
-   Brightness control
-   Power control
-   Clock mode selection
-   12h / 24h format selection
-   Timezone management (-12 ... +12)
-   DST modes: off / on / auto
-   Hourly automatic DST sync (auto mode)
-   Polling every 30 seconds (detects app changes)
-   Immediate UI updates after writes (read-after-write)

------------------------------------------------------------------------

# Installation

## Option 1 -- HACS (Recommended)

1.  Open HACS in Home Assistant
2.  Go to **Integrations**
3.  Click the three dots (top right) → **Custom repositories**
4.  Add this repository URL
5.  Select category: **Integration**
6.  Click **Add**
7.  Search for **Gixie Clock Mini**
8.  Click **Install**
9.  Restart Home Assistant

After restart:

-   Go to **Settings → Devices & Services**
-   Click **Add Integration**
-   Select **Gixie Clock Mini**
-   Enter the IP address of your clock

------------------------------------------------------------------------

## Option 2 -- Manual Installation

1.  Copy the folder:

    custom_components/gixie/

    into your Home Assistant config directory:

    config/custom_components/

2.  Restart Home Assistant

3.  Go to:

    Settings → Devices & Services → Add Integration → Gixie Clock Mini

4.  Enter the IP address of your clock

------------------------------------------------------------------------

## Entities

### light.gixie_clock

-   RGB control
-   Brightness
-   Power

Uses: - cmd 9 (RGB) - cmd 14 (Brightness) - cmd 15 (Power)

------------------------------------------------------------------------

### switch.gixie_power

Power On/Off\
Uses cmd 15

------------------------------------------------------------------------

### select.gixie_mode

  Value   Mode
  ------- -----------------------
  0       clock fixed color
  1       clock overall rainbow
  2       clock single rainbow
  3       number flash
  4       wordline
  5       custom number
  6       zero one random
  7       fan count

Uses cmd 211

------------------------------------------------------------------------

### select.gixie_time_format

  Option   Device Value
  -------- --------------
  12h      0
  24h      1

Uses cmd 213

------------------------------------------------------------------------

### number.gixie_base_timezone

User-visible offset range:

-12 ... +12

Internally converted to:

tz_index = offset + 12

Example:

  Offset   Device Index
  -------- --------------
  UTC+1    13
  UTC+2    14

Uses cmd 16

------------------------------------------------------------------------

### select.gixie_dst

Options: - off - on - auto

Behavior:

  Mode   Effect
  ------ ------------------------
  off    uses base timezone
  on     base timezone + 1 hour
  auto   system UTC offset

When auto is active: - Base timezone editing is logically disabled -
Attribute: controlled_by = system timezone (DST auto)

------------------------------------------------------------------------

## Timezone Logic

effective_offset = - base_offset (DST off) - base_offset + 1 (DST on) -
system_utc_offset() (DST auto)

tz_index = effective_offset + 12

Range is clamped to -12 ... +12.

------------------------------------------------------------------------

## Protocol Reference

### Read

{"cmdType":0,"cmdNum":X}

### Write

{"cmdType":1,"cmdNum":X,"cmdCtx":{"value":Y}}

### RGB Write

{ "cmdType":1, "cmdNum":9, "cmdCtx":\[ {"red":r,"green":g,"blue":b},
{"red":r,"green":g,"blue":b}, {"red":r,"green":g,"blue":b},
{"red":r,"green":g,"blue":b} \] }

------------------------------------------------------------------------

## Confirmed Command Map

  cmdNum   Function
  -------- ------------
  9        RGB
  14       Brightness
  15       Power
  16       Timezone
  211      Mode
  213      12h / 24h

------------------------------------------------------------------------

## Design Decisions

-   Connect-per-operation WebSocket model
-   No permanent socket
-   Clock is source of truth at startup
-   Read-after-write consistency
-   Fully local communication

------------------------------------------------------------------------

## License

MIT (recommended) or adapt to your needs.
