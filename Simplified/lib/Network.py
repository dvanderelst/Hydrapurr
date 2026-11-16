"""
Network.py - lab WiFi (station mode) and the healthchecks.io heartbeat

The recorder joins the WiFi at boot (WIFI_SSID / WIFI_PASSWORD in
settings.toml) and stays connected. A lost connection is re-joined, at most
every wifi_retry_ms and only when the loop allows it (joining blocks up to
wifi_connect_timeout_s, so the loop asks only when the wire is quiet).

heartbeat() sends one HTTPS POST to HEALTHCHECK_URL (or <url>/fail) with a
status line as body. Measured 2026-11-16: ~3.5 s, almost all of it the TLS
handshake, ~5 KB memory. Recording stops for that long, so MainLoop only
calls it when the wire has been quiet.

Without WiFi credentials, or with wifi_enabled = False, everything here is a
no-op and the recorder runs as before. `used` tells MainLoop whether the
radio was touched: then a soft reboot can drop USB (HANDOFF.md, 2026-11-16),
so MainLoop resets the board instead.
"""

import gc
import time
import Settings
from components.MySystemLog import info, warn

EAGAIN = 11                    # "send buffer full / no data yet, try again"
SOCKET_TIMEOUT_S = 10


def now_ms():
    return time.monotonic_ns() // 1_000_000


def _errno(e):
    return getattr(e, 'errno', None) or (e.args[0] if e.args else None)


def split_url(url):
    """'https://hc-ping.com/abc' -> ('hc-ping.com', '/abc')."""
    rest = url.split("://", 1)[-1]
    if "/" in rest:
        host, path = rest.split("/", 1)
        return host, "/" + path
    return rest, "/"


class Network:
    def __init__(self):
        self.enabled = bool(Settings.wifi_enabled and Settings.wifi_ssid)
        self.used = False          # radio touched: avoid soft reboots
        self.pool = None
        self.context = None
        self._next_join_ms = 0
        self.was_connected = False
        self.heartbeat_url = Settings.healthcheck_url
        if self.heartbeat_url:
            self.host, self.path = split_url(self.heartbeat_url)
        else:
            self.host, self.path = None, None

    # --- WiFi ---------------------------------------------------------------

    @property
    def connected(self):
        if not self.enabled:
            return False
        import wifi
        return wifi.radio.connected

    def rssi(self):
        if not self.connected:
            return None
        import wifi
        ap = wifi.radio.ap_info
        return ap.rssi if ap is not None else None

    def ip(self):
        if not self.connected:
            return None
        import wifi
        return str(wifi.radio.ipv4_address)

    def join_due(self, t_ms):
        """True when not connected and a (blocking) join may be tried."""
        return self.enabled and not self.connected and t_ms >= self._next_join_ms

    def join(self):
        """Join the WiFi. Blocks up to wifi_connect_timeout_s. Returns True
        when connected."""
        if not self.enabled:
            return False
        import wifi
        import socketpool
        import ssl
        self.used = True
        self._next_join_ms = now_ms() + Settings.wifi_retry_ms
        if wifi.radio.connected:
            return True
        try:
            wifi.radio.connect(Settings.wifi_ssid, Settings.wifi_password,
                               timeout=Settings.wifi_connect_timeout_s)
        except Exception as e:
            warn(f'[Network] WiFi join failed: {e!r}')
            return False
        try:
            wifi.radio.tx_power = Settings.wifi_tx_power_dbm
        except Exception as e:
            warn(f'[Network] could not set tx_power: {e!r}')
        if self.pool is None:
            self.pool = socketpool.SocketPool(wifi.radio)
            self.context = ssl.create_default_context()
        info(f'[Network] joined {Settings.wifi_ssid}, ip {self.ip()}, rssi {self.rssi()}')
        return True

    # --- heartbeat ------------------------------------------------------------

    def _send_all(self, sock, data):
        view = memoryview(data)
        pos = 0
        start = now_ms()
        while pos < len(view):
            try:
                pos += sock.send(view[pos:])
            except OSError as e:
                if _errno(e) == EAGAIN and now_ms() - start < SOCKET_TIMEOUT_S * 1000:
                    continue
                raise

    def _read_status(self, sock):
        """HTTP status line of the reply ('HTTP/1.1 200 OK')."""
        buf = bytearray(512)
        got = b''
        start = now_ms()
        while now_ms() - start < SOCKET_TIMEOUT_S * 1000:
            try:
                n = sock.recv_into(buf)
            except OSError as e:
                if _errno(e) == EAGAIN:
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

    def heartbeat(self, body, fail=False):
        """POST body to the healthcheck URL (/fail when fail). Blocking,
        ~3.5 s. Returns (ok, ms, status text)."""
        t0 = now_ms()
        if not self.connected or self.host is None:
            return False, 0, 'no WiFi' if self.host else 'no HEALTHCHECK_URL'
        path = self.path + ('/fail' if fail else '')
        data = body.encode()
        request = (f'POST {path} HTTP/1.1\r\nHost: {self.host}\r\n'
                   f'User-Agent: hydrapurr\r\nContent-Type: text/plain\r\n'
                   f'Content-Length: {len(data)}\r\nConnection: close\r\n\r\n'
                   ).encode() + data
        sock = None
        try:
            gc.collect()
            addr = self.pool.getaddrinfo(self.host, 443)[0][-1]
            sock = self.context.wrap_socket(
                self.pool.socket(self.pool.AF_INET, self.pool.SOCK_STREAM),
                server_hostname=self.host)
            sock.settimeout(SOCKET_TIMEOUT_S)
            sock.connect(addr)
            self._send_all(sock, request)
            status = self._read_status(sock)
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
        return ok, now_ms() - t0, status
