import json
import logging
import logging.config
import os
import select
import shlex
import shutil
import socket
import subprocess
import sys
import time

from tableconv_daemon import protocol

SELF_NAME = os.path.basename(sys.argv[0])
SOCKET_ADDR = "/tmp/tableconv-daemon.sock"
PIDFILE_PATH = "/tmp/tableconv-daemon.pid"
LOGFILE_PATH = "/tmp/tableconv-daemon.log"

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Worker process handle
# --------------------------------------------------------------------------- #
class _Worker:
    """Owns the long-lived worker child process and its three supervisor-side fds:
    the control socket (req/end/abort frames) and the stdout/stderr pipes (raw bytes
    that the supervisor frames as `out`/`err`)."""

    def __init__(self) -> None:
        out_r, out_w = os.pipe()
        err_r, err_w = os.pipe()
        parent_sock, child_sock = socket.socketpair()
        child_fd = child_sock.fileno()
        env = dict(os.environ)
        env["TABLECONV_MY_DAEMON_SUPERVISOR_PID"] = str(os.getpid())
        env["TABLECONV_DAEMON_CONTROL_FD"] = str(child_fd)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "tableconv_daemon.worker"],
            stdin=subprocess.DEVNULL,
            stdout=out_w,
            stderr=err_w,
            pass_fds=(child_fd,),
            env=env,
            close_fds=True,
        )
        os.close(out_w)
        os.close(err_w)
        child_sock.close()
        self.out_r = out_r
        self.err_r = err_r
        self.sock = parent_sock  # blocking socket; reads are select-guarded
        os.set_blocking(self.out_r, False)
        os.set_blocking(self.err_r, False)
        self._ctrl_buf = b""
        self._ctrl_eof = False

    def send(self, data: bytes) -> None:
        """Send raw frame bytes (a complete req/abort line) to the worker control socket."""
        self.sock.sendall(data)

    def read_ctrl_frames(self) -> list[dict]:
        """Read all currently-available complete frames from the control socket. Safe to
        call only when select() has reported the socket readable."""
        frames: list[dict] = []
        if self._ctrl_eof:
            return frames
        try:
            chunk = self.sock.recv(65536)
        except BlockingIOError:
            return frames
        except OSError:
            self._ctrl_eof = True
            return frames
        if not chunk:
            self._ctrl_eof = True
            return frames
        self._ctrl_buf += chunk
        while b"\n" in self._ctrl_buf:
            line, _, self._ctrl_buf = self._ctrl_buf.partition(b"\n")
            if line.strip():
                try:
                    frames.append(json.loads(line.decode("utf-8")))
                except json.JSONDecodeError:
                    logger.warning("Malformed control frame from worker: %r", line)
        return frames

    @property
    def ctrl_eof(self) -> bool:
        return self._ctrl_eof

    def alive(self) -> bool:
        return self.proc.poll() is None

    def kill(self) -> None:
        try:
            self.proc.kill()
        except ProcessLookupError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for fd in (self.out_r, self.err_r):
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            self.sock.close()
        except OSError:
            pass

    def respawn(self) -> "_Worker":
        self.kill()
        return _Worker()


# --------------------------------------------------------------------------- #
# Supervisor
# --------------------------------------------------------------------------- #
def _read_pipe(fd: int) -> bytes | None:
    """Read one chunk from a non-blocking pipe. Returns bytes (data), b'' (EOF -- writer
    closed), or None (would-block: no data right now)."""
    try:
        return os.read(fd, 65536)
    except BlockingIOError:
        return None
    except OSError:
        return b""


def _send_frame(client_conn, frame: dict) -> bool:
    try:
        client_conn.sendall(protocol.encode_frame(frame))
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def _drain_pipe_to_client(client_conn, fd: int, type_: str) -> bool:
    """Forward all currently-buffered pipe bytes to the client as payload frames. Returns
    False if the client disconnected, True otherwise."""
    while True:
        data = _read_pipe(fd)
        if data is None:
            return True
        if data == b"":
            # EOF on this pipe (worker closed it); nothing more to drain here.
            return True
        if not _send_frame(client_conn, protocol.make_payload_frame(type_, data)):
            return False


def _recv_line(sock: socket.socket) -> bytes:
    """Blocking read of one newline-terminated line. Returns b'' on EOF/error before a
    newline, else the line including the trailing b'\\n'."""
    buf = b""
    while b"\n" not in buf:
        try:
            chunk = sock.recv(65536)
        except OSError:
            return b""
        if not chunk:
            return b""
        buf += chunk
        if len(buf) > 4_000_000:
            logger.warning("Oversized request line from client; dropping.")
            return b""
    return buf[: buf.index(b"\n") + 1]


