"""PyWebView + Streamlit desktop launcher for Incubrix Growth Engine."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import webview

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8501
APP = ROOT / "app.py"


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex((host, port)) == 0


def _wait_for_server(host: str, port: int, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.35)
    return False


def main() -> int:
    if not APP.exists():
        print(f"Missing Streamlit app: {APP}", file=sys.stderr)
        return 1

    # Reuse an already-running Streamlit instance when possible
    proc: subprocess.Popen | None = None
    if not _port_open(HOST, PORT):
        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(APP),
            "--server.headless=true",
            f"--server.port={PORT}",
            f"--server.address={HOST}",
            "--browser.gatherUsageStats=false",
            "--global.developmentMode=false",
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    if not _wait_for_server(HOST, PORT):
        if proc is not None:
            proc.terminate()
        print("Streamlit failed to start within timeout.", file=sys.stderr)
        return 1

    url = f"http://{HOST}:{PORT}"
    window = webview.create_window(
        title="Incubrix Growth Engine",
        url=url,
        width=1360,
        height=900,
        min_size=(1024, 700),
        background_color="#0f1419",
    )
    webview.start()

    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    _ = window
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
