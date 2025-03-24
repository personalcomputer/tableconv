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
LOGFILE_PATH = "/tmp/tableconv-daemon.log"
CRASHLOGFILE_PATH = "/tmp/tableconv-daemon.crash.log"


logger = logging.getLogger(__name__)

EOF_SENTINEL = b"\0"


def handle_daemon_supervisor_request(daemon_proc, client_conn) -> None:
    import contextlib
    import base64
    import pexpect.exceptions

    logger.info("Client connected.")
    debug_start_time = time.time()
    cmd = None
    try:
        request_data = b''
        while True:
            new_data = client_conn.recv(1024)
            if not new_data:
                logger.info("Lost connection to client before receiving complete request.")
                return
            request_data += new_data
            if request_data[-len(EOF_SENTINEL):] == EOF_SENTINEL:
                request_data = request_data[:-len(EOF_SENTINEL)]
                break

        cmd = f'{os.path.basename(sys.argv[0])} {shlex.join(json.loads(request_data)["argv"])}'

        # We're sending the binary data over a line-buffered text pipe, so so we need to encode it into a text format so
        # that any b'\n's don't get corrupted.
        data_encoded = base64.b64encode(request_data) + EOF_SENTINEL
        max_stdin_buffer_size = os.fpathconf(0, 'PC_MAX_CANON')
        for i in range(0, len(data_encoded), max_stdin_buffer_size):
            daemon_proc.sendline(data_encoded[i:i+max_stdin_buffer_size])
            daemon_proc.expect('ack')

        while True:
            with contextlib.suppress(pexpect.exceptions.TIMEOUT):
                response = daemon_proc.read_nonblocking(8192, timeout=0.05)
                if response:
                    # Replace any \r\n with \n. Weirdest thing ever.
                    # https://github.com/pexpect/pexpect/blob/master/doc/overview.rst (search for "CR/LF")
                    response = response.replace(b'\r\n', b'\n')
                    client_conn.sendall(response)
                if response[-len(EOF_SENTINEL):] == EOF_SENTINEL:
                    # Using ASCII NUL (0) as a sentinal value to indicate end-of-file. TODO: Need to upgrade this to a
                    # proper streaming protocol with frames so we can send a more complete end message, including the
                    # status code and distinguishing between STDOUT and STDERR.
                    break
    finally:
        client_conn.close()
    debug_duration = round(1000*(time.time() - debug_start_time))
    logger.info(f"Client disconnected after {debug_duration}ms. cmd: `{cmd}`")


def abort_if_daemon_already_running():
    if os.path.exists(SOCKET_ADDR):
        raise RuntimeError("Daemon already running?")


def run_daemon_supervisor():
    logger.info("Running as daemon")
    abort_if_daemon_already_running()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_ADDR)
    with open(PIDFILE_PATH, "w") as f:
        f.write(f"{os.getpid()}\n")
    try:
        sock.listen(0)  # Note: daemon as-is can only handle one client at a time, backlog arg of 0 disables queing.
        import pexpect

        daemon_proc = pexpect.spawn(sys.argv[0], args=["!!you-are-a-daemon!!"], echo=False)
        daemon_proc.delaybeforesend = None

        logger.info(f"{SELF_NAME} daemon online, listening on {SOCKET_ADDR}. Subprocess pid: {daemon_proc.pid}")
        while True:
            client_conn, _ = sock.accept()
            handle_daemon_supervisor_request(daemon_proc, client_conn)
    finally:
        sock.close()
        os.unlink(SOCKET_ADDR)
        os.unlink(PIDFILE_PATH)


def run_daemon():
    import base64
    from tableconv.main import main_wrapper

    while True:
        try:
            data_encoded = b''
            while True:
                # TODO: refactor all this text-pipe-protocol code so that the serializer code is next to the
                # deserializer code.
                new_data = sys.stdin.readline().strip('\n').encode()
                print('ack')
                data_encoded += new_data
                if data_encoded[-len(EOF_SENTINEL):] == EOF_SENTINEL:
                    data_encoded = data_encoded[:-len(EOF_SENTINEL)]
                    break

            data = json.loads(base64.b64decode(data_encoded))
            os.environ.update(data['environ'])
            os.chdir(data["cwd"])
            os.environ['TABLECONV_IS_DAEMON'] = '1'
            main_wrapper(data["argv"])
        except Exception:
            traceback.print_exc()
        except SystemExit:
            continue
        finally:
            sys.stdout.write(EOF_SENTINEL.decode())
            sys.stdout.flush()


