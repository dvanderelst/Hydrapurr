"""
hydrapurr_fetch.py - copy the HydraPurr's SD card over WiFi

The board serves its SD card at http://hydrapurr.local/files/ (firmware/
lib/FileServer.py), one HTML page per folder. fetch() walks those pages and
downloads every file that is missing locally or whose size differs (the
pages carry the exact size as data-size="..."). Finished hourly raw files
never change, so after the first run only the current hour's raw file,
today's events file and the logs are fetched again.

Local files are never overwritten with different content (2026-11-23: a
cleared card replaced the local events file of the day). A board file
replaces the local one only when it starts with the local file's bytes,
i.e. it is the same file grown longer. Otherwise (another card, a log that
rotated, the same hour written again after a card swap) the local file
stays and the board's one is saved next to it: `2026-11-23~2.csv`,
`16~2.csv`, `system.log~2` (then ~3, ...). Later fetches grow that side copy
the same way. hydrapurr_reader reads the side copies too.

The board keeps recording while it serves (~125-150 KB/s, so a full hourly
raw file takes ~1-2 min). Use include_raw=False to fetch only events and
logs. pause=True asks the board to stop recording while each raw file is
sent (~310 KB/s, 2.5x faster; a `paused`/`resumed` event pair per file, and
the data of those minutes is missing). Events files and logs are always
fetched alongside recording. A board with fileserver_allow_pause = False
ignores the request and serves at the normal speed.

    from library.hydrapurr_fetch import fetch
    fetch()                                  # -> data/v2_esp32s3_touch/
    fetch(include_raw=False)                 # events + logs only
    fetch(pause=True)                        # faster, recording pauses

Command line (from analysis/):
    python -m library.hydrapurr_fetch [--no-raw] [--pause] [--days 2026-11-16]
                                      [--url http://<board ip>/]
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://hydrapurr.local/"
DEFAULT_DEST = Path(__file__).resolve().parent.parent / "data" / "v2_esp32s3_touch"
TIMEOUT_S = 30

_ROW = re.compile(r"<tr>(.*?)</tr>")
_HREF = re.compile(r'href="([^"]+)"')
_SIZE = re.compile(r'data-size="(\d+)"')


def _rows(page: str) -> list[tuple[str, int | None]]:
    out = []
    for row in _ROW.findall(page):
        href = _HREF.search(row)
        if href is None:
            continue
        size = _SIZE.search(row)
        out.append((href.group(1), int(size.group(1)) if size else None))
    return out


def _finished(path: str) -> bool:
    """True for a file the board no longer writes: an hourly raw file of an
    earlier hour, an events file of an earlier day (board clock = UTC)."""
    now = time.gmtime()
    m = re.fullmatch(r"/raw/(\d{4}-\d{2}-\d{2})/(\d{2})\.csv", path)
    if m:
        return (m.group(1), m.group(2)) < (time.strftime("%Y-%m-%d", now),
                                           time.strftime("%H", now))
    m = re.fullmatch(r"/events/(\d{4}-\d{2}-\d{2})\.csv", path)
    if m:
        return m.group(1) < time.strftime("%Y-%m-%d", now)
    return False


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
        return r.read()


def list_remote(url: str = DEFAULT_URL, path: str = "/files/") -> list[tuple[str, int | None]]:
    """All files on the card as (path, size in bytes or None), depth first.
    The folder pages start at /files/ (/ is the start page for testers);
    their links are absolute paths. Older board versions served the root
    folder at / with relative links: both are handled."""
    try:
        page = _get(url.rstrip("/") + path).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if path == "/files/" and e.code == 404:
            return list_remote(url, "/")       # board without the start page
        raise
    base = "/" if path == "/files/" else path
    files = []
    for href, size in _rows(page):
        if href.startswith(".."):
            continue
        full = href if href.startswith("/") else base + href
        if not full.startswith(base) or full == base:
            continue                           # up / start-page links
        if full.endswith("/"):
            files.extend(list_remote(url, full))
        else:
            files.append((full, int(size) if size else None))
    return files


def _side_name(local: Path, n: int) -> Path:
    """2026-11-23.csv -> 2026-11-23~2.csv; system.log -> system.log~2."""
    if local.suffix == ".csv":
        return local.with_name(f"{local.stem}~{n}.csv")
    return local.with_name(f"{local.name}~{n}")


def _copies(local: Path) -> list[Path]:
    """The local file and its existing side copies, in order."""
    out = [local] if local.exists() else []
    n = 2
    while _side_name(local, n).exists():
        out.append(_side_name(local, n))
        n += 1
    return out


def _target(local: Path, data: bytes) -> tuple[Path | None, str]:
    """Where the board's data goes: (path, how) with how 'new', 'grown' or
    'side'; (None, 'same') when a local copy already holds exactly this."""
    copies = _copies(local)
    for c in copies:
        old = c.read_bytes()
        if old == data:
            return None, "same"
        if data.startswith(old):
            return c, "grown"
    if not copies:
        return local, "new"
    return _side_name(local, len(copies) + 1), "side"


def fetch(dest: str | Path = DEFAULT_DEST, url: str = DEFAULT_URL,
          include_raw: bool = True, raw_days: list[str] | None = None,
          pause: bool = False, verbose: bool = True) -> list[Path]:
    """Download new or changed files into dest. Returns the paths fetched.
    raw_days limits the raw files to those days ('YYYY-MM-DD'); events and
    logs are always fetched. pause: the board stops recording while each
    raw file is sent (faster)."""
    dest = Path(dest)
    fetched = []
    files = list_remote(url)
    todo = []
    for path, size in files:
        if path.startswith("/raw/"):
            if not include_raw:
                continue
            if raw_days is not None and path.split("/")[2] not in raw_days:
                continue
        local = dest / path.lstrip("/")
        copies = _copies(local)
        if copies:
            if size is not None and any(c.stat().st_size == size for c in copies):
                continue          # a local copy has this size: assume the same
                                  # (sizes are the only check without a download;
                                  # a growing file is fetched once they differ)
            if size is None and _finished(path):
                continue          # page without exact sizes: trust finished files
        todo.append((path, size, local))
    if verbose:
        total = sum(s or 0 for _, s, _ in todo)
        print(f"{len(files)} files on the board, {len(todo)} to fetch "
              f"({total / 1e6:.1f} MB)" + (", recording paused per raw file" if pause else ""))
    for path, size, local in todo:
        local.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()
        query = "?pause=1" if pause and path.startswith("/raw/") else ""
        data = _get(url.rstrip("/") + path + query)
        target, how = _target(local, data)
        if target is not None:
            tmp = target.with_name(target.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(target)
            fetched.append(target)
        if verbose:
            took = time.monotonic() - t0
            note = {"side": f"  -> kept the local file, saved as {target.name}",
                    "same": "  (unchanged)"}.get(how, "")
            print(f"  {path}  {len(data) / 1e6:.2f} MB  {took:.1f} s{note}")
    return fetched


def main():
    parser = argparse.ArgumentParser(description="Mirror the HydraPurr SD card over WiFi")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--dest", default=str(DEFAULT_DEST))
    parser.add_argument("--no-raw", action="store_true", help="events and logs only")
    parser.add_argument("--days", nargs="*", help="raw files of these days only (YYYY-MM-DD)")
    parser.add_argument("--pause", action="store_true",
                        help="board stops recording while each raw file is sent (faster)")
    args = parser.parse_args()
    fetch(args.dest, args.url, include_raw=not args.no_raw, raw_days=args.days,
          pause=args.pause)


if __name__ == "__main__":
    main()
