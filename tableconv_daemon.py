import contextlib
import json
import logging
import os
import shlex
import socket
import sys
import time
import traceback

SOCKET_ADDR = '/tmp/tableconv-daemon.sock'
SELF_NAME = os.path.basename(sys.argv[0])


def handle_daemon_supervisor_request(daemon_proc, client_conn) -> None:
    import pexpect.exceptions
    logging.info('client connected.')
    debug_start_time = time.time()
    try:
        request_data = None
        while not request_data:
            request_data = client_conn.recv(1024**2)

        daemon_proc.sendline(request_data)
        _ = daemon_proc.readline()  # ignore stdin playback (?)
        while True:
            with contextlib.suppress(pexpect.exceptions.TIMEOUT):
                response = daemon_proc.read_nonblocking(1024**2, timeout=0.05)
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
    logging.info(f'client disconnected after {debug_duration}s. cmd: {cmd}')


def run_daemon_supervisor():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(name)s](%(levelname)s) %(message)s')
    if os.path.exists(SOCKET_ADDR):
        raise RuntimeError('Daemon already running?')
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_ADDR)
    try:
        sock.listen(0)  # Note: daemon as-is can only handle one client at a time, backlog arg of 0 disables queing.
        import pexpect
        daemon_proc = pexpect.spawn(sys.argv[0], args=['!!you-are-a-daemon!!'])
        logging.info(f'{SELF_NAME} daemon online, listening on {SOCKET_ADDR}')
        while True:
            client_conn, _ = sock.accept()
            handle_daemon_supervisor_request(daemon_proc, client_conn)
    finally:
        sock.close()
        os.unlink(SOCKET_ADDR)


def run_daemon():
    from tableconv.main import main
    while True:
        try:
            data = json.loads(sys.stdin.readline())
            # os.environ = data['environ']
            os.chdir(data['cwd'])
            main(data['argv'])
        except Exception:
            traceback.print_exc()
        except SystemExit:
            continue
        finally:
            sys.stdout.write('\0')
            sys.stdout.flush()


def client_process_request_by_daemon(raw_data: bytes):
    if not os.path.exists(SOCKET_ADDR):
        # Daemon not online!
        return None

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET_ADDR)
    try:
        sock.sendall(raw_data)
        while True:
            response_part = sock.recv(1024**2)
            sys.stdout.write(response_part.decode())
            sys.stdout.flush()
            if not response_part or response_part[-1] == '\0':
                break
    finally:
        sock.close()

    return True


def main_wrapper():
    """
    This is _technically_ an entrypoint for tableconv if running from the CLI. However, everything in this file is
    merely just wrapper code that lets tableconv optionally preload its Python libraries via a background daemon (to
    improve startup time).

    **To view the "real" tableconv entrypoint, the real main(), check tableconv.main.main.**
    """
    argv = sys.argv[1:]
    if argv in [['--spawn-daemon-supervisor'], ['--daemon']]:
        return run_daemon_supervisor()
    if argv == ['!!you-are-a-daemon!!']:
        return run_daemon()

    status = client_process_request_by_daemon(json.dumps({
        'argv': argv,
        # 'environ': dict(os.environ),
        'cwd': os.getcwd()
    }).encode())
    if not status:
        from tableconv.main import main
        main(argv)
