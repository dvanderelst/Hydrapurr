# lib/components/MySystemLog.py
# Minimal logger: prefer SD (/sd), else console. Uses components.MySD for mounting.
import Settings
from components import MySD  # ← NEW
from components import TimeUtil

DEBUG = 10
INFO  = 20
WARN  = 30
ERROR = 40

_level = INFO
_sink = None
_sd_ok = False
_mirror_to_console = True
_mount_point = "/sd"
_log_path = None  # actual file path in use

# small in-memory ring buffer so you can read logs during runtime
_mem_buf = []
_mem_max = 500  # number of recent lines to keep

# ---------------- basics ----------------

_csv_lines = True  # If True: "time,mono_ms,LEVEL,msg"; else legacy "[time] LEVEL: msg"

def _count_lines(path, stop_at=None):
    try:
        count = 0
        with open(path, "r") as f:
            for _ in f:
                count += 1
                if stop_at is not None and count >= stop_at:
                    break
        return count
    except Exception:
        return 0

def _next_rotation_path(path, max_tries=10000):
    try:
        import os
        for i in range(1, max_tries + 1):
            candidate = f"{path}.{i}"
            try:
                os.stat(candidate)
            except OSError:
                return candidate
    except Exception:
        return None
    return None

def set_csv_lines(flag):
    """If True, lines are 'time,mono_ms,LEVEL,msg'. If False, keep bracket style."""
    global _csv_lines
    _csv_lines = bool(flag)

def set_system_log_level(level):
    """Set minimum level to emit: DEBUG, INFO, WARN, ERROR."""
    global _level
    _level = int(level)

def get_level():
    return _level

def set_mirror_to_console(flag):
    global _mirror_to_console
    _mirror_to_console = bool(flag)

def set_mem_max(n):
    global _mem_max
    try:
        _mem_max = int(n)
    except:
        pass

def _escape_csv(text):
    if text is None:
        return ""
    s = str(text)
    if any(c in s for c in [",", "\"", "\n", "\r"]):
        s = "\"" + s.replace("\"", "\"\"") + "\""
    return s

def _fmt(level_name, msg):
    # Normalize level text and choose format
    lvl = (level_name or "").strip()
    ts, mono = TimeUtil.timestamp_pair('iso', True)
    if _csv_lines:
        # CSV-style with monotonic wall time + raw monotonic (ms)
        return f"{ts},{mono},{_escape_csv(lvl)},{_escape_csv(msg)}"
    else:
        # Legacy bracketed style
        return f"[{ts}] {lvl}: {msg}"

def _emit(line):
    global _mem_buf
    if _sink:
        try:
            _sink(line)
        except:
            pass
    # keep a RAM mirror for quick access
    try:
        _mem_buf.append(line)
        if len(_mem_buf) > _mem_max:
            _mem_buf.pop(0)
    except:
        pass

# joiner that behaves like print(*parts)
_def_join = lambda parts: " ".join(str(p) for p in parts)

# ---- public logging API (varargs) ----

def debug(*parts):
    if _level <= DEBUG:
        _emit(_fmt("DEBUG", _def_join(parts)))

def info(*parts):
    if _level <= INFO:
        _emit(_fmt("INFO", _def_join(parts)))

def warn(*parts):
    if _level <= WARN:
        _emit(_fmt("WARN", _def_join(parts)))

def error(*parts):
    if _level <= ERROR:
        _emit(_fmt("ERROR", _def_join(parts)))

def critical(*parts):
    msg = _def_join(parts)
    error(msg)
    raise RuntimeError(msg)

# Optional printf-style helpers

def infof(fmt, *args):
    try:
        info(fmt % args)
    except Exception:
        info(fmt, *args)

def debugf(fmt, *args):
    try:
        debug(fmt % args)
    except Exception:
        debug(fmt, *args)

def warnf(fmt, *args):
    try:
        warn(fmt % args)
    except Exception:
        warn(fmt, *args)

def errorf(fmt, *args):
    try:
        error(fmt % args)
    except Exception:
        error(fmt, *args)

# ---------------- sinks ----------------

class _PrintSink:
    def __call__(self, line):
        print(line)

    def flush(self):
        try:
            import sys
            sys.stdout.flush()
        except:
            pass