def handle_supervisor_daemon_request(worker: _Worker, client_conn: socket.socket) -> _Worker:
    debug_start_time = time.time()
    cmd = None
    try:
        req_line = _recv_line(client_conn)
        if not req_line:
            logger.info("Client disconnected before sending a complete request.")
            return worker
        try:
            req = json.loads(req_line.decode("utf-8"))
            cmd = f"{SELF_NAME} {shlex.join(req.get('argv', []))}"
        except json.JSONDecodeError:
            logger.warning("Malformed request from client; closing connection.")
            return worker

        # Forward the request to the worker; respawn if the worker died.
        try:
            worker.send(req_line)
        except (BrokenPipeError, ConnectionResetError, OSError):
            logger.info("Worker unreachable on request; respawning.")
            worker = worker.respawn()
            worker.send(req_line)

        logger.info(f"Dispatched request to worker. cmd: `{cmd}`")

        got_end = False
        end_code = 0
        client_gone = False
        worker_dead = False

        while not got_end and not client_gone and not worker_dead:
            try:
                readable, _, _ = select.select([client_conn, worker.sock, worker.out_r, worker.err_r], [], [], 1.0)
            except (OSError, ValueError):
                break

            # Process the control channel first: an `end` frame must take precedence over
            # a simultaneously-arriving client EOF (which would otherwise look like an
            # abnormal mid-request disconnect).
            if worker.sock in readable:
                for frame in worker.read_ctrl_frames():
                    if frame.get("t") == "end":
                        got_end = True
                        end_code = int(frame.get("code", 0) or 0)
                        break
                    # Any other control frame type is unexpected mid-request; ignore.

            if not got_end and worker.out_r in readable:
                data = _read_pipe(worker.out_r)
                if data == b"":
                    worker_dead = True
                elif data:
                    if not _send_frame(client_conn, protocol.make_payload_frame("out", data)):
                        client_gone = True

            if not got_end and not client_gone and worker.err_r in readable:
                data = _read_pipe(worker.err_r)
                if data == b"":
                    worker_dead = True
                elif data:
                    if not _send_frame(client_conn, protocol.make_payload_frame("err", data)):
                        client_gone = True

            if not got_end and not client_gone and client_conn in readable:
                # No stdin relay in v1: the only legitimate reason the client socket is
                # readable mid-response is that it closed (EOF). Treat any data as noise.
                try:
                    chunk = client_conn.recv(65536, socket.MSG_DONTWAIT)
                except BlockingIOError:
                    chunk = None
                except OSError:
                    chunk = b""
                if chunk == b"":
                    client_gone = True

        if got_end:
            # The worker flushed before sending `end`; drain any pipe bytes the relay
            # hadn't forwarded yet, then deliver the terminator.
            _drain_pipe_to_client(client_conn, worker.out_r, "out")
            _drain_pipe_to_client(client_conn, worker.err_r, "err")
            _send_frame(client_conn, {"t": "end", "code": end_code})
        elif worker_dead:
            # Worker crashed without sending `end`. Forward whatever it managed to write,
            # then synthesize an error + non-zero exit so the client fails loudly instead
            # of hanging (TODO #2b: input-blocking bugs are now observable).
            _drain_pipe_to_client(client_conn, worker.out_r, "out")
            _drain_pipe_to_client(client_conn, worker.err_r, "err")
            _send_frame(
                client_conn,
                protocol.make_payload_frame("err", b"tableconv daemon worker died unexpectedly\n"),
            )
            _send_frame(client_conn, {"t": "end", "code": 1})
            logger.warning("Worker died mid-request; respawning. cmd: `%s`", cmd)
            worker = worker.respawn()
        elif client_gone:
            # Client disconnected mid-request (e.g. Ctrl+C). Kill the worker so a stuck
            # request cannot stall subsequent requests; respawn a fresh warm worker.
            logger.info(f"Client disconnected early. cmd: `{cmd}`")
            worker = worker.respawn()

        debug_duration = round(1000 * (time.time() - debug_start_time))
        logger.info(f"Request complete after {debug_duration}ms. cmd: `{cmd}`")
        return worker
    finally:
        try:
            client_conn.close()
        except OSError:
            pass


def abort_if_daemon_already_running():
    if os.path.exists(SOCKET_ADDR):
        raise RuntimeError("Daemon already running?")


