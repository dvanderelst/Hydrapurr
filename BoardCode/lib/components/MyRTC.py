import time, board
import busio
import adafruit_pcf8523
from components.MySystemLog import debug, info, warn, error
from components.MyI2C import common_i2c

#i2c_singleton = None

# def get_i2c():
#     global i2c_singleton
#     if i2c_singleton is None: i2c_singleton = busio.I2C(board.SCL, board.SDA)
#     return i2c_singleton

class MyRTC:
    def __init__(self):
        self.i2c = common_i2c
        self.rtc = adafruit_pcf8523.PCF8523(self.i2c)
    # ---- reads ----
    def now(self):
        return self.rtc.datetime  # time.struct_time

    def datestr(self):
        t = self.now()
        days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        return f"{days[t.tm_wday]} {t.tm_mday}/{t.tm_mon}/{t.tm_year}"

    def timestr(self, with_seconds=True):
        t = self.now()
        return f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}" if with_seconds else f"{t.tm_hour:02d}:{t.tm_min:02d}"

    def dtstr(self, with_seconds=True):
        return f"{self.datestr()} {self.timestr(with_seconds)}"

    def get_time(self, as_string=False, with_seconds=True):
        if as_string: return self.dtstr(with_seconds)
        t = self.now()
        return {
            "year": t.tm_year,
            "month": t.tm_mon,
            "day": t.tm_mday,
            "hour": t.tm_hour,
            "minute": t.tm_min,
            "second": t.tm_sec,
            "weekday": t.tm_wday,  # 0=Mon..6=Sun
        }

    # ---- helpers ----
    def weekday_from_ymd(self, y, m, d):
        # Tomohiko Sakamoto’s algorithm -> Monday=0..Sunday=6
        table = [0,3,2,5,0,3,5,1,4,6,2,4]
        y2 = y - (1 if m < 3 else 0)
        w_sun0 = (y2 + y2//4 - y2//100 + y2//400 + table[m-1] + d) % 7
        return (w_sun0 - 1) % 7

    def norm_year(self, y):
        # Map 0..99 -> 2000..2099; validate 2000..2099
        if 0 <= y <= 99:
            y = 2000 + y
        if not (2000 <= y <= 2099):
            warn(f"[MyRTC] PCF8523 year must be 2000..2099, got {y}")
            if y < 2000: y = 2000
            if y > 2099: y = 2099
        return y

    # ---- single partial setter ----
    def set_time(self, yr=None, mt=None, dy=None, hr=None, mn=None, sc=None):
        cur = self.now()
        year   = cur.tm_year if yr is None else yr
        month  = cur.tm_mon  if mt is None else mt
        day    = cur.tm_mday if dy is None else dy
        hour   = cur.tm_hour if hr is None else hr
        minute = cur.tm_min  if mn is None else mn
        second = cur.tm_sec  if sc is None else sc

        
        year = self.norm_year(year)
        wday = self.weekday_from_ymd(year, month, day)

        t = time.struct_time((year, month, day, hour, minute, second, wday, -1, -1))
        self.rtc.datetime = t
