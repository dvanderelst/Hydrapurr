"""
TestUpload.py - WiFi upload speed test, for walking around with the board

Joins the home WiFi (WIFI_SSID / WIFI_PASSWORD in settings.toml) and sends
data nonstop over TCP to UploadSink/upload_sink.py on a computer on the same
network (UPLOAD_TEST_HOST in settings.toml). The sink throws the data away.
Every upload_test_window_ms the screen shows:

    123.4 KB/s          rate over the last window (green/yellow/red)
    RSSI -61 ch 6       signal strength at the board (dBm), WiFi channel
    max send 12 ms      longest single send() of a 4 KB chunk
    tx 8.5dBm D1=chg    radio power; D1 cycles upload_test_tx_powers
    n 14 err 0          windows measured, connection errors

max send matters for the real upload: sending happens between samples, so a
send that blocks longer than ~8 ms would leave a gap in the recording.
The rate is what the board managed to hand to the network; the sink prints
what actually arrived.

Start it by holding D2 while the board starts (see code.py), or run it from
Thonny. Runs on a battery: nothing here needs USB. The result of each window
is also printed to the serial console.
"""

import time
import board
import wifi
import socketpool
import Settings
from StatusDisplay import StatusDisplay
from Button import Button

GREEN, YELLOW, RED, WHITE = 0x00FF00, 0xFFFF00, 0xFF4040, 0xFFFFFF
CONNECT_TIMEOUT_S = 10
SEND_TIMEOUT_S = 3
EAGAIN = 11             # 'send buffer full, try again'


def now_ms():
    return time.monotonic_ns() // 1_000_000


def rate_color(kb_s):
    # 4.4 KB/s is the average raw-data rate (380 MB/day); the events file
    # needs far less.
    if kb_s >= 50:
        return GREEN
    if kb_s >= 10:
        return YELLOW
    return RED


class UploadTest:
    def __init__(self):
        self.screen = StatusDisplay()
        self.screen.manual()
        self.button = Button(board.D1)
        self.powers = Settings.upload_test_tx_powers
        self.power_index = 0
        self.pool = socketpool.SocketPool(wifi.radio)
        self.sock = None
        self.chunk = bytes(Settings.upload_test_chunk)
        self.windows = 0
        self.errors = 0

    def show(self, line, text, color=WHITE, now=True):
        self.screen.set_line(line, text, color, now=now)

    def set_power(self):
        dbm = self.powers[self.power_index]
        try:
            wifi.radio.tx_power = dbm
        except Exception as e:
            print(f'could not set tx_power: {e!r}')
        self.screen.set_line(3, f'tx {dbm}dBm D1=chg')

    def rssi_line(self):
        ap = wifi.radio.ap_info
        if ap is None:
            return 'RSSI -- (no WiFi)', RED
        return f'RSSI {ap.rssi} ch {ap.channel}', WHITE

    def join(self):
        """Join the home WiFi; True when connected."""
        if wifi.radio.connected:
            return True
        self.show(0, 'joining WiFi...', YELLOW)
        try:
            wifi.radio.connect(Settings.wifi_ssid, Settings.wifi_password,
                               timeout=CONNECT_TIMEOUT_S)
        except Exception as e:
            print(f'WiFi join failed: {e!r}')
            self.errors += 1
            self.show(0, 'WiFi join failed', RED)
            return False
        print(f'joined {Settings.wifi_ssid}, ip {wifi.radio.ipv4_address}')
        self.set_power()       # tx_power is applied per connection
        return True

    def open_socket(self):
        """Connect to the sink; True when connected."""
        if self.sock is not None:
            return True
        self.show(0, 'connecting sink...', YELLOW)
        sock = self.pool.socket(self.pool.AF_INET, self.pool.SOCK_STREAM)
        sock.settimeout(SEND_TIMEOUT_S)
        try:
            sock.connect((Settings.upload_test_host, Settings.upload_test_port))
        except Exception as e:
            print(f'sink connect failed: {e!r}')
            sock.close()
            self.errors += 1
            self.show(0, 'no sink', RED)
            self.show(4, f'{Settings.upload_test_host}:{Settings.upload_test_port}', RED)
            return False
        self.sock = sock
        return True

    def close_socket(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def send_window(self):
        """Send for one window. Returns (bytes, ms, longest send ms, full),
        or None when the connection broke. full = how often the socket's send
        buffer was full (EAGAIN): CircuitPython sockets don't wait in send(),
        they raise OSError(11) instead, and the real upload must simply try
        again on the next loop pass."""
        start = now_ms()
        end = start + Settings.upload_test_window_ms
        sent = 0
        max_send = 0
        full = 0
        stalled_since = None
        view = memoryview(self.chunk)
        pos = 0
        while True:
            t = now_ms()
            if t >= end:
                return sent, t - start, max_send, full
            if self.button.pressed(t):
                self.power_index = (self.power_index + 1) % len(self.powers)
                self.set_power()
                self.screen.refresh_all()
                return sent, now_ms() - start, max_send, full
            try:
                n = self.sock.send(view[pos:])
            except OSError as e:
                code = getattr(e, 'errno', None) or (e.args[0] if e.args else None)
                if code == EAGAIN:
                    full += 1
                    if stalled_since is None:
                        stalled_since = t
                    elif t - stalled_since > SEND_TIMEOUT_S * 1000:
                        print(f'send stalled for {SEND_TIMEOUT_S} s')
                        return None
                    continue
                print(f'send failed: {e!r}')
                return None
            except Exception as e:
                print(f'send failed: {e!r}')
                return None
            stalled_since = None
            took = now_ms() - t
            if took > max_send:
                max_send = took
            sent += n
            pos += n
            if pos >= len(view):
                pos = 0

    def run(self):
        if not Settings.wifi_ssid or not Settings.upload_test_host:
            self.show(0, 'settings.toml:', RED)
            self.show(1, 'WIFI_SSID,', RED)
            self.show(2, 'WIFI_PASSWORD,', RED)
            self.show(3, 'UPLOAD_TEST_HOST', RED)
            self.show(4, 'missing', RED)
            while True:
                time.sleep(60)
        self.show(0, 'UPLOAD TEST', GREEN)
        self.show(1, Settings.wifi_ssid[:19])
        self.show(4, f'{Settings.upload_test_host}:{Settings.upload_test_port}')
        time.sleep(2)
        self.set_power()
        while True:
            text, color = self.rssi_line()
            self.screen.set_line(1, text, color)
            self.screen.set_line(4, f'n {self.windows} err {self.errors}')
            self.screen.refresh_all()
            if not self.join() or not self.open_socket():
                self.close_socket()
                time.sleep(2)
                continue
            result = self.send_window()
            if result is None:
                self.errors += 1
                self.close_socket()
                self.screen.set_line(0, 'send failed', RED)
                time.sleep(1)       # don't hammer the sink with reconnects
                continue
            sent, ms, max_send, full = result
            if ms < 500:
                continue            # cut short by D1: too short to report
            self.windows += 1
            kb_s = sent / 1024 / (ms / 1000)
            text, color = self.rssi_line()
            print(f'{kb_s:.1f} KB/s  {text}  max_send {max_send} ms  '
                  f'tx {self.powers[self.power_index]} dBm  buffer full {full}x  '
                  f'({sent} B in {ms} ms)')
            self.screen.set_line(0, f'{kb_s:.1f} KB/s', rate_color(kb_s))
            self.screen.set_line(2, f'max send {max_send} ms',
                                 GREEN if max_send <= 8 else YELLOW)


def run():
    UploadTest().run()


if __name__ == '__main__':
    run()
