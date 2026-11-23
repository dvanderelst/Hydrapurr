"""
TestHeartbeat.py - healthchecks.io heartbeat test: how long does one block?

The real recorder will send a heartbeat (an HTTPS POST to healthchecks.io)
every 15 min. Recording stops while it runs, so this test measures each step
of one heartbeat, on the board, on the real network:

    dns     look up hc-ping.com
    tls     TCP connect + TLS handshake (expected to be the slow one)
    send    the HTTP request with a short status line as body
    reply   wait for healthchecks' answer ("OK")
    total   everything, = the gap one heartbeat would leave in the recording

Screen:
    HB 12 ok 1840ms         heartbeats sent, last result, last total
    tls 1520 dns 40         slowest steps of the last heartbeat (ms)
    send 12 reply 260       ...
    max 2100 mem 1.2M       longest total so far, free memory
    D1=fail RSSI -43        D1 sends a /fail ping (tests the alert)

One heartbeat every TEST_INTERVAL_S (so the check in healthchecks.io stays
green while testing, and enough samples come in fast). Every result is also
printed to the serial console.

Needs in the board's settings.toml (never in git):
    WIFI_SSID, WIFI_PASSWORD
    HEALTHCHECK_URL = "https://hc-ping.com/<uuid>"

Start it by holding D2 while the board starts (see code.py), or run it from
Thonny. End it with Reset, not Ctrl-C: a soft reboot with WiFi connected has
dropped USB (HANDOFF.md, 2026-11-16).
"""

import gc
import ssl
import time
import board
import wifi
import socketpool
import Settings
from StatusDisplay import StatusDisplay
from Button import Button

GREEN, YELLOW, RED, WHITE = 0x00FF00, 0xFFFF00, 0xFF4040, 0xFFFFFF
TEST_INTERVAL_S = 60
CONNECT_TIMEOUT_S = 10
SOCKET_TIMEOUT_S = 10
EAGAIN = 11


def now_ms():
    return time.monotonic_ns() // 1_000_000


def split_url(url):
    """'https://hc-ping.com/abc' -> ('hc-ping.com', '/abc')."""
    rest = url.split("://", 1)[-1]
    if "/" in rest:
        host, path = rest.split("/", 1)
        return host, "/" + path
    return rest, "/"


def mem_text(n):
    return f"{n / (1024 * 1024):.1f}M" if n >= 1024 * 1024 else f"{n // 1024}K"


