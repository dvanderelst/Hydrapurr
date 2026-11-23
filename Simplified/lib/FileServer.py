"""
FileServer.py - serve the SD card over the lab WiFi while recording goes on

    http://hydrapurr.local/          (or http://<ip>/, the IP is in every
                                      heartbeat and on the screen at boot)

Pages:
    /                      start page for testers: what the board is doing,
                           and per day one link for the raw data (all hours
                           joined into one CSV) and one for the events file
    /day/<date>/raw.csv    that day's hourly raw files, sent one after the
                           other as a single file (nothing is stored twice)
    /files/                the card's folders, one page each, every file's
                           exact size as data-size="..." (for
                           ProcessLickData/library/hydrapurr_fetch.py)
    /raw/..., /events/...  the folders and files themselves

Days are the board's days, so UTC days (MainLoop keeps the RTC on UTC).

Fast download (pause): any file link with ?pause=1 makes MainLoop stop
sampling while that one download runs, so the board only sends (bigger
pieces, no sample deadlines). Sampling resumes when the download ends, when
the client stalls (CLIENT_TIMEOUT_MS) or after fileserver_max_pause_ms,
whichever comes first. MainLoop logs `paused`/`resumed` event rows. Only
offered when Settings.fileserver_allow_pause is True; otherwise ?pause=1 is
ignored and the download runs alongside recording as usual.

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
next fetch. `before_file` (MainLoop: flush the recorder and the event log)
runs before that size is taken, so the download holds everything up to the
request instead of up to the last periodic flush (raw_log_sync_ms).
"""

import os
import time
import Settings
from components.MySystemLog import info, warn

SD_ROOT = "/sd"
EAGAIN = 11
ACCEPT_EVERY_MS = 50           # how often an idle server looks for a client
FAST_BYTES_PER_S = 300 * 1024  # paused download speed, a bit under the measured ~360 KB/s
CLIENT_TIMEOUT_MS = 10000      # a client that does nothing this long is dropped
# Browsers open spare connections in advance and send nothing on them. With
# one client at a time, such a connection held up the real request until the
# timeout (an 11 KB file took 9.9 s, 2026-11-17). A connection that has sent
# nothing yet is dropped for a waiting one, or after REQUEST_TIMEOUT_MS.
REQUEST_TIMEOUT_MS = 2000
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


def _is_dir(st):
    return bool(st[0] & 0x4000)


def _stat(path):
    try:
        return os.stat(path)
    except OSError:
        return None


def _listdir(path):
    try:
        return sorted(n for n in os.listdir(path)
                      if not n.startswith('.') and n != 'System Volume Information')
    except OSError:
        return []


# Kept apart from any f-string: CircuitPython treats plain literals placed
# next to an f-string as part of it, so the CSS braces became placeholders.
PAGE_STYLE = ("<style>body{font-family:sans-serif;margin:16px;max-width:52em}"
              "td,th{padding:3px 14px 3px 0;text-align:left}"
              ".r{text-align:right}.note{color:#555;font-size:90%}"
              ".st{padding:8px 12px;background:#eef6ee;border-radius:6px}"
              ".warn{padding:6px 12px;background:#fdecea;border-left:4px solid #c62828;font-size:90%}</style>")


def _head(title):
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{title}</title>").encode() + PAGE_STYLE.encode() + b"</head><body>"


def _status_response(code, text):
    body = f"{code} {text}\n".encode()
    head = (f"HTTP/1.1 {code} {text}\r\nContent-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()
    return head + body


def _file_head(name, size):
    return (f"HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n"
            f"Content-Length: {size}\r\n"
            f'Content-Disposition: attachment; filename="{name}"\r\n'
            f"Connection: close\r\n\r\n").encode()


HTML_HEAD = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
             b"Cache-Control: no-store\r\nConnection: close\r\n\r\n")


