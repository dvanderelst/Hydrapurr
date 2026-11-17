"""
EventLog.py - one row per significant event, next to the raw stream

The raw stream (RawRecorder) holds every sample; this file holds only what
happened, and is the file meant for analysis (and later for upload). Rows are
only written when there is something to log, except `water`, which is a
summary over a fixed interval.

One file per day of wall-clock time:
    /sd/events/2026-10-30.csv
Columns:
    epoch_ms, mono_ms, event, f1, f2, f3, f4
epoch_ms/mono_ms are as in RawRecorder. The meaning of f1..f4 depends on the
event (empty = not used):

    event       f1               f2                 f3              f4
    boot        reset_reason     safe_mode_reason   rtc_ok (0/1)    touch_baseline
    settings    name             value
    contact     duration_ms      peak_touch_raw     touch_baseline  water_v
    rebaseline  reason           touch_raw          old_baseline    new_baseline
    water       mean_v           min_v              max_v           samples
    shutdown    reason
    wifi        joined/join_failed/lost   ip    rssi       (MainLoop, 2026-11-16)
    heartbeat_failed  status      ms_taken                 (MainLoop, 2026-11-16)
    clock       ntp / ntp_failed   step_ms   rtt_ms   server   (RTC set from NTP)
    paused      download         path                       (fast download, FileServer)
    resumed     reason           paused_ms                  (done / timeout / max_pause / ...)

- boot is written once the sensors are set up; one settings row per setting
  follows it (same values as the snapshot in system.log).
- contact is written when the contact ends, so the row's time is the end;
  the start is epoch_ms - duration_ms. touch_baseline and water_v are the
  values just before the contact started. Every contact is logged: deciding
  which contacts are licks (min_lick_ms..max_lick_ms) is left to the analysis.
- rebaseline: the touch baseline was reset at once instead of tracked.
  reason `stuck` = contact held longer than touch_stuck_ms (a contact row
  with that duration follows); `drop` = raw fell far below the baseline.
- water summarises the single Sharp reads over water_event_interval_ms.
- shutdown is the reason the loop ended: an exception, or e.g.
  KeyboardInterrupt (Ctrl-C) / ReloadException (auto-reload on file save).

Rows are written at once (~1 ms) but flushed only every events_sync_ms: a
flush takes ~10 ms, too long to do after every contact while a cat drinks.
"""

import os
import time
import Settings
from components import MySD
from components.MySystemLog import info, warn
from RawRecorder import wall_seconds, epoch_offset_ms

HEADER = "epoch_ms,mono_ms,event,f1,f2,f3,f4"
ROOT = "/sd/events"


def _mkdir(path):
    try:
        os.mkdir(path)
    except OSError:
        pass                    # exists


def _field(value):
    """CSV field: floats with 4 decimals, quoted when it holds a comma or quote."""
    if value is None:
        return ''
    if isinstance(value, float):
        return f"{value:.4f}"
    text = str(value)
    if ',' in text or '"' in text or '\n' in text:
        text = '"' + text.replace('"', '""').replace('\n', ' ') + '"'
    return text


class EventLog:
    def __init__(self):
        self.enabled = Settings.events_enabled and MySD.is_mounted()
        self.sync_ms = Settings.events_sync_ms
        self.file = None
        self.path = None
        self.day_key = None
        self.errors = 0
        self._dirty = False
        self._next_sync_ms = 0
        if self.enabled:
            _mkdir(ROOT)
            info(f'[Events] logging to {ROOT}/<date>.csv')
        elif Settings.events_enabled:
            warn('[Events] SD not mounted; event log off')

    def _open_for(self, t_ms):
        """Open (or continue) the file for the day that contains t_ms."""
        t = time.localtime(wall_seconds(t_ms))
        key = (t.tm_year, t.tm_mon, t.tm_mday)
        if key == self.day_key and self.file is not None:
            return
        self.close()
        self.path = f"{ROOT}/{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}.csv"
        new_file = True
        try:
            new_file = os.stat(self.path)[6] == 0
        except OSError:
            pass
        self.file = open(self.path, "a")
        if new_file:
            self.file.write(HEADER + "\n")
        self.day_key = key
        info(f'[Events] writing {self.path}')

    def log(self, t_ms, event, *fields):
        """Write one event row (up to four fields)."""
        if not self.enabled:
            return
        try:
            self._open_for(t_ms)
            cells = [_field(f) for f in fields] + [''] * (4 - len(fields))
            self.file.write(f"{t_ms + epoch_offset_ms()},{t_ms},{event},{','.join(cells)}\n")
            self._dirty = True
        except OSError as e:
            self.errors += 1
            warn(f'[Events] write failed: {e!r}')
            self.close()

    def update(self, t_ms):
        """Call every loop pass: flushes pending rows every events_sync_ms."""
        if self._dirty and t_ms >= self._next_sync_ms:
            self._next_sync_ms = t_ms + self.sync_ms
            self.flush()

    def flush(self):
        if self.file is not None:
            try:
                self.file.flush()
            except OSError:
                pass
        self._dirty = False

    def close(self):
        if self.file is not None:
            try:
                self.file.close()
            except OSError:
                pass
        self.file = None
        self.day_key = None
        self._dirty = False
