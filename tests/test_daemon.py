"""Integration tests for the tableconv daemon IPC refactor (ARCHITECTURE_DAEMON_REFACTOR.md).

These spin up a real supervisor+worker daemon (subprocess) and exercise it end-to-end,
verifying: basic round-trip, rich colorized output preserved byte-for-byte, binary
output via the base64 path, non-zero exit-code propagation through the `end` frame,
the raw JSON Lines wire protocol, and daemon survival across a mid-request client
disconnect (worker kill + respawn).
"""

import fcntl
import os
import pty
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

from tableconv_daemon import protocol

SOCKET_ADDR = "/tmp/tableconv-daemon.sock"
PIDFILE_PATH = "/tmp/tableconv-daemon.pid"
FIXTURES = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _tableconv_cmd(args):
    return [sys.executable, "-m", "tableconv_daemon.main", *args]


def run_tableconv(args, env=None, stdin=None):
    """Run tableconv as a subprocess (daemon client if a daemon is up, else in-process)."""
    proc = subprocess.run(
        _tableconv_cmd(args),
        input=stdin,
        capture_output=True,
        env={**os.environ, **(env or {})},
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_tableconv_pty(args, env=None):
    """Run tableconv with its stdout/stderr attached to a pseudo-terminal (so isatty() is
    True and rich colorizes). Returns (returncode, output_bytes)."""
    master, slave = pty.openpty()
    # 120 cols x 24 rows, matching a typical terminal.
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 120, 0, 0))
    proc = subprocess.Popen(
        _tableconv_cmd(args),
        stdin=subprocess.DEVNULL,
        stdout=slave,
        stderr=slave,
        env={**os.environ, **(env or {})},
        close_fds=True,
    )
    os.close(slave)
    out = b""
    while True:
        try:
            data = os.read(master, 65536)
        except OSError:
            break
        if not data:
            break
        out += data
    proc.wait()
    os.close(master)
    return proc.returncode, out


def _stop_daemon():
    subprocess.run(
        _tableconv_cmd(["--kill-daemon"]),
        capture_output=True,
        timeout=10,
    )
    # Belt-and-suspenders cleanup of any stale state.
    for path in (SOCKET_ADDR, PIDFILE_PATH):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
    # Reap any stray worker.
    subprocess.run(["pkill", "-f", "tableconv_daemon.worker"], capture_output=True, timeout=5)


def _start_daemon():
    log = open("/tmp/tableconv-daemon-test.log", "ab")
    proc = subprocess.Popen(
        _tableconv_cmd(["--daemon"]),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        env={**os.environ},
        close_fds=True,
    )
    # Wait for the listening socket (supervisor binds before the worker import finishes).
    deadline = time.time() + 10
    while time.time() < deadline:
        if os.path.exists(SOCKET_ADDR):
            return proc
        if proc.poll() is not None:
            raise RuntimeError("daemon supervisor exited early; see /tmp/tableconv-daemon-test.log")
        time.sleep(0.02)
    raise RuntimeError("daemon did not come up in time")


def _wait_daemon_gone(timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and os.path.exists(SOCKET_ADDR):
        time.sleep(0.02)


@pytest.fixture
def daemon():
    """Start a fresh daemon for one test, then stop it."""
    _stop_daemon()
    _wait_daemon_gone()
    proc = _start_daemon()
    try:
        yield proc
    finally:
        _stop_daemon()
        _wait_daemon_gone()


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_basic_roundtrip(daemon):
    rc, out, err = run_tableconv([str(FIXTURES / "example.csv"), "-o", "tsv:-"])
    assert rc == 0
    assert out == b"id\tname\tdate\n1\tGeorge\t2023\n2\tSteven\t1950\n3\tRachel\t1995\n"
    assert err == b""


def test_nonzero_exit_code_propagated_and_streams_separated(daemon):
    rc, out, err = run_tableconv(["nonexistent.csv", "-o", "tsv:-"])
    assert rc != 0
    assert out == b""  # nothing on stdout
    assert b"nonexistent.csv" in err  # the error went to stderr
    assert b"InvalidLocationReferenceError" in err


def test_multiple_consecutive_requests_reuse_warm_worker(daemon):
    for _ in range(5):
        rc, out, _ = run_tableconv([str(FIXTURES / "example.csv"), "-o", "tsv:-"])
        assert rc == 0
        assert b"George" in out


def test_raw_jsonlines_wire_protocol(daemon):
    """Connect a raw socket, send a `req` frame, and parse the framed response."""
    import socket

    env = {"COLUMNS": "120", "TERM": "xterm-256color"}
    req = {
        "t": "req",
        "argv": [str(FIXTURES / "example.csv"), "-o", "tsv:-"],
        "cwd": os.getcwd(),
        "env": env,
        "tty": {"isatty": False, "columns": 120},
    }
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET_ADDR)
    try:
        sock.sendall(protocol.encode_frame(req))
        reader = sock.makefile("rb")
        frames = []
        while True:
            frame = protocol.read_frame(reader)
            if frame is None:
                break
            frames.append(frame)
            if frame.get("t") == "end":
                break
    finally:
        sock.close()

    types = [f["t"] for f in frames]
    assert types[-1] == "end"
    assert types[-1] == "end" and frames[-1]["code"] == 0
    # At least one out frame carrying the table data, and it round-trips through the
    # payload decoder to the exact expected bytes.
    out_bytes = b"".join(protocol.extract_payload(f) for f in frames if f["t"] == "out")
    assert out_bytes == b"id\tname\tdate\n1\tGeorge\t2023\n2\tSteven\t1950\n3\tRachel\t1995\n"
    # The out frame must be the readable 'd' form for utf-8 text output (no base64).
    out_frames = [f for f in frames if f["t"] == "out"]
    assert all("d" in f and "b" not in f for f in out_frames)


