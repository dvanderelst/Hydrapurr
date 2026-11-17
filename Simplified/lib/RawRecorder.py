"""
RawRecorder.py - continuous raw sensor stream to the SD card

One row per sample (MainLoop samples every raw_log_interval_ms):
    epoch_ms, mono_ms, touch_raw, touch_baseline, contact, water_v

epoch_ms is wall-clock time (ms since 1970-01-01, RTC local time), computed
as RTC-at-boot + time since boot. It holds no more information than mono_ms
plus the anchor below, but it stays correct when a restart appends to the
same file and mono_ms starts again from ~0.

Files are split per hour of wall-clock time, one folder per day:
    /sd/raw/2026-10-20/13.csv
Each file (and each re-open after a restart) gets a comment line holding the
wall-clock time that belongs to a given mono_ms (human-readable check):
    # start 2026-10-20 13:00:00.004 mono_ms 3600123

Writing, chosen from timings measured on this board and card:
- Each row is written as soon as it is taken (median 0.9 ms, max ~10 ms).
  The filesystem collects rows in a 512-byte sector and only touches the card
  when a sector fills (~every 17 rows).
- flush() (directory entry update, ~10 ms) runs every raw_log_sync_ms. A
  power cut loses at most that much data.
- Writing 100-row batches instead blocked for 25-80 ms at a time, long enough
  to swallow a whole lick, so batching was dropped.
- The file stays open: re-opening a file to append gets slower as it grows
  (FAT walks the cluster chain). Hourly files stay ~16 MB at 100 rows/s, far
  below FAT32's 4 GB limit.
"""

import os
import time
import Settings
from components import MySD
from components import TimeUtil
from components.MySystemLog import info, warn

HEADER = "epoch_ms,mono_ms,touch_raw,touch_baseline,contact,water_v"
ROOT = "/sd/raw"
HOUR_CHECK_MS = 1000           # how often to check for a new wall-clock hour


def _mkdir(path):
    try:
        os.mkdir(path)
    except OSError:
        pass                    # exists


def wall_seconds(mono_ms):
    """Wall-clock seconds (epoch) for a monotonic ms value, via TimeUtil."""
    if not TimeUtil.timebase_ready:
        TimeUtil.init_timebase()
    return TimeUtil.boot_epoch + (mono_ms - TimeUtil.boot_mono_ms) // 1000


def epoch_offset_ms():
    """Add to a monotonic ms value to get wall-clock epoch ms."""
    if not TimeUtil.timebase_ready:
        TimeUtil.init_timebase()
    return TimeUtil.boot_epoch * 1000 - TimeUtil.boot_mono_ms


class RawRecorder:
    def __init__(self):
        self.enabled = Settings.raw_log_enabled and MySD.is_mounted()
        self.sync_ms = Settings.raw_log_sync_ms
        self.file = None
        self.path = None
        self.hour_key = None
        self.epoch_offset_ms = None
        self.rows_written = 0      # since boot
        self.errors = 0
        self.slowest_ms = 0        # slowest write/flush/rollover since last read
        self._next_sync_ms = 0
        self._next_hour_check_ms = 0
        if self.enabled:
            _mkdir(ROOT)
            info(f'[Raw] recording to {ROOT}/<date>/<hour>.csv')
        elif Settings.raw_log_enabled:
            warn('[Raw] SD not mounted; raw recording off')

    def _open_for(self, t_ms):
        """Open (or continue) the file for the hour that contains t_ms."""
        t = time.localtime(wall_seconds(t_ms))
        key = (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour)
        if key == self.hour_key and self.file is not None:
            return
        self.close()
        self.epoch_offset_ms = epoch_offset_ms()
        day_dir = f"{ROOT}/{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
        _mkdir(day_dir)
        self.path = f"{day_dir}/{t.tm_hour:02d}.csv"
        new_file = True
        try:
            new_file = os.stat(self.path)[6] == 0
        except OSError:
            pass
        self.file = open(self.path, "a")
        ts = TimeUtil._wall_time_from_mono(t_ms, 'iso', True)
        self.file.write(f"# start {ts} mono_ms {t_ms}\n")
        if new_file:
            self.file.write(HEADER + "\n")
        self.hour_key = key
        info(f'[Raw] writing {self.path}')

    def add(self, t_ms, touch, water_v):
        """Write one row."""
        if not self.enabled:
            return
        start = time.monotonic_ns()
        try:
            if self.file is None or t_ms >= self._next_hour_check_ms:
                self._next_hour_check_ms = t_ms + HOUR_CHECK_MS
                self._open_for(t_ms)
            self.file.write(f"{t_ms + self.epoch_offset_ms},{t_ms},{touch.raw},{touch.baseline:.0f},"
                            f"{touch.contact},{water_v:.4f}\n")
            self.rows_written += 1
            if t_ms >= self._next_sync_ms:
                self._next_sync_ms = t_ms + self.sync_ms
                self.file.flush()
        except OSError as e:
            self.errors += 1
            warn(f'[Raw] write failed: {e!r}')
            self.close()
        took = (time.monotonic_ns() - start) // 1_000_000
        if took > self.slowest_ms:
            self.slowest_ms = took

    def retime(self):
        """The clock was re-set (NTP): use the new offset from now on, and
        check at the next row whether that changes the hourly file."""
        self.epoch_offset_ms = epoch_offset_ms()
        self._next_hour_check_ms = 0

    def take_slowest_ms(self):
        """Slowest single add() since the last call, then reset."""
        slowest, self.slowest_ms = self.slowest_ms, 0
        return slowest

    def flush(self):
        if self.file is not None:
            try:
                self.file.flush()
            except OSError:
                pass

    def close(self):
        if self.file is not None:
            try:
                self.file.close()
            except OSError:
                pass
        self.file = None
        self.hour_key = None
