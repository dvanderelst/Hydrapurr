# lib/components/MyStore.py
import os, board  # sdcardio/storage no longer needed here
import Settings
from components import MySD  # ← NEW: centralize SD ops
from components import TimeUtil

# ---------------------------------------------------------------------
# Global variables and constants
# ---------------------------------------------------------------------
path_separator = os.sep
separator = ','
mount_point = '/sd'
sd_is_mounted = False
time_labels = ["time", "mono_ms"]

# ---------------------------------------------------------------------
# Filesystem utilities (path helpers remain local)
# ---------------------------------------------------------------------
def ensure_dir(path):
    try:
        os.mkdir(path)
    except OSError:
        pass

def ensure_dir_recursive(path):
    if not path or path == '/': return
    parts = path.strip('/').split('/')
    cur = ''
    for p in parts:
        cur = (cur + '/' + p) if cur else '/' + p
        try: os.mkdir(cur)
        except OSError: pass

def mount_sd():
    """Compat wrapper to the new SD module; preserves old API."""
    global sd_is_mounted
    ok = bool(MySD.mount_sd_card())
    sd_is_mounted = ok
    return ok

def normalize_to_sd(name):
    if not name:
        name = "measurements.csv"
    n = name.replace('\\', '/')
    if n.startswith(mount_point + '/'):
        n = n[len(mount_point) + 1:]
    if n.startswith('/'):
        n = n[1:]
    return mount_point + '/' + n

def file_exists(path):
    try:
        with open(path, 'r'):
            return True
    except OSError:
        return False

def file_empty(path):
    try:
        return os.stat(path)[6] == 0
    except OSError:
        return True

def create_file(path):
    if not MySD.is_mounted():
        print("Warning: SD not mounted; create_file skipped")
        return False
    parent = '/'.join(path.split('/')[:-1])
    if parent and parent != '/': ensure_dir_recursive(parent)
    try:
        with open(path, 'w'): return True
    except OSError as e:
        print(f"Warning: Unable to create file. {e}"); return False

def write_line(path, line):
    if not MySD.is_mounted():
        print("Warning: SD not mounted; write_line skipped")
        return False
    try:
        with open(path, 'a') as f: f.write(str(line) + '\n'); return True
    except OSError as e:
        print(f"Warning: Unable to write line. {e}"); return False

def _escape_csv_cell(value):
    if value is None:
        return ""
    s = str(value)
    if any(c in s for c in [",", "\"", "\n", "\r"]):
        s = "\"" + s.replace("\"", "\"\"") + "\""
    return s

def _parse_csv_line(line, sep=","):
    fields = []
    if line is None:
        return fields
    s = str(line)
    cur = []
    in_quotes = False
    i = 0
    while i < len(s):
        ch = s[i]
        if in_quotes:
            if ch == "\"":
                if i + 1 < len(s) and s[i + 1] == "\"":
                    cur.append("\"")
                    i += 1
                else:
                    in_quotes = False
            else:
                cur.append(ch)
        else:
            if ch == "\"":
                in_quotes = True
            elif ch == sep:
                fields.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
        i += 1
    fields.append("".join(cur))
    return fields

def _coerce_cell(text):
    if text is None or text == "":
        return "" if text == "" else None
    if text.isdigit():
        return int(text)
    try:
        return float(text)
    except ValueError:
        return text

def write_list(path, lst):
    if not MySD.is_mounted():
        print("Warning: SD not mounted; write_list skipped")
        return False
    try:
        with open(path, 'a') as f: f.write(separator.join(_escape_csv_cell(x) for x in lst) + '\n'); return True
    except OSError as e:
        print(f"Warning: Unable to write list. {e}"); return False

def read_lines(path, split=True):
    if not MySD.is_mounted():
        print("Warning: SD not mounted; read_lines skipped")
        return False
    try:
        with open(path, 'r') as f: lines = [s.rstrip('\n') for s in f.readlines()]
        if not split: return lines
        out = []
        for s in lines:
            row = []
            for x in _parse_csv_line(s, separator):
                row.append(_coerce_cell(x))
            out.append(row)
        return out
    except OSError as e:
        print(f"Warning: Unable to read lines. {e}"); return False

def delete_file(name):
    """Delete a file via the new SD module."""
    return bool(MySD.delete(name))