def run_supervisor_daemon():
    logger.info("Running as daemon")
    abort_if_daemon_already_running()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_ADDR)
    supervisor_pid = os.getpid()
    # Defer writing the PID file until after bind() so its existence is a valid readiness
    # indicator for kill_daemon / connect-retry (TODO #5).
    with open(PIDFILE_PATH, "w") as f:
        f.write(f"{supervisor_pid}\n")
    worker = None
    try:
        sock.listen(0)  # backlog 0: one client at a time (single worker, like before).
        worker = _Worker()
        logger.info(
            f"{SELF_NAME} daemon online, listening on {SOCKET_ADDR}. "
            f"Supervisor pid: {supervisor_pid}, Worker pid: {worker.proc.pid}"
        )
        while True:
            client_conn, _ = sock.accept()
            worker = handle_supervisor_daemon_request(worker, client_conn)
    finally:
        if worker is not None:
            try:
                worker.kill()
            except Exception:
                pass
        sock.close()
        for path in (SOCKET_ADDR, PIDFILE_PATH):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
def _connect_with_retry(timeout: float = 0.5):
    """Connect to the supervisor's Unix socket, retrying briefly to paper over the
    bind/listen readiness race right after --daemonize. Returns a connected socket or
    None (TODO #5: replaces time.sleep(0.5))."""
    deadline = time.time() + timeout
    last_err: Exception | None = None
    sock = None
    while time.time() < deadline:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(SOCKET_ADDR)
            return sock
        except (FileNotFoundError, ConnectionRefusedError) as e:
            last_err = e
            sock.close()
            time.sleep(0.05)
    if last_err is not None:
        logger.debug(f"Could not connect to daemon within {timeout}s: {last_err}")
    return None


def _write_bytes(stream, data: bytes) -> None:
    buf = getattr(stream, "buffer", None)
    if buf is not None:
        try:
            stream.flush()
        except Exception:
            pass
        buf.write(data)
        buf.flush()
    else:
        stream.write(data.decode("utf-8", errors="surrogateescape"))


def client_process_request_by_daemon(argv, startup_timeout: float = 0.0):
    """Forward an invocation to a running daemon. Returns the worker's exit code (int) on
    success, or None if no daemon is reachable (so the caller falls back to in-process)."""
    # Wait for the socket to appear if we just spawned the daemon (AUTO_DAEMON path).
    if startup_timeout > 0:
        deadline = time.time() + startup_timeout
        while time.time() < deadline and not os.path.exists(SOCKET_ADDR):
            time.sleep(0.05)

    if not os.path.exists(SOCKET_ADDR):
        return None  # No daemon.

    verbose = {"-v", "--verbose", "--debug"} & set(argv)  # No argparse/logging loaded yet.
    if verbose:
        logger.debug("Using tableconv daemon (run `tableconv --kill-daemon` to kill)")

    env: dict[str, str] = {}
    for key in protocol.TERMINAL_ENV_KEYS:
        if key in os.environ:
            env[key] = os.environ[key]
    # COLUMNS from the actual terminal takes precedence over any inherited value.
    try:
        env["COLUMNS"] = str(os.get_terminal_size().columns)
    except (OSError, ValueError):
        pass

    tty: dict[str, object] = {"isatty": sys.stdout.isatty()}
    if "COLUMNS" in env:
        try:
            tty["columns"] = int(env["COLUMNS"])
        except ValueError:
            pass

    req = {"t": "req", "argv": argv, "cwd": os.getcwd(), "env": env, "tty": tty}

    sock = _connect_with_retry()
    if sock is None:
        return None
    try:
        sock.sendall(protocol.encode_frame(req))
        reader = sock.makefile("rb")
        code = 0
        while True:
            frame = protocol.read_frame(reader)
            if frame is None:
                break  # Connection closed before `end`; treat as failure-ish.
            t = frame.get("t")
            if t == "out":
                _write_bytes(sys.stdout, protocol.extract_payload(frame))
            elif t == "err":
                _write_bytes(sys.stderr, protocol.extract_payload(frame))
            elif t == "end":
                code = int(frame.get("code", 0) or 0)
                break
        try:
            sys.stdout.flush()
        except Exception:
            pass
        try:
            sys.stderr.flush()
        except Exception:
            pass
        return code
    finally:
        try:
            reader.close()
        except Exception:
            pass
        sock.close()


