import ast
import copy
import io
import json
import logging
import os
import re
import shlex
import sqlite3
import subprocess
import textwrap

import pytest

from tableconv.__main__ import main

EXAMPLE_CSV_RAW = textwrap.dedent('''
    id,name,date
    1,George,2023
    2,Steven,1950
    3,Rachel,1995
''').strip()
EXAMPLE_TSV_RAW = textwrap.dedent('''
    id\tname\tdate
    1\tGeorge\t2023
    2\tSteven\t1950
    3\tRachel\t1995
''').strip()
EXAMPLE_JSON_RAW = textwrap.dedent('''
    [
        {"id":1,"name":"George","date":2023},
        {"id":2,"name":"Steven","date":1950},
        {"id":3,"name":"Rachel","date":1995}
    ]
''').strip()
EXAMPLE_LIST_RAW = textwrap.dedent('''
    a
    b
    c
''').strip()


def invoke_cli(args, stdin=None, capture_stderr=False, assert_nonzero_exit_code=False,
               use_subprocess=False, capfd=None, monkeypatch=None):
    if use_subprocess:
        # Test by invoking a subprocess. This is extremely similar to how a user would experience tableconv from their
        # terminal.
        cmd = ['tableconv'] + args
        logging.warning(f'Running cmd `{shlex.join(cmd)}`')
        process = subprocess.run(cmd, capture_output=True, input=stdin, text=True)
        if assert_nonzero_exit_code:
            assert process.returncode != 0
        else:
            assert process.returncode == 0
        if capture_stderr:
            return process.stdout, process.sderr
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


def test_csv_to_tsv(capfd, monkeypatch):
    stdout = invoke_cli(['csv:-', '-o', 'tsv:-'], stdin=EXAMPLE_CSV_RAW, capfd=capfd, monkeypatch=monkeypatch)
    assert stdout == EXAMPLE_TSV_RAW + '\n'


def test_tsv_to_csv(capfd, monkeypatch):
    stdout = invoke_cli(['tsv:-', '-o', 'csv:-'], stdin=EXAMPLE_TSV_RAW, capfd=capfd, monkeypatch=monkeypatch)
    assert stdout == EXAMPLE_CSV_RAW + '\n'


def test_tsv_to_csv_files(tmp_path, capfd, monkeypatch):
    with open(f'{tmp_path}/test.tsv', 'w') as f:
        f.write(EXAMPLE_TSV_RAW)
    invoke_cli([f'tsv://{tmp_path}/test.tsv', '-o', f'csv://{tmp_path}/test.csv'], capfd=capfd, monkeypatch=monkeypatch)
    assert open(f'{tmp_path}/test.csv').read() == EXAMPLE_CSV_RAW + '\n'


def test_tsv_to_csv_files_inferred_scheme(tmp_path, capfd, monkeypatch):
    with open(f'{tmp_path}/test.tsv', 'w') as f:
        f.write(EXAMPLE_TSV_RAW)
    invoke_cli([f'{tmp_path}/test.tsv', '-o', f'{tmp_path}/test.csv'], capfd=capfd, monkeypatch=monkeypatch)
    assert open(f'{tmp_path}/test.csv').read() == EXAMPLE_CSV_RAW + '\n'


def test_tsv_query(capfd, monkeypatch):
    stdout = invoke_cli(['tsv:-', '-q', 'SELECT COUNT(*) AS count FROM data', '-o', 'json:-'], stdin=EXAMPLE_TSV_RAW, capfd=capfd, monkeypatch=monkeypatch)
    assert json.loads(stdout) == [{'count': 3}]


def test_inferred_numbers_from_ascii_format(capfd, monkeypatch):
    stdout = invoke_cli(['tsv:-', '-o', 'json:-'], stdin=EXAMPLE_TSV_RAW, capfd=capfd, monkeypatch=monkeypatch)
    id_val = json.loads(stdout)[0]['id']
    assert isinstance(id_val, int)
    assert id_val == 1