def print_directory(path=mount_point, tabs=0):
    if not MySD.is_mounted():
        print("Warning: SD not mounted; print_directory skipped")
        return
    try: entries = os.listdir(path)
    except OSError as e:
        print(f"Unable to list {path}: {e}"); return
    for name in entries:
        if name == "?": continue
        full = path + "/" + name
        try: st = os.stat(full)
        except OSError: continue
        isdir = bool(st[0] & 0x4000); size = st[6]
        if isdir: sizestr = "<DIR>"
        elif size < 1000: sizestr = f"{size} bytes"
        elif size < 1_000_000: sizestr = f"{size/1000:.1f} KB"
        else: sizestr = f"{size/1_000_000:.1f} MB"
        print(f'{"   "*tabs}{name + ("/" if isdir else ""):<40} Size: {sizestr:>10}')
        if isdir: print_directory(full, tabs + 1)

# ---------------------------------------------------------------------
# Rotation helpers
# ---------------------------------------------------------------------
def _count_lines(path, stop_at=None):
    try:
        count = 0
        with open(path, "r") as f:
            for _ in f:
                count += 1
                if stop_at is not None and count >= stop_at:
                    break
        return count
    except OSError:
        return 0

def _next_rotation_path(path, max_tries=10000):
    for i in range(1, max_tries + 1):
        candidate = f"{path}.{i}"
        try:
            os.stat(candidate)
        except OSError:
            return candidate
    return None

# ---------------------------------------------------------------------
# Time handling
# ---------------------------------------------------------------------
def timestamp(fmt='iso', with_ms=True):
    return TimeUtil.timestamp(fmt, with_ms)

# ---------------------------------------------------------------------
# MyStore class
# ---------------------------------------------------------------------
class MyStore:
    """Logs time-stamped rows (CSV-like text format) to SD card."""

    def __init__(self, filename, fmt='iso', with_ms=True, auto_header=None, time_label=None, max_lines=None):
        mount_sd()
        self.file_name = filename
        self.file_path = normalize_to_sd(filename)
        self.fmt = fmt; self.with_ms = with_ms
        self.time_label = time_label if time_label is not None else list(time_labels)
        self._header = auto_header
        self._max_lines = max_lines if max_lines is not None else getattr(Settings, "data_log_max_lines", None)
        self._line_count = 0
        if MySD.is_mounted() and not file_exists(self.file_path): create_file(self.file_path)
        if auto_header: self.header(auto_header, label=self.time_label)
        if MySD.is_mounted() and self._max_lines:
            total = _count_lines(self.file_path, stop_at=self._max_lines + 1)
            self._line_count = max(total - 1, 0) if self._header else total
            if self._line_count >= self._max_lines:
                self._rotate_file()
                if self._header:
                    self.header(self._header, label=self.time_label)
                self._line_count = 0

    def empty(self):
        if not MySD.is_mounted(): return False
        ok = create_file(self.file_path)
        if ok:
            self._line_count = 0
        return ok

    def header(self, cols, label="time"):
        if cols is None or not MySD.is_mounted(): return
        if not file_empty(self.file_path): return
        if isinstance(label, (list, tuple)):
            row = list(label)
        else:
            row = [label]
        row += list(cols) if isinstance(cols, (list, tuple)) else [str(cols)]
        return write_list(self.file_path, row)

    def _rotate_file(self):
        if not MySD.is_mounted():
            print("Warning: SD not mounted; rotate skipped")
            return False
        if not file_exists(self.file_path):
            return create_file(self.file_path)
        rotated = _next_rotation_path(self.file_path)
        if rotated is None:
            print("Warning: No rotation slot available; rotate skipped")
            return False
        try:
            os.rename(self.file_path, rotated)
            return create_file(self.file_path)
        except OSError as e:
            print(f"Warning: Unable to rotate file. {e}")
            return False

    def add(self, data):
        if not MySD.is_mounted(): return False
        if self._max_lines and self._line_count >= self._max_lines:
            self._rotate_file()
            if self._header:
                self.header(self._header, label=self.time_label)
            self._line_count = 0
        ts, mono = TimeUtil.timestamp_pair(self.fmt, self.with_ms)
        row = list(data) if isinstance(data, (list,tuple)) else [data]
        ok = write_list(self.file_path, [ts, mono] + row)
        if ok and self._max_lines is not None:
            self._line_count += 1
        return ok

    def read(self, split=True):
        if not MySD.is_mounted(): return False
        return read_lines(self.file_path, split=split)

    def iter_lines(self, split=True):
        """Yield one line at a time (optionally split)."""
        if not MySD.is_mounted():
            print("Warning: SD not mounted; iter_lines skipped")
            return
        try:
            with open(self.file_path, 'r') as f:
                for line in f:
                    line = line.rstrip('\n')
                    if not split:
                        yield line
                    else:
                        parts = []
                        for x in _parse_csv_line(line, separator):
                            parts.append(_coerce_cell(x))
                        yield parts
        except OSError as e:
            print(f"Warning: Unable to iterate lines. {e}")
            return
