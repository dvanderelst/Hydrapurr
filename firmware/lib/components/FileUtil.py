# lib/components/FileUtil.py
# Shared file/CSV utilities used by MyStore and MySystemLog.
import os


def count_lines(path, stop_at=None):
    """Count lines in a file, optionally stopping early at stop_at."""
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


def next_rotation_path(path, max_tries=10000):
    """Return the first path.<n> that does not exist yet, or None."""
    for i in range(1, max_tries + 1):
        candidate = f"{path}.{i}"
        try:
            os.stat(candidate)
        except OSError:
            return candidate
    return None


def escape_csv(value):
    """Escape a single value for CSV: quote if it contains , \" \\n or \\r."""
    if value is None:
        return ""
    s = str(value)
    if any(c in s for c in [",", "\"", "\n", "\r"]):
        s = "\"" + s.replace("\"", "\"\"") + "\""
    return s


def parse_csv_line(line, sep=","):
    """Parse one CSV line (handles quoted fields) into a list of strings."""
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