def test_interactive(tmp_path):
    with open(f'{tmp_path}/test.tsv', 'w') as f:
        f.write(EXAMPLE_TSV_RAW)
    cmd = ['tableconv'] + [f'{tmp_path}/test.tsv', '-i', '-o', 'asciipretty:-']
    logging.warning(f'Running cmd `{shlex.join(cmd)}`')
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    stdout, _ = proc.communicate('SELECT date FROM DATA WHERE date > \'2015\'\n', timeout=1)
    stdout_lines = stdout.splitlines()
    assert re.match(r'/.{6}\[\.\.\.\]teractive0/test\.tsv=> ', stdout_lines.pop(0))
    assert stdout_lines.pop(0) == '| date |'
    assert stdout_lines.pop(0) == '+------+'
    assert stdout_lines.pop(0) == '| 2023 |'

    # NOTE: this test is weak because it is not using a real TTY. The interactive mode only needs to work correctly on a
    # real TTY. Here, we should have a linebreak between the end of the query output and the next prompt. However, lack of
    # real TTY in this test can break tableconv and cause it to miss the linebreak. Not strictly a bug, but needs to be
    # fixed so that this test can be completed (TODO).
    # assert stdout_lines.pop(0) == '+------+'
    # assert re.match(r'/.{6}\[\.\.\.\]teractive0/test\.tsv=> ', stdout_lines.pop(0))


# @pytest.mark.skip('Broken')
# def test_interactive_multi_input(tmp_path):
#     proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

#     flag = fcntl.fcntl(proc.stdout.fileno(), fcntl.F_GETFL)
#     fcntl.fcntl(proc.stdout.fileno(), fcntl.F_SETFL, flag | os.O_NONBLOCK)
#     time.sleep(2)
#     stdout = proc.stdout.read().decode()
#     stdout_lines = stdout.splitlines()

#     assert re.match(r'/.{6}\[\.\.\.\]lti_input0/test\.tsv=> ', stdout_lines.pop(0))
#     proc.stdin.write('SELECT date FROM DATA WHERE date > \'2015\'\n'.encode())
#     time.sleep(0.5)
#     stdout = proc.stdout.read().decode()
#     stdout_lines = stdout.splitlines()
#     assert stdout_lines.pop(0) == '+------+'
#     assert stdout_lines.pop(0) == '| date |'
#     assert stdout_lines.pop(0) == '+------+'
#     assert stdout_lines.pop(0) == '| 2023 |'
#     assert stdout_lines.pop(0) == '+------+'

#     assert re.match(r'/.{6}\[\.\.\.\]lti_input0/test\.tsv=> ', stdout_lines.pop(0))
#     proc.stdin.write('SELECT id FROM DATA ORDER BY id DESC\n'.encode())
#     time.sleep(0.5)
#     stdout = proc.stdout.read().decode()
#     stdout_lines = stdout.splitlines()
#     assert stdout_lines.pop(0) == '+----+'
#     assert stdout_lines.pop(0) == '| id |'
#     assert stdout_lines.pop(0) == '+----+'
#     assert stdout_lines.pop(0) == '|  1 |'
#     assert stdout_lines.pop(0) == '|  2 |'
#     assert stdout_lines.pop(0) == '|  3 |'
#     assert stdout_lines.pop(0) == '+----+'

#     proc.stdin.close()
#     proc.wait()
#     assert proc.returncode == 0

def help_test_util(capfd, use_subprocess=False):
    stdout = invoke_cli(['-h'], use_subprocess=use_subprocess, capfd=capfd)
    MINIMUM_SUPPORED_SCHEMES = [
        'csv ', 'json ', 'jsonl ', 'python ', 'tsv ', 'xls ', 'ascii', 'gsheets'
    ]
    for scheme in MINIMUM_SUPPORED_SCHEMES:
        assert scheme in stdout.lower()
    assert 'usage' in stdout.lower()
    assert '-o' in stdout.lower()
    assert '://' in stdout.lower()


def test_help(capfd):
    help_test_util(capfd=capfd)


def test_launch_process(capfd):
    help_test_util(use_subprocess=True, capfd=capfd)


def test_no_arguments(capfd, monkeypatch):
    _, stderr = invoke_cli([], assert_nonzero_exit_code=True,
                           capfd=capfd, monkeypatch=monkeypatch, capture_stderr=True)
    assert 'traceback' not in stderr.lower()
    assert 'usage:' in stderr.lower()
    assert 'error' in stderr.lower()
    assert 'arguments are required' in stderr.lower()


