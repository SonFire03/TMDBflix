#!/usr/bin/env python3

import json
import subprocess
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def fetch(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return r.status, r.read().decode("utf-8"), r.headers.get("Content-Type", "")


def wait_ready(timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            status, _, _ = fetch("/api/v1/health")
            if status == 200:
                return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    p = subprocess.Popen([".venv/bin/uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_ready(), "server not ready"

        s, b, ct = fetch("/")
        assert s == 200 and "text/html" in ct and "TMDB Explorer" in b

        s, b, _ = fetch("/api/v1/health")
        h = json.loads(b)
        assert h.get("ok") is True

        s, b, _ = fetch("/api/v1/tmdb?endpoint=/trending/movie/week")
        d = json.loads(b)
        assert "results" in d

        print("SMOKE TESTS: OK")
    finally:
        p.terminate()
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()


if __name__ == "__main__":
    main()
