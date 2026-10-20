"""
TouchSensor.py - lick contact from a single wire in the water (touchio)

The wire, the water and the bowl form one electrode. A tongue in the water
adds the cat's body to it, and touchio's raw_value jumps up. This class turns
raw values into a 0/1 contact state for BoutDetection:

- baseline: averaged at boot, then tracked slowly (exponential moving
  average) while there is no contact, so it follows drift from water level,
  humidity and the surroundings but not the licks themselves.
- contact on/off thresholds relative to the baseline, with hysteresis.
- a contact that lasts longer than touch_stuck_ms is not a lick; the
  baseline is re-taken from the current level so a level step or a resting
  paw cannot hold the state at 1 forever. A large drop below the baseline
  is followed at once, so it recovers when the paw is lifted.
"""

import time
import touchio
import Settings
from components.MySystemLog import info, warn


def now_ms():
    return int(time.monotonic() * 1000)


class TouchSensor:
    def __init__(self, pin=None):
        self.touch = touchio.TouchIn(pin if pin is not None else Settings.touch_pin)
        self.on_fraction = Settings.touch_on_fraction
        self.off_fraction = Settings.touch_off_fraction
        self.tau_ms = Settings.touch_baseline_tau_ms
        self.stuck_ms = Settings.touch_stuck_ms

        self.raw = 0
        self.contact = 0
        self.contact_since = None
        self._last_ms = None
        self.baseline = self.measure_baseline(Settings.touch_baseline_samples)
        info(f'[Touch] baseline {self.baseline:.0f} at boot')
        if self.baseline <= 0:
            warn('[Touch] baseline is 0: touchio is not measuring '
                 '(CircuitPython 10.3.0 bug, needs 10.3.1+)')

    def measure_baseline(self, n):
        total = 0
        for _ in range(n):
            total += self.touch.raw_value
            time.sleep(0.005)
        return total / n

    def on_level(self):
        return self.baseline * (1 + self.on_fraction)

    def off_level(self):
        return self.baseline * (1 + self.off_fraction)

    def update(self, t_ms=None):
        """Read the pin once and return the contact state (0 or 1)."""
        t_ms = now_ms() if t_ms is None else t_ms
        raw = self.touch.raw_value
        self.raw = raw

        if self.contact:
            if raw < self.off_level():
                self.contact = 0
                self.contact_since = None
            elif t_ms - self.contact_since > self.stuck_ms:
                info(f'[Touch] contact held > {self.stuck_ms} ms '
                     f'(raw {raw}, baseline {self.baseline:.0f}): re-taking baseline')
                self.baseline = raw
                self.contact = 0
                self.contact_since = None
        else:
            if raw > self.on_level():
                self.contact = 1
                self.contact_since = t_ms
            elif raw < self.baseline * (1 - self.on_fraction):
                # Big drop (e.g. after a re-baseline during a long contact):
                # follow it at once instead of over tau_ms.
                self.baseline = raw
            elif self._last_ms is not None:
                # Track slow drift only while untouched.
                dt = t_ms - self._last_ms
                alpha = dt / (self.tau_ms + dt)
                self.baseline += alpha * (raw - self.baseline)
        self._last_ms = t_ms
        return self.contact
