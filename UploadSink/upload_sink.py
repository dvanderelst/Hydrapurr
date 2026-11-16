#!/usr/bin/env python3
"""
upload_sink.py - receiver for the board's WiFi upload speed test

Run on a computer on the same network as the board:

    python3 UploadSink/upload_sink.py          # listens on port 5001

It accepts TCP connections, throws the data away, and prints the received
rate once per second per connection. Its addresses are printed at startup:
put the one on the home network in the board's settings.toml as
UPLOAD_TEST_HOST, then hold D2 while the board starts (Simplified/TestUpload.py).

If nothing arrives, check the computer's firewall (e.g. `sudo ufw allow 5001/tcp`).
"""

import argparse
import socket
import subprocess
import threading
import time


def local_addresses():
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout
        return [a for a in out.split() if ":" not in a]
    except OSError:
        return [socket.gethostbyname(socket.gethostname())]


def handle(conn, peer):
    name = f"{peer[0]}:{peer[1]}"
    print(f"{time.strftime('%H:%M:%S')}  {name} connected")
    total = 0
    window = 0
    window_start = time.monotonic()
    with conn:
        while True:
            try:
                data = conn.recv(65536)
            except OSError as e:
                print(f"{time.strftime('%H:%M:%S')}  {name} error: {e}")
                break
            if not data:
                break
            total += len(data)
            window += len(data)
            now = time.monotonic()
            if now - window_start >= 1.0:
                kb_s = window / 1024 / (now - window_start)
                print(f"{time.strftime('%H:%M:%S')}  {name}  {kb_s:7.1f} KB/s  "
                      f"total {total / 1024 / 1024:.2f} MB")
                window = 0
                window_start = now
    print(f"{time.strftime('%H:%M:%S')}  {name} closed after {total / 1024 / 1024:.2f} MB")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", args.port))
    server.listen()
    print(f"upload sink listening on port {args.port}; this computer: "
          f"{', '.join(local_addresses())}")
    try:
        while True:
            conn, peer = server.accept()
            threading.Thread(target=handle, args=(conn, peer), daemon=True).start()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
