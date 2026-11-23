"""
Button.py - edge-detecting push button (D0/D1/D2 on the Reverse TFT)

D1 on the Reverse TFT reads differently from D0 (D0 is pulled up, D1/D2
pulled down), so "pressed" means "different from the level at startup".
Used by TestHeartbeat.py (D1 sends a /fail ping).
"""

import time
import digitalio

DEBOUNCE_MS = 50


def now_ms():
    return time.monotonic_ns() // 1_000_000


class Button:
    """pressed() is True once per press."""

    def __init__(self, pin):
        self.io = digitalio.DigitalInOut(pin)
        self.io.switch_to_input(pull=digitalio.Pull.DOWN)
        time.sleep(0.01)
        self.idle = self.io.value
        self.down = False
        self.changed_ms = 0

    def pressed(self, t_ms=None):
        t_ms = now_ms() if t_ms is None else t_ms
        down = self.io.value != self.idle
        if down != self.down and t_ms - self.changed_ms >= DEBOUNCE_MS:
            self.down = down
            self.changed_ms = t_ms
            return down
        return False
