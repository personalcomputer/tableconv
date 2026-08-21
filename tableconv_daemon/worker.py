"""Worker daemon entry point.

Launched by the supervisor (``tableconv_daemon/main.py``) via ``python -m
tableconv_daemon.worker`` -- NOT via the ``!!you-are-a-worker-daemon!!`` argv sentinel
(TODO #4). The supervisor passes the worker one end of a ``socket.socketpair()`` as a
file descriptor via the ``TABLECONV_DAEMON_CONTROL_FD`` environment variable; this is the
dedicated control channel (TODO #2b). Request/exit-code/abort frames flow over it.

Output capture
--------------
The worker's STDOUT/STDERR are connected to pipes created by the supervisor (via
``subprocess.Popen(stdout=..., stderr=...)``). The supervisor reads those pipes and frames
the bytes as ``out``/``err`` JSON Lines frames for the client.

This deliberately diverges from ARCHITECTURE_DAEMON_REFACTOR.md §3.4, which proposed
replacing ``sys.stdout``/``sys.stderr`` with in-worker ``FramedStream`` objects that write
``out``/``err`` frames to the control socket. That approach is **not sufficient on its
own**: several tableconv adapters open ``/dev/fd/1`` (and ``/dev/fd/2``) *directly* -- e.g.
``avro.py``, ``json.py`` (msgpack/bson), ``pandas_io.py``, ``yaml.py`` -- which bypasses
the Python ``sys.stdout`` object entirely and writes to the process's real fd 1. (The
doc's §3.4 "verified absences" scan looked for ``os.write(1, ...)`` etc. but missed
``open("/dev/fd/1", "wb")``.) Capturing fd 1/fd 2 with pipes catches *both* ``sys.stdout``
writes and direct ``/dev/fd/1`` writes, which is why the old PTY design worked for binary
output formats. Pipes preserve that without a PTY.

What we DO still override on ``sys.stdout``/``sys.stderr``/``sys.stdin`` is ``isatty()``
(see §3.6/§3.7): rich's ``is_terminal`` check is a Python-level ``file.isatty()`` call, so
returning the client's tty status makes rich colorize/box-draw exactly as it would
in-process -- no PTY, no ioctl required (verified: no ncurses in tableconv).
"""

import os
import sys
import traceback

from tableconv_daemon import protocol

# Terminal-related env keys reset per-request so a value from one client cannot leak into
# the next request's environment (the worker process persists across requests).
_TERMINAL_ENV_KEYS = protocol.TERMINAL_ENV_KEYS

# Captured once, before any per-request wrapping, so re-wrapping never nests wrappers.
_orig_stdout = sys.stdout
_orig_stderr = sys.stderr
_orig_stdin = sys.stdin


class _TtyStream:
    """Thin wrapper around a real std stream that overrides ``isatty()`` to reflect the
    client's terminal, while delegating all actual I/O to the underlying stream (which
    points at the supervisor-captured pipe)."""

    def __init__(self, underlying, isatty: bool) -> None:
        self._u = underlying
        self._isatty = isatty

    def write(self, s):
        return self._u.write(s)

    def flush(self):
        return self._u.flush()

    def isatty(self):
        return self._isatty

    def fileno(self):
        return self._u.fileno()

    @property
    def buffer(self):
        return self._u.buffer

    @property
    def encoding(self):
        return getattr(self._u, "encoding", "utf-8")

    @property
    def errors(self):
        return getattr(self._u, "errors", "strict")

    def writable(self):
        return True

    def readable(self):
        return hasattr(self._u, "read")

    def seekable(self):
        return False

    def close(self):
        # Never close the underlying stream: it persists across requests.
        pass

    @property
    def closed(self):
        return False

    def __getattr__(self, name):
        return getattr(self._u, name)


def _install_tty_overrides(isatty: bool) -> None:
    sys.stdout = _TtyStream(_orig_stdout, isatty)
    sys.stderr = _TtyStream(_orig_stderr, isatty)
    sys.stdin = _TtyStream(_orig_stdin, isatty)


def run_worker_daemon() -> None:
    ctrl_fd = int(os.environ["TABLECONV_DAEMON_CONTROL_FD"])
    # BufferedReader for readline()-based req parsing; closefd=False so closing the reader
    # does not close the underlying fd (we still write `end` frames to it via os.write).
    ctrl_reader = os.fdopen(ctrl_fd, "rb", closefd=False)

    # Heavy import happens once (warm start). tableconv.main is import-clean (no stdout
    # writes at import time), so this is safe to do before any request arrives.
    from tableconv.main import main_wrapper

    while True:
        try:
            req = protocol.read_frame(ctrl_reader)
        except Exception:
            traceback.print_exc()
            continue
        if req is None:
            # Supervisor closed the control socket; exit cleanly.
            break
        if req.get("t") != "req":
            # e.g. an `abort` frame received between requests; ignore and keep serving.
            continue

        try:
            os.chdir(req["cwd"])
        except Exception:
            traceback.print_exc()
            protocol.write_frame_fd(ctrl_fd, {"t": "end", "code": 1})
            continue

        # Reset then re-apply terminal env so per-client values don't leak across requests.
        for key in _TERMINAL_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(req.get("env", {}))

        tty_info = req.get("tty", {}) or {}
        _install_tty_overrides(bool(tty_info.get("isatty", False)))

        code = 0
        try:
            main_wrapper(req["argv"])
        except SystemExit as e:
            if e.code is None:
                code = 0
            elif isinstance(e.code, int):
                code = e.code
            else:
                code = 1
        except Exception:
            # Traceback goes to the (pipe-captured) stderr -> `err` frames -> client stderr.
            traceback.print_exc()
            code = 1
        finally:
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:
                pass

        protocol.write_frame_fd(ctrl_fd, {"t": "end", "code": code})


if __name__ == "__main__":
    run_worker_daemon()
