# HydraPurr (touch-wire version): guide for testers

This folder is the firmware of the current HydraPurr test device. This page
is for whoever runs the device: how to set it up, what the screen means, and
how to get the data. Development notes are in [HANDOFF.md](../HANDOFF.md).

## What the device does

The device **records**; it does not feed and it does not decide anything. A
thin wire in the water bowl senses touches: a tongue (or a finger) in the
water makes the reading jump. A float next to the bowl, read by an infrared
distance sensor, gives the water level. The board samples both 100 times a
second and writes everything to its SD card. Licks are picked out later,
from the data.

The board joins the WiFi and serves the SD card as a web page, so you can
download data while it keeps recording. It also reports to an online health
check every 15 minutes; if it stops reporting, or something goes wrong,
Dieter gets an alert.

## Setting up

1. **Water first**, then power. Fill the bowl so the wire is covered. A full
   bowl reads about 1.16 V on the screen, an empty one about 0.62 V.
2. **Power:** a USB cable into the board, from a USB power adapter or a
   computer. It needs USB power: the water-level sensor runs on it.
3. **Don't touch the bowl or the water for the first ~10 s** after power-on or
   a reset: the board measures the untouched level then.
4. **Your WiFi network:** plug the board into a computer with a USB cable. It
   shows up as a drive called `CIRCUITPY`. Open the file `settings.toml` on
   that drive in a text editor and add your network under the ones already
   there, numbered on:

   ```toml
   WIFI_SSID_2 = "your network name"
   WIFI_PASSWORD_2 = "your password"
   ```

   Up to 5 networks (`_2` … `_5`). At start-up the board uses the first
   listed network that is in range. Save the file, then press **Reset** on
   the board (saving alone doesn't restart it). Keep this file private: it
   holds the passwords. Don't change any other file on that drive.

The board can stay plugged into the computer while it records. Unplugging it
at any time is fine: at most the last 5 seconds of data are lost.

## The screen

While starting (a few seconds):

| line | meaning |
| --- | --- |
| `SD ok` / `NO SD CARD` (red) | the SD card; without it nothing is recorded |
| date and time `UTC` (green) / `RTC: set time!` (red) | the clock; it is set from the internet once WiFi works |
| `joining WiFi...` → an address like `192.168.x.x` (green) / `no WiFi` (red) | the network. Note the address: you need it if the web page doesn't open (below) |

While recording:

| line | meaning |
| --- | --- |
| `REC 123456` (green) | recording; the number is rows written since start-up |
| `NOT RECORDING` (red) | the SD card failed: press Reset; if it stays, tell Dieter |
| `NOT REC: download` (red) | a "fast" download is running and recording is paused (see below) |
| `contacts 12` | touches counted since start-up (water, bowl, cat: all of them) |
| `water 1.160V` | water level: higher = fuller |
| `touch 37900` | the touch reading now (green while touched) |
| `base 37850` | the untouched level the board compares with |
| WiFi icon, top right | green = connected; grey with a red slash = not connected (it keeps recording and retries every 5 min) |

The screen **freezes while something touches the water** and catches up a
few seconds later: redrawing would interrupt the recording.

## Getting the data

On a computer or phone **on the same WiFi as the board**, open
**http://hydrapurr.local/** in a browser. If that page doesn't open:

- Switch off any VPN.
- Use the address the screen showed at start-up instead, e.g.
  `http://192.168.1.50/` (it can change between start-ups).
- Some networks (many university and guest networks) block this kind of
  local access; then the data has to come from the SD card or via Dieter.

The page shows the board's status and one row per day:

- **events**: a small file (opens in Excel) with one row per touch (written
  when it ends: time, duration, peak), a status row every 15 minutes (water level, touch
  level), and restarts. This is the one to look at first.
- **raw**: every sample, 100 per second. A full day is about 300 MB and
  takes about 35 minutes to download; for analysis in Python.
- **raw, fast (stops recording)**: about 3 times faster, but **nothing is
  recorded until it has finished**. Don't use it while a cat may drink.
  Recording restarts by itself when the download ends or breaks off.

Times in the files and day names are in **UTC** (US Eastern winter time is
UTC − 5 h). The board serves one download at a time: a second browser tab
waits until the first is done.

For Python: see [`analysis/readme.md`](../analysis/readme.md).
`plot_hydrapurr_day.py` fetches new data from the board and plots a day.

## Notes that help the analysis

Write down (with the time) anything that isn't a cat drinking: refilling,
cleaning, moving the device, touching the water or the bowl, people or other
animals at the bowl. Touching the outside of the bowl also registers (weaker
than touching the water), so these notes matter. A phone video of a drinking
session, with the time visible, is very useful too.

## Don'ts

- Don't take the SD card out while the board has power.
- **Unplug the USB before (dis)connecting a sensor.** Plugging one in while the
  board runs can upset the SD card for minutes (nothing gets recorded then).
- Don't hold the **D2** button while the board starts (it runs a test
  program instead of recording); don't press **D0/BOOT** together with Reset.
- Don't use "raw, fast" during an experiment.
- Don't edit files on the `CIRCUITPY` drive other than `settings.toml`.

## If something is wrong

| what you see | what to do |
| --- | --- |
| screen dark | check the USB cable and power; press Reset |
| `NO SD CARD` or `NOT RECORDING` | unplug, check that the card sits in its slot, plug in again |
| `no WiFi` / grey WiFi icon | check the name and password in `settings.toml`, then Reset. It records anyway |
| `contacts` climbs with nobody there | note the time and tell Dieter |
| the web page doesn't open | see "Getting the data" above |

**Reset** = the small button on the board; it restarts the recording (a few
seconds' gap). Anything else: contact Dieter.
