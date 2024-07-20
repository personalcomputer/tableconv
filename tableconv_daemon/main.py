import contextlib
import json
import logging
import logging.config
import os
import shlex
import socket
import subprocess
import sys
import time
import traceback

SELF_NAME = os.path.basename(sys.argv[0])
SOCKET_ADDR = "/tmp/tableconv-daemon.sock"
PIDFILE_PATH = "/tmp/tableconv-daemon.pid"


logger = logging.getLogger(__name__)


def handle_daemon_supervisor_request(daemon_proc, client_conn) -> None:
    import pexpect.exceptions

    logger.info("client connected.")
    debug_start_time = time.time()
    try:
        request_data = None
        while not request_data:
            request_data = client_conn.recv(4096)

        daemon_proc.sendline(request_data)
        _ = daemon_proc.readline()  # ignore stdin playback (?)
        while True:
            with contextlib.suppress(pexpect.exceptions.TIMEOUT):
                response = daemon_proc.read_nonblocking(4096, timeout=0.05)
                if response:
                    client_conn.sendall(response)
                if response[-1] == 0:
                    # Using ASCII NUL (0) temporarily as a sentinal value to indicate end-of-file. TODO: Need to upgrade
                    # this to a proper streaming protocol with frames so we can send a more complete end message,
                    # including the status code and distinguishing between STDOUT and STDERR.
                    break
    finally:
        client_conn.close()
    debug_duration = round(time.time() - debug_start_time, 2)
    cmd = f'{sys.argv[0]} {shlex.join(json.loads(request_data)["argv"])}'
    logger.info(f"client disconnected after {debug_duration}s. cmd: {cmd}")


def run_daemon_supervisor():
    logger.info("Running as daemon")
    if os.path.exists(SOCKET_ADDR):
        raise RuntimeError("Daemon already running?")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_ADDR)
    with open(PIDFILE_PATH, "w") as f:
        f.write(f"{os.getpid()}\n")
    try:
        sock.listen(0)  # Note: daemon as-is can only handle one client at a time, backlog arg of 0 disables queing.
        import pexpect

        daemon_proc = pexpect.spawn(sys.argv[0], args=["!!you-are-a-daemon!!"])
        logger.info(f"{SELF_NAME} daemon online, listening on {SOCKET_ADDR}")
        while True:
            client_conn, _ = sock.accept()
            handle_daemon_supervisor_request(daemon_proc, client_conn)
    finally:
        sock.close()
        os.unlink(SOCKET_ADDR)
        os.unlink(PIDFILE_PATH)


def run_daemon():
    from tableconv.main import main

    while True:
        try:
            data = json.loads(sys.stdin.readline())
            # os.environ = data['environ']
            os.chdir(data["cwd"])
            main(data["argv"])
        except Exception:
            traceback.print_exc()
        except SystemExit:
            continue
        finally:
            sys.stdout.write("\0")
            sys.stdout.flush()


def client_process_request_by_daemon(argv):
    if not os.path.exists(SOCKET_ADDR):
        # Daemon not online!
        return None

    verbose = {"-v", "--verbose", "--debug"} & set(argv)  # Hack.. no argparse or logging.config loaded yet
    if verbose:
        logger.debug("Using tableconv daemon (run `tableconv --kill-daemon` to kill)")

    raw_request_msg = json.dumps(
        {
            "argv": argv,
            # 'environ': dict(os.environ),
            "cwd": os.getcwd(),
        }
    ).encode()

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET_ADDR)
    try:
        sock.sendall(raw_request_msg)
        while True:
            response_part = sock.recv(4096)
            sys.stdout.write(response_part.decode())
            sys.stdout.flush()
            if not response_part or response_part[-1] == "\0":
                break
    finally:
        sock.close()

    return 0  # process status code 0