def test_colorized_rich_output_preserved_byte_for_byte():
    """Rich colorized output (asciirich) over the daemon must match in-process byte-for-byte,
    including SGR escape sequences and box-drawing characters (no PTY, no data loss)."""
    _stop_daemon()
    _wait_daemon_gone()
    # In-process reference with the pager disabled (the daemon path also skips the pager via
    # the TABLECONV_MY_DAEMON_SUPERVISOR_PID guard), so both render via a direct rich print.
    pty_env = {"TERM": "xterm-256color", "COLORTERM": "truecolor", "TABLECONV_MY_DAEMON_SUPERVISOR_PID": "1"}
    rc_ref, out_ref = run_tableconv_pty([str(FIXTURES / "example.csv"), "-o", "asciirich:/dev/fd/1"], env=pty_env)
    assert rc_ref == 0
    ESC = bytes([27]) + b"["
    assert out_ref.count(ESC) > 0, "in-process reference should be colorized"

    _start_daemon()
    try:
        rc, out = run_tableconv_pty(
            [str(FIXTURES / "example.csv"), "-o", "asciirich:/dev/fd/1"],
            env={"TERM": "xterm-256color", "COLORTERM": "truecolor"},
        )
        assert rc == 0
        assert out.count(ESC) > 0, "daemon output should be colorized"
        assert out == out_ref  # byte-for-byte preservation
    finally:
        _stop_daemon()
        _wait_daemon_gone()


def test_binary_output_base64_path_byte_for_byte():
    """A binary output format (msgpack) round-trips byte-for-byte via the base64 path."""
    _stop_daemon()
    _wait_daemon_gone()
    rc_ref, out_ref, _ = run_tableconv([str(FIXTURES / "example.csv"), "-o", "msgpack:-"])
    assert rc_ref == 0
    assert len(out_ref) > 0

    _start_daemon()
    try:
        rc, out, err = run_tableconv([str(FIXTURES / "example.csv"), "-o", "msgpack:-"])
        assert rc == 0
        assert out == out_ref  # byte-for-byte, including non-utf8 bytes via base64
    finally:
        _stop_daemon()
        _wait_daemon_gone()


def test_client_disconnect_does_not_kill_daemon(daemon):
    """A client that disconnects mid-request must not stall the daemon; the worker is killed
    and respawned so subsequent requests still succeed."""
    import socket

    # Send a req then immediately close (simulating Ctrl+C before reading the response).
    req = {
        "t": "req",
        "argv": [str(FIXTURES / "example.csv"), "-o", "tsv:-"],
        "cwd": os.getcwd(),
        "env": {"COLUMNS": "120"},
        "tty": {"isatty": False},
    }
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET_ADDR)
    sock.sendall(protocol.encode_frame(req))
    sock.close()

    # Give the supervisor a moment to notice the disconnect and respawn the worker.
    time.sleep(0.5)

    # The daemon must still serve subsequent requests.
    rc, out, _ = run_tableconv([str(FIXTURES / "example.csv"), "-o", "tsv:-"])
    assert rc == 0
    assert b"George" in out


def test_no_daemon_falls_back_to_in_process():
    """With no daemon running, tableconv runs in-process (no regression of the fallback)."""
    _stop_daemon()
    _wait_daemon_gone()
    rc, out, err = run_tableconv([str(FIXTURES / "example.csv"), "-o", "tsv:-"])
    assert rc == 0
    assert b"George" in out
