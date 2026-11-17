"""
WaterSensor.py - water level from a Sharp IR sensor above a float

The float sits in a chimney connected to the bowl; the Sharp GP2Y0A51SK0F
looks down at its flat top. Output voltage rises as the float comes closer,
so a higher value means more water. Values stay in volts (no calibration to
millilitres yet), like the water column in BoardCode's licks.dat.

The recorder (MainLoop) takes one read_volts() per sample and stores it as
is. update()/level are for the bout version: the sensor produces a new
reading every ~16.5 ms, so there it is sampled on a timer (water_sample_ms)
and smoothed with a moving average. One ADC read takes ~1.3 ms on the
ESP32-S3.
"""

import time
import analogio
import Settings


def now_ms():
    return time.monotonic_ns() // 1_000_000


class WaterSensor:
    def __init__(self, pin=None):
        self.adc = analogio.AnalogIn(pin if pin is not None else Settings.water_pin)
        self.scale = self.adc.reference_voltage / 65535
        self.interval_ms = Settings.water_sample_ms
        self.window = [self.read_volts()] * max(1, Settings.water_smooth_samples)
        self.index = 0
        self.level = self.window[0]     # smoothed volts
        self.last_raw = self.level      # latest single reading, volts
        self._next_ms = now_ms()

    def read_volts(self):
        return self.adc.value * self.scale

    def update(self, t_ms=None):
        """Take a sample if one is due. Returns True when a sample was taken."""
        t_ms = now_ms() if t_ms is None else t_ms
        if t_ms < self._next_ms:
            return False
        self._next_ms = t_ms + self.interval_ms
        v = self.read_volts()
        self.last_raw = v
        self.window[self.index] = v
        self.index = (self.index + 1) % len(self.window)
        self.level = sum(self.window) / len(self.window)
        return True
