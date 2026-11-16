"""
FileServer.py - serve the SD card over the lab WiFi while recording goes on

    http://hydrapurr.local/          (or http://<ip>/, the IP is in every
                                      heartbeat and on the screen at boot)

Every page is one folder of the card: /, /raw/, /raw/<date>/, /events/.
Click a file to download it, or fetch everything from a laptop with

    wget -r -np -nH -R "index.html*" http://hydrapurr.local/

How it keeps recording going: the server never blocks. MainLoop calls
poll(t, deadline) on every loop pass; it does small steps (accept a
connection, read the request, read one piece of a file, send it) only until
`deadline`, which is just before the next sample is due. A socket that is
not ready (EAGAIN: nothing to accept, request not here yet, send buffer
full) simply means "next pass". One client at a time; others wait in the
listen queue. Measured 2026-11-16 with plain sends: ~400-550 KB/s,
longest single 4 KB send 7 ms, so pieces are fileserver_chunk (2 KB) and
several go per pass when there is time.

A file still being written (this hour's raw file, today's events file) is
served up to its size when the request came in: the rest arrives on the
next fetch.
"""

import os
import time
import Settings
from components.MySystemLog import info, warn

SD_ROOT = "/sd"
EAGAIN = 11
ACCEPT_EVERY_MS = 50           # how often an idle server looks for a client
CLIENT_TIMEOUT_MS = 10000      # a client that does nothing this long is dropped
MAX_REQUEST = 2048


def now_ms():
    return time.monotonic_ns() // 1_000_000


def _errno(e):
    return getattr(e, 'errno', None) or (e.args[0] if e.args else None)


def _human(size):
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


# Kept apart from any f-string: CircuitPython treats plain literals placed
# next to an f-string as part of it, so the CSS braces became placeholders.
PAGE_STYLE = ("<style>body{font-family:sans-serif;margin:16px}"
              "td{padding:2px 12px 2px 0}</style>")