def client_process_request_by_daemon(argv):
    if not os.path.exists(SOCKET_ADDR):
        # Daemon not online!
        return None

    verbose = {"-v", "--verbose", "--debug"} & set(argv)  # Hack.. no argparse or logging.config loaded yet
    if verbose:
        logger.debug("Using tableconv daemon (run `tableconv --kill-daemon` to kill)")

    # environ = dict(os.environ)
    environ = {}
    try:
        columns = os.get_terminal_size().columns
        environ['COLUMNS'] = str(columns)
    except (OSError, AttributeError):
        pass
    raw_request_msg = json.dumps({
        "argv": argv,
        'environ': environ,
        "cwd": os.getcwd(),
    }).encode() + EOF_SENTINEL

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET_ADDR)
    try:
        sock.sendall(raw_request_msg)
        response_part = b''
        while True:
            response_part += sock.recv(1024)

            eof = False
            if not response_part:
                eof = True
            elif response_part[-len(EOF_SENTINEL):] == EOF_SENTINEL:
                eof = True
                response_part = response_part[:-len(EOF_SENTINEL)]

            try:
                response_text = response_part.decode()
            except UnicodeDecodeError:
                # Because we're receiving unicode data, we might receive half a character in any given frame.
                # So we need to buffer up the data until we have a full character.
                pass
            else:
                sys.stdout.write(response_text)
                sys.stdout.flush()
                response_part = b''

            if eof:
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
    abort_if_daemon_already_running()
    if log:
        logger.info(f"Forking daemon using `daemonize`. Daemon logs piped to {LOGFILE_PATH} & {CRASHLOGFILE_PATH}")
    os.system(f"daemonize -e {CRASHLOGFILE_PATH} \"$(which {sys.argv[0]})\" --daemon")


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
                "logfile": {
                    "class": "logging.FileHandler",
                    "level": "DEBUG",
                    "formatter": "default",
                    "filename": LOGFILE_PATH,
                    "mode": "a",
                },
            },
            "root": {
                "level": "DEBUG",
                "handlers": ["default", "logfile"],
            },
        }
    )


def main_wrapper():
    """
    This is technically the entrypoint for tableconv if ran from the CLI. However, everything in this file is merely
    just wrapper code for providing the optional feature of preloading the tableconv Python libraries into a background
    daemon process (to improve startup time), and the corresponding code also to invoke any already-spun-up daemon.

    **Check tableconv.main.main to view the "real" tableconv entrypoint.**

    Note: When running tableconv as a daemon, there are actally three processes runnning: the client, the daemon, and
    the daemon supervisor.

    For ease of communication, in the tableconv UI we oversimplify and refer to both the daemon supervisor and the
    daemon beneath it simply as the "daemon", but within the code you can see that what we actually run is the
    supervisor, which then runs the daemon. (Also: if you invoke via --daemonize, you actually get 4 processes!)

    The reason for the seperation of the daemon supervisor and the daemon is in order to allow us to fully capture the
    STDIN/STDOUT/STDERR of the application and send it back over the network (while also of course still allowing the
    daemon itself to make its own logs to STDOUT).
    """
    set_up_logging()

    argv = sys.argv[1:]

    # Daemon management commands
    if "--daemon" in argv:  # Undocumented feature
        if len(argv) > 1:
            raise ValueError("ERROR: --daemon cannot be combined with any other options")
        try:
            return run_daemon_supervisor()
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
    if argv == ["!!you-are-a-daemon!!"]:
        # TODO use a alternative entry_point console_script instead of this sentinel value? I don't want to pollute the
        # end-user's PATH with another command though, this is not something an end user should ever directly run.
        # TODO: Using alternative entry point does not require adding pollution to PATH! I can just direcctly invoke a
        # python file relative to this python file - i.e. another python file within the tableconv _install directory_,
        # not within PATH.
        return run_daemon()


    # Try running as daemon client
    if "-i" not in argv and "--interactive" not in argv:  # If interactive mode is requested, don't use daemon.
        daemon_status = client_process_request_by_daemon(argv)
        if daemon_status is not None:
            return daemon_status
        elif os.environ.get("TABLECONV_AUTO_DAEMON"):  # Undocumented feature
            print("[Automatically forking daemon]", file=sys.stderr)
            print("[To kill daemon, run `unset TABLECONV_AUTO_DAEMON && tableconv --kill-daemon`]", file=sys.stderr)
            run_daemonize(log=False)
            time.sleep(0.5)  # Give daemon time to start # hack..
            return client_process_request_by_daemon(argv)

    # Runinng as daemon client failed, so run tableconv normally: run within this process.
    from tableconv.main import main_wrapper
    sys.exit(main_wrapper(argv))


if __name__ == "__main__":
    main_wrapper()