def test_invalid_filename(capfd, monkeypatch):
    _, stderr = invoke_cli(['/tmp/does_not_exist_c3b8c2ecd34a.csv'], assert_nonzero_exit_code=True,
                           capfd=capfd, monkeypatch=monkeypatch, capture_stderr=True)
    assert 'traceback' not in stderr.lower()
    assert 'error' in stderr.lower()
    assert 'does_not_exist_c3b8c2ecd34a.csv' in stderr.lower()
    assert 'not found' in stderr.lower() or 'no such file' in stderr.lower()


def test_no_data_file(tmp_path, capfd, monkeypatch):
    filename = f'{tmp_path}/test.tsv'
    with open(filename, 'w') as f:
        f.write('')
    _, stderr = invoke_cli([filename], assert_nonzero_exit_code=True,
                           capfd=capfd, monkeypatch=monkeypatch, capture_stderr=True)
    assert 'traceback' not in stderr.lower()
    assert 'error' in stderr.lower()
    assert 'empty' in stderr.lower()


def test_no_data_sqlite3(tmp_path, capfd, monkeypatch):
    path = f'{tmp_path}/test.sqlite3'
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute('CREATE TABLE wasd (name TEXT NOT NULL, id INT NOT NULL)')
    conn.close()

    _, stderr = invoke_cli([f'{path}?table=wasd'], assert_nonzero_exit_code=True,
                           capfd=capfd, monkeypatch=monkeypatch, capture_stderr=True)
    assert 'traceback' not in stderr.lower()
    assert 'error' in stderr.lower()
    assert 'empty' in stderr.lower()


def test_full_roundtrip_file_adapters(tmp_path, capfd, monkeypatch):
    """ Go from json -> tsv -> csv -> python -> yaml -> jsonl -> parquet -> xls -> json and verify the json at the end
    is semantically identical to the json we started with. """
    urls = [
        'json://-',
        'tsv://-',
        'csv://-',
        'python://-',
        'yaml://-',
        'jsonl://-',
        f'{tmp_path}/test.parquet',
        f'{tmp_path}/test.xls',
        'json://-',
    ]
    last_call_stdout = None
    for i, url_b in enumerate(urls[1:]):
        url_a = urls[i]
        if i == 0:
            # Initialize
            stdin = EXAMPLE_JSON_RAW
        else:
            stdin = copy.copy(last_call_stdout)
        last_call_stdout = invoke_cli([url_a, '-o', url_b], stdin=stdin, capfd=capfd, monkeypatch=monkeypatch)

    assert json.loads(EXAMPLE_JSON_RAW) == json.loads(last_call_stdout)


def test_sqlite_file_missing_table(tmp_path, capfd, monkeypatch):
    _, stderr = invoke_cli(['csv://-', '-o', f'{tmp_path}/db.sqlite3'], stdin=EXAMPLE_CSV_RAW, assert_nonzero_exit_code=True,
                           capture_stderr=True, capfd=capfd, monkeypatch=monkeypatch)
    assert 'traceback' not in stderr.lower()
    assert 'error' in stderr.lower()
    assert 'table' in stderr.lower()


def test_sqlite_file_roundtrip(tmp_path, capfd, monkeypatch):
    invoke_cli(['csv://-', '-o', f'{tmp_path}/db.sqlite3?table=test'], stdin=EXAMPLE_CSV_RAW, capfd=capfd, monkeypatch=monkeypatch)
    stdout = invoke_cli([f'{tmp_path}/db.sqlite3?table=test', '-o', 'csv:-'], capfd=capfd, monkeypatch=monkeypatch)
    assert stdout == EXAMPLE_CSV_RAW + '\n'


def test_sqlite_roundtrip(tmp_path, capfd, monkeypatch):
    invoke_cli(['csv:-', '-o', f'sqlite://{tmp_path}/db.db?table=test'], stdin=EXAMPLE_CSV_RAW, capfd=capfd, monkeypatch=monkeypatch)
    stdout = invoke_cli([f'sqlite://{tmp_path}//db.db?table=test', '-o', 'csv:-'], capfd=capfd, monkeypatch=monkeypatch)
    assert stdout == EXAMPLE_CSV_RAW + '\n'