def _status_response(code, text):
    body = f"{code} {text}\n".encode()
    head = (f"HTTP/1.1 {code} {text}\r\nContent-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()
    return head + body


class FileServer:
    def __init__(self, pool, ip):
        self.pool = pool
        self.ip = ip
        self.listener = None
        self.client = None
        self._next_accept_ms = 0
        self.requests = 0
        self.bytes_sent = 0
        self.start()

    # --- listening socket ---------------------------------------------------

    def start(self):
        try:
            s = self.pool.socket(self.pool.AF_INET, self.pool.SOCK_STREAM)
            try:
                s.setsockopt(self.pool.SOL_SOCKET, self.pool.SO_REUSEADDR, 1)
            except Exception:
                pass
            s.bind((self.ip, 80))
            s.listen(2)
            s.setblocking(False)
            self.listener = s
            info(f'[Server] serving {SD_ROOT} at http://{self.ip}/')
        except Exception as e:
            warn(f'[Server] could not start: {e!r}')
            self.listener = None

    def stop(self):
        self._close_client('server stopped')
        if self.listener is not None:
            try:
                self.listener.close()
            except Exception:
                pass
        self.listener = None

    @property
    def busy(self):
        return self.client is not None

    # --- per-pass work ---------------------------------------------------------

    def poll(self, t, deadline):
        """Do server work until deadline (ms). Never blocks."""
        if self.listener is None:
            return
        if self.client is None:
            if t < self._next_accept_ms:
                return
            self._next_accept_ms = t + ACCEPT_EVERY_MS
            try:
                sock, addr = self.listener.accept()
            except OSError as e:
                if _errno(e) != EAGAIN:
                    warn(f'[Server] accept failed: {e!r}')
                return
            sock.setblocking(False)
            self.client = sock
            self.peer = addr[0] if addr else '?'
            self.request = b''
            self.body = None
            self.pending = None
            self.pos = 0
            self.sent = 0
            self.started_ms = t
            self.last_ms = t
            self.what = ''
        while self.client is not None and now_ms() < deadline:
            try:
                if self.body is None:
                    progressed = self._read_request()
                else:
                    progressed = self._send_some()
            except Exception as e:
                self._close_client(f'error {e!r}')
                return
            if not progressed:
                break
        if self.client is not None and now_ms() - self.last_ms > CLIENT_TIMEOUT_MS:
            self._close_client('timeout')

    def _read_request(self):
        buf = bytearray(512)
        try:
            n = self.client.recv_into(buf)
        except OSError as e:
            if _errno(e) == EAGAIN:
                return False
            raise
        if not n:
            self._close_client('closed by client')
            return False
        self.last_ms = now_ms()
        self.request += bytes(buf[:n])
        if b'\r\n\r\n' not in self.request:
            if len(self.request) > MAX_REQUEST:
                self._respond(_status_response(431, 'Request Too Large'), 'too large')
            return True
        line = self.request.split(b'\r\n', 1)[0].decode('utf-8', 'replace')
        parts = line.split(' ')
        if len(parts) < 2 or parts[0] != 'GET':
            self._respond(_status_response(405, 'Method Not Allowed'), line)
            return True
        self._route(parts[1].split('?', 1)[0])
        return True

    def _respond(self, data, what, body=None):
        """Start sending data (bytes), then the pieces of body (iterator)."""
        self.pending = data
        self.pos = 0
        self.body = body if body is not None else iter(())
        self.what = what

    def _send_some(self):
        if self.pending is None:
            try:
                self.pending = next(self.body)
                self.pos = 0
            except StopIteration:
                self._close_client('done')
                return False
            return True        # reading a piece took time: check the deadline
        try:
            n = self.client.send(memoryview(self.pending)[self.pos:])
        except OSError as e:
            if _errno(e) == EAGAIN:
                return False
            raise
        self.last_ms = now_ms()
        self.pos += n
        self.sent += n
        if self.pos >= len(self.pending):
            self.pending = None
        return True

    def _close_client(self, why):
        if self.client is None:
            return
        if self.body is not None:
            try:
                self.body.close()          # closes an open file
            except Exception:
                pass
        try:
            self.client.close()
        except Exception:
            pass
        self.client = None
        self.body = None
        self.pending = None
        self.requests += 1
        self.bytes_sent += self.sent
        took = now_ms() - self.started_ms
        if self.what:
            info(f'[Server] {self.peer} {self.what}: {self.sent} B in {took} ms ({why})')

    # --- pages and files --------------------------------------------------------

    def _route(self, path):
        if '..' in path or '//' in path:
            self._respond(_status_response(403, 'Forbidden'), f'GET {path} 403')
            return
        full = SD_ROOT + path.rstrip('/')
        try:
            st = os.stat(full)
        except OSError:
            self._respond(_status_response(404, 'Not Found'), f'GET {path} 404')
            return
        if st[0] & 0x4000:
            if not path.endswith('/'):
                head = (f"HTTP/1.1 301 Moved Permanently\r\nLocation: {path}/\r\n"
                        "Content-Length: 0\r\nConnection: close\r\n\r\n").encode()
                self._respond(head, f'GET {path} 301')
                return
            head = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                    b"Connection: close\r\n\r\n")
            self._respond(head, f'GET {path} (folder)', self._listing(full, path))
            return
        size = st[6]
        name = path.split('/')[-1]
        head = (f"HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n"
                f"Content-Length: {size}\r\n"
                f'Content-Disposition: attachment; filename="{name}"\r\n'
                f"Connection: close\r\n\r\n").encode()
        self._respond(head, f'GET {path} ({_human(size)})', self._file(full, size))

    def _file(self, full, size):
        """The file's first `size` bytes, one piece per next()."""
        chunk = Settings.fileserver_chunk
        left = size
        f = open(full, 'rb')
        try:
            while left > 0:
                data = f.read(min(chunk, left))
                if not data:
                    break
                left -= len(data)
                yield data
        finally:
            f.close()

    def _listing(self, full, path):
        """HTML page for one folder, one row per next() (each needs a stat)."""
        title = 'HydraPurr data' + ('' if path == '/' else f' {path}')
        yield (f"<!doctype html><html><head><meta charset='utf-8'>"
               f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
               f"<title>{title}</title>").encode() + PAGE_STYLE.encode()
        yield f"</head><body><h1>{title}</h1>".encode()
        if path == '/':
            yield ("<p>Recording goes on while you download. Everything at once:<br>"
                   "<code>wget -r -np -nH -R \"index.html*\" "
                   f"http://{Settings.mdns_hostname}.local/</code></p>").encode()
        else:
            yield b"<p><a href='../'>up</a></p>"
        yield b"<table>"
        try:
            names = sorted(os.listdir(full))
        except OSError:
            names = []
        for name in names:
            if name.startswith('.') or name == 'System Volume Information':
                continue
            try:
                st = os.stat(full + '/' + name)
            except OSError:
                continue
            if st[0] & 0x4000:
                yield f'<tr><td><a href="{name}/">{name}/</a></td><td></td></tr>'.encode()
            else:
                yield (f'<tr><td><a href="{name}">{name}</a></td>'
                       f'<td style="text-align:right">{_human(st[6])}</td></tr>').encode()
        yield b"</table></body></html>"
