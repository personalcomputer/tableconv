import io
import logging
import os
import shlex
import subprocess
from pathlib import Path

import pytest

from tableconv.main import main

FIXTURES_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / 'fixtures'


@pytest.fixture
def invoke_cli(capfd, monkeypatch):
    def func(args, stdin=None, capture_stderr=False, assert_nonzero_exit_code=False, use_subprocess=False):
        args = [str(arg) for arg in args]
        if use_subprocess:
            # Test by invoking a subprocess. This is extremely similar to how a user would experience tableconv from
            # their terminal.
            cmd = ['tableconv'] + args
            logging.warning(f'Running cmd `{shlex.join(cmd)}`')
            process = subprocess.run(cmd, capture_output=True, input=stdin, text=True)
            if assert_nonzero_exit_code:
                assert process.returncode != 0
            else:
                assert process.returncode == 0
            if capture_stderr:
                return process.stdout, process.stderr
            else:
                return process.stdout
        else:
            # Test by running the CLI within the same test thread. This is faster than a subprocess, but less realistic,
            # testcases could be corrupted by e.g. global variables shared from test to test.
            if stdin:
                monkeypatch.setattr('sys.stdin', io.StringIO(stdin))
            try:
                main(args)
            except SystemExit as sysexit:
                if assert_nonzero_exit_code:
                    assert sysexit.code != 0
                else:
                    assert sysexit.code == 0
            stdout, stderr = capfd.readouterr()
            if capture_stderr:
                return stdout, stderr
            else:
                return stdout
    return func