class FileServer:
    def __init__(self, pool, ip, before_file=None):
        self.pool = pool
        self.ip = ip
        self.before_file = before_file
        self.listener = None
        self.client = None
        self._next_accept_ms = 0
        self.requests = 0
        self.bytes_sent = 0
        # Set by MainLoop about once a second: one line for the start page.
        self.status = ''
        # Pause: wanted by the current download (?pause=1); MainLoop asks
        # `pausing` every pass. pause_end says why the last one ended.
        self._pause = False
        self._pause_since_ms = 0
        self.pause_what = ''
        self.pause_end = ''
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

    @property
    def pausing(self):
        """True while the current download asked for recording to pause."""
        if not self._pause:
            return False
        if now_ms() - self._pause_since_ms > Settings.fileserver_max_pause_ms:
            warn('[Server] pause longer than fileserver_max_pause_ms: recording again, '
                 'download goes on alongside')
            self._end_pause('max_pause')
            return False
        return True

    def _end_pause(self, why):
        if self._pause:
            self._pause = False
            self.pause_end = why

    def _chunk(self):
        return Settings.fileserver_pause_chunk if self._pause else Settings.fileserver_chunk

    # --- per-pass work ---------------------------------------------------------

    def poll(self, t, deadline):
        """Do server work until deadline (ms). Never blocks."""
        if self.listener is None:
            return
        idle = self.client is not None and self.body is None and not self.request
        if (self.client is None or idle) and t >= self._next_accept_ms:
            self._next_accept_ms = t + ACCEPT_EVERY_MS
            try:
                sock, addr = self.listener.accept()
            except OSError as e:
                if _errno(e) != EAGAIN:
                    warn(f'[Server] accept failed: {e!r}')
                sock = None
            if sock is not None:
                if idle:
                    self._drop_idle()          # a spare connection: take the new one
                self._take(sock, addr, t)
        if self.client is None:
            return
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
        if self.client is not None:
            if self.body is None and not self.request:
                if now_ms() - self.started_ms > REQUEST_TIMEOUT_MS:
                    self._drop_idle()
            elif now_ms() - self.last_ms > CLIENT_TIMEOUT_MS:
                self._close_client('timeout')

    def _take(self, sock, addr, t):
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

    def _drop_idle(self):
        """Close a connection that never sent a request (not logged)."""
        try:
            self.client.close()
        except Exception:
            pass
        self.client = None

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
        target = parts[1].split('?', 1)
        query = target[1] if len(target) > 1 else ''
        self._route(target[0], 'pause=1' in query.split('&'))
        return True

    def _respond(self, data, what, body=None):
        """Start sending data (bytes), then the pieces of body (iterator)."""
        self.pending = data or None
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
            if not self.pending:
                self.pending = None    # an empty piece: a step that only did a stat
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
        self._end_pause(why)
        self.requests += 1
        self.bytes_sent += self.sent
        took = now_ms() - self.started_ms
        if self.what:
            info(f'[Server] {self.peer} {self.what}: {self.sent} B in {took} ms ({why})')

    # --- pages and files --------------------------------------------------------

    def _route(self, path, pause):
        if not path.startswith('/') or '..' in path or '//' in path:
            self._respond(_status_response(403, 'Forbidden'), f'GET {path} 403')
            return
        if path == '/':
            self._respond(HTML_HEAD, 'GET / (start page)', self._start_page())
            return
        if path in ('/files', '/files/'):
            if path == '/files':
                self._redirect('/files/')
                return
            self._respond(HTML_HEAD, 'GET /files/ (folder)', self._listing(SD_ROOT, '/'))
            return
        parts = path.split('/')            # ['', 'day', '<date>', 'raw.csv']
        if len(parts) == 4 and parts[1] == 'day' and parts[3] == 'raw.csv':
            day_dir = f"{SD_ROOT}/raw/{parts[2]}"
            st = _stat(day_dir)
            if st is None or not _is_dir(st):
                self._respond(_status_response(404, 'Not Found'), f'GET {path} 404')
                return
            self._begin_pause(pause, path)
            self._flush_data()
            self._respond(b'', f'GET {path} (day)', self._day_raw(day_dir, parts[2]))
            return
        full = SD_ROOT + path.rstrip('/')
        if not path.endswith('/'):
            self._flush_data()          # a file: its size should include the latest rows
        st = _stat(full)
        if st is None:
            self._respond(_status_response(404, 'Not Found'), f'GET {path} 404')
            return
        if _is_dir(st):
            if not path.endswith('/'):
                self._redirect(path + '/')
                return
            self._respond(HTML_HEAD, f'GET {path} (folder)', self._listing(full, path))
            return
        size = st[6]
        self._begin_pause(pause, path)
        self._respond(_file_head(path.split('/')[-1], size),
                      f'GET {path} ({_human(size)})', self._file(full, size))

    def _flush_data(self):
        if self.before_file is not None:
            try:
                self.before_file()
            except Exception as e:
                warn(f'[Server] flush before a file failed: {e!r}')

    def _redirect(self, to):
        head = (f"HTTP/1.1 301 Moved Permanently\r\nLocation: {to}\r\n"
                "Content-Length: 0\r\nConnection: close\r\n\r\n").encode()
        self._respond(head, f'GET -> {to} 301')

    def _begin_pause(self, wanted, path):
        if wanted and Settings.fileserver_allow_pause:
            self._pause = True
            self._pause_since_ms = now_ms()
            self.pause_what = path
            self.pause_end = ''

    def _file(self, full, size):
        """The file's first `size` bytes, one piece per next()."""
        left = size
        f = open(full, 'rb')
        try:
            while left > 0:
                data = f.read(min(self._chunk(), left))
                if not data:
                    break
                left -= len(data)
                yield data
        finally:
            f.close()

    def _day_raw(self, day_dir, day):
        """Header, then every hourly file of the day in order. Sizes are
        taken first (one stat per step) so the header can carry the total."""
        files = []
        total = 0
        for name in _listdir(day_dir):
            if not name.endswith('.csv'):
                continue
            st = _stat(day_dir + '/' + name)
            if st is not None and not _is_dir(st):
                files.append((day_dir + '/' + name, st[6]))
                total += st[6]
            yield b''
        self.what = f'GET /day/{day}/raw.csv ({len(files)} hours, {_human(total)})'
        yield _file_head(f'hydrapurr_raw_{day}_UTC.csv', total)
        for full, size in files:
            # yield from: closing this generator (client gone) also closes
            # the inner one and with it the open file.
            yield from self._file(full, size)

    def _start_page(self):
        """Start page: status, then one row per day (stats one per step)."""
        yield _head('HydraPurr')
        yield b"<h1>HydraPurr</h1>"
        if self.status:
            yield f"<p class='st'>{self.status}</p>".encode()
        days = set(_listdir(SD_ROOT + '/raw'))
        for name in _listdir(SD_ROOT + '/events'):
            if name.endswith('.csv'):
                days.add(name[:-4])
        days = sorted(days, reverse=True)
        allow = Settings.fileserver_allow_pause
        yield b"<h2>Download one day</h2>"
        yield (b"<p class='note'>Days and times are UTC (lab time in winter = UTC - 5 h). "
               b"<b>events</b>: one row per contact, a status row every 15 min (water, touch), restarts; "
               b"opens in Excel. <b>raw</b>: every sample (100 per second), for analysis "
               b"in Python; a full day is about 300 MB and too long for Excel.</p>")
        if allow:
            yield (b"<p class='note'>Recording goes on while you download "
                   b"(a full day of raw takes about 35 min).</p>"
                   b"<p class='warn'><b>fast stops the recording</b> until that download "
                   b"ends: about 3 times faster, but nothing (licks, water) is recorded "
                   b"meanwhile. The board's screen shows NOT REC in red; recording restarts "
                   b"by itself when the download ends or breaks off (after "
                   + str(Settings.fileserver_max_pause_ms // 60000).encode() +
                   b" min at the latest). Don't use it while a cat may drink.</p>")
        else:
            yield b"<p class='note'>Recording goes on while you download.</p>"
        yield b"<table><tr><th>day (UTC)</th><th>events</th><th class='r'></th><th>raw</th><th class='r'></th>"
        yield b"<th></th></tr>" if allow else b"</tr>"
        for day in days:
            ev = _stat(f"{SD_ROOT}/events/{day}.csv")
            yield b''
            raw_dir = f"{SD_ROOT}/raw/{day}"
            raw_total, hours = 0, 0
            for name in _listdir(raw_dir):
                st = _stat(raw_dir + '/' + name)
                if st is not None and not _is_dir(st):
                    raw_total += st[6]
                    hours += 1
                yield b''
            row = f"<tr><td>{day}</td>"
            if ev is not None:
                row += (f"<td><a href='/events/{day}.csv'>events</a></td>"
                        f"<td class='r'>{_human(ev[6])}</td>")
            else:
                row += "<td></td><td></td>"
            if hours:
                row += (f"<td><a href='/day/{day}/raw.csv'>raw</a></td>"
                        f"<td class='r'>{_human(raw_total)} ({hours} h)</td>")
                if allow:
                    mins = raw_total // (FAST_BYTES_PER_S * 60) + 1
                    row += (f"<td><a href='/day/{day}/raw.csv?pause=1' onclick=\"return "
                            f"confirm('This STOPS RECORDING for about {mins} min, until the "
                            f"download ends. Continue?')\">raw, fast (stops recording)</a></td>")
            else:
                row += "<td></td><td></td>" + ("<td></td>" if allow else "")
            yield (row + "</tr>").encode()
        yield b"</table>"
        yield (b"<p><a href='/files/'>All files on the card</a> "
               b"(hourly raw files, system log)</p></body></html>")

    def _listing(self, full, path):
        """HTML page for one folder, one row per next() (each needs a stat).
        Links are absolute paths, so the /files/ alias of the root works."""
        title = 'HydraPurr files' + ('' if path == '/' else f' {path}')
        yield _head(title)
        yield f"<h1>{title}</h1>".encode()
        if path == '/':
            yield b"<p><a href='/'>start page</a></p>"
        else:
            parent = path.rstrip('/').rsplit('/', 1)[0] + '/'
            up = '/files/' if parent == '/' else parent
            yield f"<p><a href='{up}'>up</a></p>".encode()
        yield b"<table>"
        for name in _listdir(full):
            st = _stat(full + '/' + name)
            if st is None:
                continue
            href = path + name
            if _is_dir(st):
                yield f'<tr><td><a href="{href}/">{name}/</a></td><td></td></tr>'.encode()
            else:
                yield (f'<tr><td><a href="{href}">{name}</a></td>'
                       f'<td style="text-align:right" data-size="{st[6]}">'
                       f'{_human(st[6])}</td></tr>').encode()
        yield b"</table></body></html>"
