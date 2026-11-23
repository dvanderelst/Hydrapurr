"""
Network.py - lab WiFi (station mode) and the healthchecks.io heartbeat

The recorder joins the WiFi at boot (WIFI_SSID / WIFI_PASSWORD in
settings.toml, plus WIFI_SSID_2 ... _5 for more networks: Settings.wifi_networks)
and stays connected. A join scans first and tries the listed networks that are
in range, in the listed order (one attempt, up to wifi_connect_timeout_s, per
visible network; one not in range costs nothing). A lost connection is re-joined, at most
every wifi_retry_ms and only when the loop allows it (joining blocks up to
wifi_connect_timeout_s, so the loop asks only when the wire is quiet).

ntp_time() asks a time server for UTC (MainLoop sets the RTC with it at
boot and once a day).

It also announces the board as <mdns_hostname>.local (mDNS), for the file
server (FileServer.py).

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
        self.enabled = bool(Settings.wifi_enabled and Settings.wifi_networks)
        self.ssid = None           # network joined last
        self.used = False          # radio touched: avoid soft reboots
        self.pool = None
        self.context = None
        self.mdns = None           # keeps the hydrapurr.local name alive
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

    def join(self, feed=None):
        """Join the WiFi. Blocks ~2 s (scan) plus up to wifi_connect_timeout_s
        per network tried; feed() (the watchdog) is called before each try.
        Returns True when connected."""
        if not self.enabled:
            return False
        import wifi
        import socketpool
        import ssl
        self.used = True
        self._next_join_ms = now_ms() + Settings.wifi_retry_ms
        # Already connected (e.g. a soft reboot after a crash): still set up
        # the socket pool and mDNS below, or nothing network-side works.
        if not wifi.radio.connected:
            if not self._connect(wifi, feed):
                return False
        else:
            ap = wifi.radio.ap_info
            self.ssid = ap.ssid if ap is not None else self.ssid
        try:
            wifi.radio.tx_power = Settings.wifi_tx_power_dbm
        except Exception as e:
            warn(f'[Network] could not set tx_power: {e!r}')
        if self.pool is None:
            self.pool = socketpool.SocketPool(wifi.radio)
            self.context = ssl.create_default_context()
        if self.mdns is None:
            try:
                import mdns
                server = mdns.Server(wifi.radio)
                server.hostname = Settings.mdns_hostname
                server.advertise_service(service_type='_http', protocol='_tcp', port=80)
                self.mdns = server
            except Exception as e:
                warn(f'[Network] mDNS name not set: {e!r}')
        info(f'[Network] joined {self.ssid}, ip {self.ip()}, rssi {self.rssi()}')
        return True

    def visible_ssids(self, wifi):
        """SSIDs in range (one scan, ~2 s). None when the scan fails."""
        try:
            seen = set()
            for net in wifi.radio.start_scanning_networks():
                seen.add(net.ssid)
            return seen
        except Exception as e:
            warn(f'[Network] WiFi scan failed: {e!r}')
            return None
        finally:
            try:
                wifi.radio.stop_scanning_networks()
            except Exception:
                pass

    def _connect(self, wifi, feed):
        """Try the listed networks that are in range, in the listed order.
        A failed scan: try them all (the scan is only a shortcut)."""
        nets = Settings.wifi_networks
        seen = self.visible_ssids(wifi) if len(nets) > 1 else None
        if seen is not None:
            tried = [n for n in nets if n[0] in seen]
            if not tried:
                warn(f'[Network] none of the {len(nets)} WiFi networks in range')
                return False
        else:
            tried = nets
        for ssid, password in tried:
            if feed is not None:
                feed()
            try:
                wifi.radio.connect(ssid, password,
                                   timeout=Settings.wifi_connect_timeout_s)
                self.ssid = ssid
                return True
            except Exception as e:
                warn(f'[Network] WiFi join {ssid} failed: {e!r}')
        return False

    # --- clock (NTP) ----------------------------------------------------------

    def ntp_time(self):
        """Ask the NTP server for the time. Returns (utc_ms, mono_ms, rtt_ms):
        utc_ms was the UTC time (ms since 1970) at monotonic time mono_ms.
        None when it fails. Blocks up to ntp_timeout_s (one UDP round trip,
        normally well under 0.2 s). Integers only: CircuitPython floats
        can't hold an epoch to the millisecond."""
        if not self.connected:
            return None
        sock = None
        try:
            addr = self.pool.getaddrinfo(Settings.ntp_server, 123)[0][-1]
            sock = self.pool.socket(self.pool.AF_INET, self.pool.SOCK_DGRAM)
            sock.settimeout(Settings.ntp_timeout_s)
            packet = bytearray(48)
            packet[0] = 0x1B                 # version 3, client mode
            t_send = now_ms()
            sock.sendto(packet, addr)
            buf = bytearray(48)
            n, _ = sock.recvfrom_into(buf)
            t_recv = now_ms()
            if n < 48:
                return None
            # A server reply (mode 4), synchronised (leap indicator not 3),
            # from a real clock source (stratum 1-15): else don't trust it.
            leap, mode, stratum = buf[0] >> 6, buf[0] & 7, buf[1]
            if mode != 4 or leap == 3 or not 1 <= stratum <= 15:
                warn(f'[Network] NTP reply not usable (leap {leap}, mode {mode}, '
                     f'stratum {stratum})')
                return None
            secs = int.from_bytes(buf[40:44], 'big')      # transmit timestamp
            frac = int.from_bytes(buf[44:48], 'big')
            if secs < 3_970_000_000:                      # before Oct 2025: nonsense
                return None
            rtt = t_recv - t_send
            utc_ms = (secs - 2208988800) * 1000 + (frac * 1000 >> 32) + rtt // 2
            return utc_ms, t_recv, rtt
        except Exception as e:
            warn(f'[Network] NTP failed: {e!r}')
            return None
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

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