def kill_daemon():
    try:
        with open(PIDFILE_PATH) as f:
            pid = int(f.read().strip())
    except FileNotFoundError:
        if os.path.exists(SOCKET_ADDR):
            raise RuntimeError(
                "Daemon appears to be running (unix domain socket found), but PID file not found! Failed to kill."
            ) from None
        logger.error("Daemon does not appear to be running (PID file not found).")
        return
    else:
        try:
            subprocess.run(["kill", "-INT", str(pid)], capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode()
            if "No such process" in err:
                clean_sock = os.path.exists(SOCKET_ADDR)
                logger.info(
                    f"Tried to send SIGINT to daemon, PID {pid}, but process is already dead. "
                    f"Cleaning up stale PID file{' and socket file' if clean_sock else ''}."
                )
                os.unlink(PIDFILE_PATH)
                if clean_sock:
                    os.unlink(SOCKET_ADDR)
        else:
            logger.info(f"Sent SIGINT to daemon, PID {pid}...")


def run_daemonize(log=True):
    abort_if_daemon_already_running()
    if log:
        logger.info(f"Forking daemon using `daemonize`. Daemon logs will be sent to {LOGFILE_PATH}.")
    exe_path = shutil.which(sys.argv[0]) or sys.argv[0]
    subprocess.run(
        ["daemonize", "-e", LOGFILE_PATH, exe_path, "--daemon"],
        check=True,
    )
    logger.info("To kill the daemon, `tableconv --kill-daemon` is provided as a convenience command.")


def set_up_logging():
    # Note: This config is duplicated within tableconv.main.set_up_logging. This config
    # applies to the daemon and daemon wrapper/client code; tableconv.main's applies to
    # real tableconv. tableconv_daemon is kept import-light so the daemon client path does
    # not pay the pandas import cost. (TODO #3 is made unnecessary by this refactor; see
    # ARCHITECTURE_DAEMON_REFACTOR.md §3.11.)
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(process)d][%(name)s] %(levelname)s: %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S %Z",
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "level": "DEBUG",
                    "formatter": "default",
                    "stream": "ext://sys.stderr",
                },
            },
            "root": {
                "level": "DEBUG",
                "handlers": ["default"],
            },
        }
    )


def main_wrapper():
    """
    Entry point for the ``tableconv`` CLI. Everything here is wrapper code for the optional
    daemon optimization (preloading tableconv into a background worker process to improve
    startup time) plus the client that talks to such a daemon.

    **Check tableconv.main.main to view the "real" tableconv entrypoint.**

    When running via the daemon there are three processes: the client, the supervisor
    daemon (accepts client connections on a Unix socket, relays to the worker), and the
    worker daemon (holds the warmed tableconv imports, runs ``tableconv.main.main_wrapper``
    per request). The supervisor and worker communicate over a dedicated control socket
    (req/end/abort frames) plus captured stdout/stderr pipes; see
    ``tableconv_daemon/worker.py`` and ``ARCHITECTURE_DAEMON_REFACTOR.md``.
    """
    set_up_logging()

    argv = sys.argv[1:]

    # Daemon management commands
    if "--daemon" in argv:  # Undocumented feature
        if len(argv) > 1:
            raise ValueError("ERROR: --daemon cannot be combined with any other options")
        try:
            return run_supervisor_daemon()
        except KeyboardInterrupt:
            logger.info("Received SIGINT. Terminated.")
            return

    if "--daemonize" in argv:
        if len(argv) > 1:
            raise ValueError("ERROR: --daemonize cannot be combined with any other options")
        return run_daemonize()
    if "--kill-daemon" in argv:  # Undocumented feature
        if len(argv) > 1:
            raise ValueError("ERROR: --kill-daemon cannot be combined with any other options")
        return kill_daemon()

    # Try running as daemon client.
    if "-i" not in argv and "--interactive" not in argv:  # Interactive mode bypasses the daemon.
        daemon_status = client_process_request_by_daemon(argv)
        if daemon_status is not None:
            return daemon_status
        elif os.environ.get("TABLECONV_AUTO_DAEMON"):  # Undocumented feature
            print("[Automatically forking daemon]", file=sys.stderr)
            print("[To kill daemon, run `unset TABLECONV_AUTO_DAEMON && tableconv --kill-daemon`]", file=sys.stderr)
            run_daemonize(log=False)
            return client_process_request_by_daemon(argv, startup_timeout=3.0)

    # No daemon available: run tableconv in-process.
    from tableconv.main import main_wrapper

    sys.exit(main_wrapper(argv))


if __name__ == "__main__":
    sys.exit(main_wrapper())