class _SDSink:
    def __init__(self, path="/sd/system.log", autosync=False, keep_open=True, max_lines=None):
        self.path = path
        self.autosync = autosync
        self.keep_open = keep_open
        self._max_lines = max_lines
        self._line_count = 0
        self._fh = open(self.path, "a") if keep_open else None
        if self._max_lines:
            total = _count_lines(self.path, stop_at=self._max_lines + 1)
            self._line_count = total
            if self._line_count >= self._max_lines:
                self._rotate_file()
                self._line_count = 0

    def __call__(self, line):
        try:
            if self._max_lines and self._line_count >= self._max_lines:
                self._rotate_file()
                self._line_count = 0
            if self.keep_open:
                self._fh.write(line + "\n")
                if self.autosync:
                    try:
                        self._fh.flush()
                        import os
                        try: os.sync()
                        except: pass
                    except: pass
            else:
                with open(self.path, "a") as f:
                    f.write(line + "\n")
                    if self.autosync:
                        try:
                            f.flush()
                            import os
                            try: os.sync()
                            except: pass
                        except: pass
            if self._max_lines is not None:
                self._line_count += 1
        except Exception as e:
            try: print("[MySystemLog] SD write failed:", repr(e))
            except: pass

    def flush(self):
        if self.keep_open and self._fh:
            try:
                self._fh.flush()
                import os
                try: os.sync()
                except: pass
            except: pass

    def close(self):
        try:
            if self._fh:
                self._fh.flush()
                self._fh.close()
        except: pass
        self._fh = None

    def _rotate_file(self):
        try:
            if self._fh:
                self._fh.flush()
                self._fh.close()
        except:
            pass
        rotated = _next_rotation_path(self.path)
        if rotated is None:
            try: print("[MySystemLog] No rotation slot available; rotate skipped")
            except: pass
            return False
        try:
            import os
            os.rename(self.path, rotated)
            if self.keep_open:
                self._fh = open(self.path, "a")
            return True
        except Exception as e:
            try: print("[MySystemLog] rotate failed:", repr(e))
            except: pass
            return False

class _TeeSink:
    def __init__(self, *sinks):
        self.sinks = list(sinks)
    def __call__(self, line):
        for s in self.sinks:
            try: s(line)
            except: pass
    def flush(self):
        for s in self.sinks:
            if hasattr(s, "flush"):
                try: s.flush()
                except: pass
    def close(self):
        for s in self.sinks:
            if hasattr(s, "close"):
                try: s.close()
                except: pass

# ---------------- setup / teardown ----------------

def setup_system_log(autosync=True, keep_open=True, quiet=False):
    """Initialize logging. Returns True if logging to SD, else False (console-only)."""
    filename = Settings.system_log_filename
    max_lines = getattr(Settings, "system_log_max_lines", None)
    global _sink, _sd_ok, _log_path

    # Use the new SD module
    _sd_ok = bool(MySD.mount_sd_card())

    # Determine path (absolute vs relative to mount point)
    if filename.startswith("/"):
        path = filename
    else:
        path = f"{_mount_point.rstrip('/')}/{filename}"

    if _sd_ok and MySD.is_mounted():
        _log_path = path
        try:
            sd_sink = _SDSink(path, autosync=autosync, keep_open=keep_open, max_lines=max_lines)
            _sink = _TeeSink(sd_sink, _PrintSink()) if _mirror_to_console else sd_sink
            if not quiet: info("[MySystemLog] Logging to SD:", path)
            return True
        except Exception as e:
            print("[MySystemLog] SD sink init failed:", repr(e))

    # fallback to console
    _log_path = None
    _sink = _PrintSink()
    info("[MySystemLog] SD not available → console-only")
    return False

def flush():
    """Force a flush to SD if possible."""
    try:
        obj = _sink
        if hasattr(obj, "flush"): obj.flush()
    except: pass

def teardown():
    """Close SD sink (if open)."""
    global _sink
    try:
        obj = _sink
        if hasattr(obj, "close"): obj.close()
    except: pass

# ---------------- utilities: clear / read / tail / snapshot ----------------

def clear_system_log():
    """Erase the system log file if using SD; recreate sink after clearing."""
    global _sink, _sd_ok, _log_path
    if not (_sd_ok and _log_path and MySD.is_mounted()):
        print("[MySystemLog] No SD log to clear")
        return False
    try:
        obj = _sink
        if hasattr(obj, "close"): obj.close()
    except: pass
    try:
        with open(_log_path, "w") as f: f.write("")
        setup_system_log(autosync=True, keep_open=True, quiet=True)
        info("[MySystemLog] System log cleared")
        return True
    except Exception as e:
        print("[MySystemLog] Clear failed:", repr(e))
        return False

def _resolve_path(default_name="system.log"):
    if _log_path: return _log_path
    return f"{_mount_point.rstrip('/')}/{default_name}"

def read_log(last_n=None):
    """Return log lines as list[str]. Falls back to memory if file not accessible."""
    try: flush()
    except: pass
    path = _resolve_path()
    try:
        with open(path, "r") as f:
            lines = [s.rstrip("\n") for s in f.readlines()]
        return lines[-last_n:] if (last_n and last_n > 0) else lines
    except Exception:
        return _mem_buf[-last_n:] if (last_n and last_n > 0) else list(_mem_buf)

def tail(n=100):
    return read_log(last_n=n)

def tail_to_console(n=100, prefix="> "):
    lines = tail(n)
    for ln in lines:
        try: print(prefix + ln)
        except: pass
    return len(lines)

def snapshot_log(to_path=None, last_n=None):
    """Write a snapshot of the log to a file (default: /sd/system.snapshot.log)."""
    lines = read_log(last_n=last_n)
    if to_path is None:
        to_path = f"{_mount_point.rstrip('/')}/system.snapshot.log"
    try:
        with open(to_path, "w") as f:
            for ln in lines: f.write(ln + "\n")
        return len(lines)
    except Exception:
        return len(lines)

def get_memory_log(last_n=None):
    """Return only the in-memory buffer (ignores file)."""
    return _mem_buf[-last_n:] if (last_n and last_n > 0) else list(_mem_buf)

def sd_available():
    return _sd_ok and MySD.is_mounted()
