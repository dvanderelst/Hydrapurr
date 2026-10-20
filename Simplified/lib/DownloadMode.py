"""
DownloadMode.py - get the data off the board over WiFi, without a network

Press the D1 button: recording pauses, the board starts its own WiFi network
(access point) and serves the SD card over HTTP. Connect a laptop or phone
to that network and open the address shown on the screen:

    http://192.168.4.1/      list of all files on the SD card, as links

Click a file to download it, or fetch everything from a laptop with
    wget -r -np -nH http://192.168.4.1/

Press D1 again, or leave it untouched for download_timeout_ms, to switch
WiFi off and resume recording. The access point only runs in this mode, so it never
mixes with the measurements (noise on touch readings, current spikes).

D1 on the Reverse TFT reads differently from D0 (D0 is pulled up, D1/D2
pulled down), so "pressed" means "different from the level at startup".
"""

import os
import time
import board
import digitalio
import Settings
from components.MySystemLog import info, warn, flush

SD_ROOT = "/sd"
DEBOUNCE_MS = 50
_ap_ip = ""                    # access point address, for the index page


def now_ms():
    return int(time.monotonic() * 1000)


class Button:
    """Edge-detecting button: pressed() is True once per press."""

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


def _human(size):
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _list_files(path, rel=""):
    """All files under path as (relative path, size), depth first, sorted."""
    out = []
    try:
        names = sorted(os.listdir(path))
    except OSError:
        return out
    for name in names:
        if name.startswith(".") or name == "System Volume Information":
            continue
        full = path + "/" + name
        try:
            st = os.stat(full)
        except OSError:
            continue
        rel_name = rel + "/" + name
        if st[0] & 0x4000:
            out.extend(_list_files(full, rel_name))
        else:
            out.append((rel_name, st[6]))
    return out


# Kept apart from any f-string: CircuitPython treats plain literals placed
# next to an f-string as part of it, so the CSS braces became placeholders.
PAGE_HEAD = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>HydraPurr data</title>"
    "<style>body{font-family:sans-serif;margin:16px}"
    "td{padding:2px 12px 2px 0}</style></head><body>"
    "<h1>HydraPurr data</h1>"
)


def _index_html():
    files = _list_files(SD_ROOT)
    total = sum(size for _, size in files)
    parts = [PAGE_HEAD]
    parts.append(f"<p>{len(files)} files, {_human(total)} on the SD card. ")
    parts.append("Recording is paused while this page is up.</p>")
    parts.append(f"<p>Everything at once: <code>wget -r -np -nH http://{_ap_ip}/</code></p>")
    parts.append("<table>")
    for rel, size in files:
        parts.append(f'<tr><td><a href="{rel}" download>{rel[1:]}</a></td>')
        parts.append(f'<td style="text-align:right">{_human(size)}</td></tr>')
    parts.append("</table></body></html>")
    return "".join(parts)


def run(screen, button):
    """Serve the SD card over a WiFi access point until D1 is pressed again
    or download_timeout_ms passes without a request. Blocking."""
    global _ap_ip
    import wifi
    import socketpool
    import gc
    from adafruit_httpserver import Server, Request, Response, ChunkedResponse

    ssid = Settings.download_ap_ssid
    password = Settings.download_ap_password
    info(f'[Download] starting access point "{ssid}"')
    flush()

    # Lower transmit power: the default (~20 dBm) is far more than a client
    # a few metres away needs, and its current spikes are a suspect for
    # restarts during long downloads.
    try:
        wifi.radio.tx_power = Settings.download_tx_power_dbm
    except Exception as e:
        warn(f'[Download] could not set tx_power: {e!r}')
    wifi.radio.start_ap(ssid, password)
    ip = str(wifi.radio.ipv4_address_ap)
    _ap_ip = ip
    pool = socketpool.SocketPool(wifi.radio)
    # No root_path: the library's own file serving stays off. Files go out
    # through send_file() below in 4 KB chunks. (A large download through the
    # library at full radio power hard-faulted the board; with lower power
    # both paths worked, but this one was tested on the largest file.)
    server = Server(pool, None, debug=False)

    @server.route("/")
    def index(request: Request):
        return Response(request, _index_html(), content_type="text/html")

    def send_file(request, rel):
        """Stream /sd/<rel> in 4 KB chunks as a download."""
        if ".." in rel:
            return Response(request, "Invalid path", status=(403, "Forbidden"))
        path = SD_ROOT + rel
        try:
            os.stat(path)
        except OSError:
            return Response(request, "File not found", status=(404, "Not Found"))
        info(f'[Download] sending {path} (mem_free={gc.mem_free()})')
        buf = bytearray(4096)

        def body():
            with open(path, "rb") as f:
                while True:
                    n = f.readinto(buf)
                    if not n:
                        break
                    yield bytes(buf[:n])
        name = rel.split("/")[-1]
        return ChunkedResponse(
            request, body, content_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # The SD card holds top-level files and /raw/<date>/<hour>.csv; these two
    # routes cover both and keep the same URLs as the file paths.
    @server.route("/raw/<day>/<name>")
    def raw_file(request: Request, day: str, name: str):
        return send_file(request, f"/raw/{day}/{name}")

    @server.route("/<name>")
    def top_file(request: Request, name: str):
        return send_file(request, "/" + name)

    server.start(ip, 80)
    info(f'[Download] serving {SD_ROOT} at http://{ip}/')

    screen.set_line(0, 'DOWNLOAD MODE', 0xFFFF00)
    screen.set_line(1, f'WiFi {ssid}')
    screen.set_line(2, f'pw {password}')
    screen.set_line(3, f'http://{ip}')
    screen.set_line(4, 'D1 = resume')
    screen.refresh_all()

    last_activity = now_ms()
    requests = 0
    try:
        while True:
            t = now_ms()
            if button.pressed(t):
                info('[Download] D1 pressed: leaving download mode')
                break
            if t - last_activity > Settings.download_timeout_ms:
                info('[Download] timeout: leaving download mode')
                break
            try:
                result = server.poll()
            except Exception as e:
                warn(f'[Download] request failed: {e!r}')
                continue
            if result != "no_request":
                last_activity = now_ms()
                requests += 1
    finally:
        try:
            server.stop()
        except Exception:
            pass
        try:
            wifi.radio.stop_ap()
        except Exception:
            pass
        # Only the access point is stopped; wifi.radio.enabled is left alone
        # (toggling it was the main suspect for USB hangs on soft reboot).
        info(f'[Download] access point off after {requests} requests; resuming recording')