class HeartbeatTest:
    def __init__(self):
        self.screen = StatusDisplay()
        self.screen.manual()
        self.button = Button(board.D1)
        self.pool = socketpool.SocketPool(wifi.radio)
        self.context = ssl.create_default_context()
        self.host, self.path = split_url(Settings.healthcheck_url or "")
        self.sent = 0
        self.failures = 0
        self.max_total = 0
        self.boot_ms = now_ms()

    def show(self, line, text, color=WHITE):
        self.screen.set_line(line, text, color)

    def join(self):
        if wifi.radio.connected:
            return True
        self.show(0, 'joining WiFi...', YELLOW)
        self.screen.refresh_all()
        joined = None
        for ssid, password in Settings.wifi_networks:   # first that works
            try:
                wifi.radio.connect(ssid, password, timeout=CONNECT_TIMEOUT_S)
                joined = ssid
                break
            except Exception as e:
                print(f'WiFi join {ssid} failed: {e!r}')
        if joined is None:
            self.show(0, 'WiFi join failed', RED)
            self.screen.refresh_all()
            return False
        try:
            wifi.radio.tx_power = Settings.wifi_tx_power_dbm
        except Exception:
            pass
        print(f'joined {joined}, ip {wifi.radio.ipv4_address}')
        return True

    def status_line(self, kind):
        ap = wifi.radio.ap_info
        rssi = ap.rssi if ap is not None else None
        up_s = (now_ms() - self.boot_ms) // 1000
        # n = number of this heartbeat (1 = first), as in the console
        return (f'test={kind} n={self.sent + 1} up={up_s}s rssi={rssi} '
                f'ip={wifi.radio.ipv4_address} mem_free={gc.mem_free()}')

    def send_all(self, sock, data):
        view = memoryview(data)
        pos = 0
        start = now_ms()
        while pos < len(view):
            try:
                n = sock.send(view[pos:])
            except OSError as e:
                code = getattr(e, 'errno', None) or (e.args[0] if e.args else None)
                if code == EAGAIN and now_ms() - start < SOCKET_TIMEOUT_S * 1000:
                    continue
                raise
            pos += n

    def read_reply(self, sock):
        """Return the HTTP status line; reads until the server closes."""
        buf = bytearray(512)
        got = b''
        start = now_ms()
        while now_ms() - start < SOCKET_TIMEOUT_S * 1000:
            try:
                n = sock.recv_into(buf)
            except OSError as e:
                code = getattr(e, 'errno', None) or (e.args[0] if e.args else None)
                if code == EAGAIN:
                    if b'\r\n\r\n' in got:
                        break
                    continue
                raise
            if not n:
                break
            got += bytes(buf[:n])
            if len(got) > 2048 or (b'\r\n\r\n' in got and got.endswith(b'OK')):
                break
        return got.split(b'\r\n', 1)[0].decode('utf-8', 'replace')

    def heartbeat(self, fail=False):
        """One POST; returns (ok, {step: ms}, http status line)."""
        path = self.path + ('/fail' if fail else '')
        body = self.status_line('fail' if fail else 'ok').encode()
        request = (f'POST {path} HTTP/1.1\r\nHost: {self.host}\r\n'
                   f'User-Agent: hydrapurr\r\nContent-Type: text/plain\r\n'
                   f'Content-Length: {len(body)}\r\nConnection: close\r\n\r\n'
                   ).encode() + body
        times = {}
        gc.collect()
        mem_before = gc.mem_free()
        t0 = now_ms()
        sock = None
        try:
            addr = self.pool.getaddrinfo(self.host, 443)[0][-1]
            t1 = now_ms()
            times['dns'] = t1 - t0
            sock = self.context.wrap_socket(
                self.pool.socket(self.pool.AF_INET, self.pool.SOCK_STREAM),
                server_hostname=self.host)
            sock.settimeout(SOCKET_TIMEOUT_S)
            sock.connect(addr)
            t2 = now_ms()
            times['tls'] = t2 - t1
            self.send_all(sock, request)
            t3 = now_ms()
            times['send'] = t3 - t2
            status = self.read_reply(sock)
            times['reply'] = now_ms() - t3
            ok = ' 200' in status
        except Exception as e:
            status = repr(e)
            ok = False
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
        times['total'] = now_ms() - t0
        times['mem_used'] = mem_before - gc.mem_free()
        return ok, times, status

    def run(self):
        if not Settings.wifi_networks or not Settings.healthcheck_url:
            for i, text in enumerate(('settings.toml:', 'WIFI_SSID,', 'WIFI_PASSWORD,',
                                      'HEALTHCHECK_URL', 'missing')):
                self.show(i, text, RED)
            self.screen.refresh_all()
            while True:
                time.sleep(60)
        self.show(0, 'HEARTBEAT TEST', GREEN)
        self.show(1, self.host[:19])
        self.show(2, '')
        self.show(3, '')
        self.show(4, 'D1=fail ping')
        self.screen.refresh_all()
        next_ms = now_ms()
        fail_next = False
        while True:
            t = now_ms()
            if self.button.pressed(t):
                fail_next = True
                next_ms = t
                self.show(0, 'sending fail...', YELLOW)   # feedback now: the
                self.screen.refresh_all()                 # ping takes ~3.5 s
            if t < next_ms:
                time.sleep(0.02)
                continue
            next_ms = t + TEST_INTERVAL_S * 1000
            if not self.join():
                next_ms = now_ms() + 5000
                continue
            ok, times, status = self.heartbeat(fail=fail_next)
            kind = 'fail' if fail_next else 'ok'
            fail_next = False
            self.sent += 1
            if not ok:
                self.failures += 1
            self.max_total = max(self.max_total, times['total'])
            print(f'heartbeat {self.sent} ({kind}): {status}  '
                  + '  '.join(f'{k} {v}' for k, v in times.items()))
            ap = wifi.radio.ap_info
            rssi = f'RSSI {ap.rssi}' if ap is not None else 'no WiFi'
            color = GREEN if ok else RED
            self.show(0, f'HB {self.sent} {kind if ok else "ERR"} {times["total"]}ms', color)
            self.show(1, f'tls {times.get("tls", "-")} dns {times.get("dns", "-")}')
            self.show(2, f'send {times.get("send", "-")} reply {times.get("reply", "-")}')
            self.show(3, f'max {self.max_total} mem {mem_text(gc.mem_free())}')
            self.show(4, f'D1=fail {rssi}')
            self.screen.refresh_all()


def run():
    HeartbeatTest().run()


if __name__ == '__main__':
    run()