def test_sqlite_roundtrip_query(tmp_path, capfd, monkeypatch):
    invoke_cli(['csv:-', '-o', f'sqlite://{tmp_path}/db.db?table=test'], stdin=EXAMPLE_CSV_RAW, capfd=capfd, monkeypatch=monkeypatch)
    stdout = invoke_cli([f'sqlite://{tmp_path}//db.db', '-q', 'SELECT * FROM test ORDER BY id ASC', '-o', 'csv:-'], capfd=capfd, monkeypatch=monkeypatch)
    assert stdout == EXAMPLE_CSV_RAW + '\n'


def test_sqlite_query_and_filter(tmp_path, capfd, monkeypatch):
    invoke_cli(['csv:-', '-o', f'sqlite://{tmp_path}/db.db?table=test'], stdin=EXAMPLE_CSV_RAW, capfd=capfd, monkeypatch=monkeypatch)
    stdout = invoke_cli([
        f'sqlite://{tmp_path}//db.db',
        '-q', 'SELECT * FROM test ORDER BY id ASC',
        '-F', 'SELECT COUNT(*) as zzzz FROM data WHERE name != \'Steven\'',
        '-o', 'csv:-'], capfd=capfd, monkeypatch=monkeypatch)
    assert stdout == 'zzzz\n2' + '\n'


def test_array_formats(capfd, monkeypatch):
    """Test conversions between the array types: list, jsonarray, csa, and pylist."""
    stdout = invoke_cli(['list:-', '-o', 'jsonarray:-'], stdin=EXAMPLE_LIST_RAW, capfd=capfd, monkeypatch=monkeypatch)
    assert json.loads(stdout) == ['a', 'b', 'c']
    stdout = invoke_cli(['list:-', '-o', 'csa:-'], stdin=EXAMPLE_LIST_RAW, capfd=capfd, monkeypatch=monkeypatch)
    assert stdout == 'a,b,c'
    stdout = invoke_cli(['list:-', '-o', 'pylist:-'], stdin=EXAMPLE_LIST_RAW, capfd=capfd, monkeypatch=monkeypatch)
    assert ast.literal_eval(stdout) == ['a', 'b', 'c']
    stdout = invoke_cli(['jsonarray:-', '-o', 'list:-'], stdin='["a","b","c"]', capfd=capfd, monkeypatch=monkeypatch)
    assert stdout == 'a\nb\nc'


def test_array_to_table(capfd, monkeypatch):
    """Test array (list) to table (json) conversion"""
    stdout = invoke_cli(['list:-', '-o', 'json:-'], stdin=EXAMPLE_LIST_RAW, capfd=capfd, monkeypatch=monkeypatch)
    assert json.loads(stdout) == [
        {'value': 'a'},
        {'value': 'b'},
        {'value': 'c'},
    ]


def test_table_to_array(capfd, monkeypatch):
    """Test table (csv) to to array (csa) conversion"""
    stdout = invoke_cli(['csv:-', '-q', 'SELECT name from data', '-o', 'csa:-'], stdin=EXAMPLE_CSV_RAW, capfd=capfd, monkeypatch=monkeypatch)
    assert stdout == 'George,Steven,Rachel'


@pytest.mark.skip('slow')
def test_packaging(tmp_path):
    """
    Test that tableconv is packaged correctly by installing it into a clean environment and then running it. Doing this
    test vaguely confirms that the required dependencies are specified for installation correctly and that the CLI
    entrypoint is specified correctly.
    """
    from tableconv.__version__ import __version__ as version_number
    assert os.path.abspath(os.getcwd()) == os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

    # Build a new copy of tableconv package
    subprocess.run(['rm', '-rf', 'dist'], check=True)
    subprocess.run(['python', 'setup.py', 'sdist', 'bdist_wheel'], check=True)

    # Install the build into an isolated docker container
    dockerfile_path = os.path.join(tmp_path, 'Dockerfile')
    with open(dockerfile_path, 'w') as f:
        f.write(textwrap.dedent('''
            FROM python:3.8
            COPY dist/* /tmp/
            RUN pip install /tmp/tableconv-*.tar.gz
        ''').strip())
    subprocess.run(['docker', 'build', '-t', 'tableconv_test', '-f', dockerfile_path, '.'], check=True)

    # Verify the tableconv CLI can be ran within that container, and verify it knows its correct version number.
    cmd = ['tableconv', '--version']
    cmd_output = subprocess.run(['docker', 'run', '-t', 'tableconv_test'] + cmd, capture_output=True, text=True, check=True).stdout
    assert version_number in cmd_output
    assert 'tableconv' in cmd_output