def kill_daemon():
    try:
        with open(PIDFILE_PATH, "r") as f:
            pid = int(f.read().strip())
    except FileNotFoundError:
        if os.path.exists(SOCKET_ADDR):
            raise RuntimeError(
                "Daemon appears to be running (unix domain socket found), but PID file not found! Failed to kill."
            )
        logger.error("Daemon does not appear to be running (PID file not found).")
        return
    else:
        try:
            subprocess.run(["kill", "-INT", str(pid)], stderr=subprocess.PIPE, stdout=subprocess.PIPE, check=True)
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
    if log:
        logger.info("Forking daemon using `daemonize`. Daemon logs piped to /tmp/tableconv-daemon.log.")
    os.system(f"daemonize -e /tmp/tableconv-daemon.log $(which {sys.argv[0]}) --daemon")


def set_up_logging():
    # Note: This config is duplicated within tableconv.main.set_up_logging. The idea is that _this- config applies to
    # the daemon and daemon wrapper/client code, and that the tableconv.main config applies to real tableconv. I do not
    # want anyone to need to read any part of tableconv_daemon UNLESS they are specifically working on the daemon /
    # daemon-client related code. That means 100% of actual tableconv behavior must be defined in the real tableconv
    # module. (& I cannot import from that module into tableconv_daemon because then the daemon client code will end up
    # loading __init__.py which right now has expensive external imports. tableconv_daemon needs to have the minimum
    # possible imports in order to acheive fast startup times.)
    # TODO: remove the expensive tableconv __init__ imports. Figure out alternative python api to allow avoiding them.
    # Perhaps repurposing `tableconv` to be the API only, and creating new module, tableconv_cli, to host the tableconv
    # cli code, with no __init__.py?
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
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
    This is _technically_ the entrypoint for tableconv if ran from the CLI. However, everything in this file is merely
    just low quality experimental wrapper code for providing the optional feature of preloading the tableconv Python
    libraries into a background daemon process (to improve startup time), and the corresponding code also to invoke any
    already-spun-up daemon.

    **Check tableconv.main.main to view the "real" tableconv entrypoint.**
    """
    set_up_logging()

    argv = sys.argv[1:]

    # Daemon management commands
    if "--daemon" in argv:
        if len(argv) > 1:
            raise ValueError("ERROR: --daemon cannot be combined with any other options")
        try:
            return run_daemon_supervisor()
        except KeyboardInterrupt:
            logger.info("Received SIGINT. Terminated.")
            return
        # Note: When running tableconv as a daemon, there are three processes runnning: the client, the daemon, and the
        # _daemon supervisor_. For ease of communication, in the tableconv UI we oversimplify and refer to both the
        # daemon supervisor and the daemon beneath it simply as the "daemon", but within the code you can see that what
        # we actually run is the supervisor, which then runs the daemon. (Also: if you invoke via --daemonize, you
        # actually get 4 processes!)
    if argv in [["--daemonize"], ["--spawn-daemon"]]:  # Undocumented feature
        return run_daemonize()
    if argv == ["--kill-daemon"]:  # Undocumented feature
        return kill_daemon()
    if argv == ["!!you-are-a-daemon!!"]:
        # TODO use a alternative entry_point console_script instead of this sentinel value? I don't want to pollute the
        # end-user's PATH with another command though, this is not something an end user should ever directly run.
        # TODO: Using alternative entry point does not require adding pollution to PATH. I can just direcctly invoke a
        # python file relative to this python file - i.e. anothe rpython file within the tableconv _install directory_,
        # not within PATH.
        return run_daemon()

    # Try running as daemon client
    daemon_status = client_process_request_by_daemon(argv)
    if daemon_status is not None:
        return daemon_status
    elif os.environ.get("TABLECONV_AUTO_DAEMON"):  # Undocumented feature
        print("[Automatically forking daemon for future invocations]", file=sys.stderr)
        print("[To kill daemon, run `unset TABLECONV_AUTO_DAEMON && tableconv --kill-daemon`]", file=sys.stderr)
        run_daemonize(log=False)

    # Runinng as daemon client failed, so run tableconv normally, run within this process.
    from tableconv.main import main

    sys.exit(main(argv))
