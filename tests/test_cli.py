import ast
import copy
import json
import logging
import re
import shlex
import subprocess
import io
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


def invoke_cli(args, stdin=None, use_subprocess=False, capfd=None, monkeypatch=None):
    if use_subprocess:
        cmd = ['tableconv'] + args
        logging.warning(f'Running cmd `{shlex.join(cmd)}`')
        return subprocess.run(cmd, capture_output=True, input=stdin, text=True, check=True).stdout
    monkeypatch.setattr('sys.stdin', io.StringIO(stdin))
    main(args)
    stdout, _ = capfd.readouterr()
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
    assert re.match(r'/.{6}\[\.\.\.\]teractive0/test\.tsv=> ', stdout_lines.pop(0) + \
                                  '+------+')
    assert stdout_lines.pop(0) == '| date |'
    assert stdout_lines.pop(0) == '+------+'
    assert stdout_lines.pop(0) == '| 2023 |'

    # NOTE: this test is weak because it is not using a real TTY. The interactive mode only needs to work correctly on a
    # real TTY. Here, we should have a space between the end of the query output and the next prompt. However, lack of
    # real TTY in this test can break tableconv and cause it to miss the space. Not strictly a bug, but needs to be
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


def test_help():
    stdout = invoke_cli(['-h'], use_subprocess=True)
    CORE_SUPPORTED_SCHEMES = [
        'csv ', 'json ', 'jsonl ', 'python ', 'tsv ', 'xls ', 'ascii', 'gsheets'
    ]
    for scheme in CORE_SUPPORTED_SCHEMES:
        assert scheme in stdout.lower()
    assert 'usage' in stdout.lower()
    assert '-o' in stdout.lower()
    assert '://' in stdout.lower()


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


def test_sqlite_url_errors(tmp_path, capfd, monkeypatch):
    with pytest.raises(subprocess.CalledProcessError) as exc:
        invoke_cli(['csv://-', '-o', 'sqlite://db.db'], use_subprocess=True, stdin=EXAMPLE_CSV_RAW, capfd=capfd, monkeypatch=monkeypatch)
        assert 'Invalid SQLite URL' in exc.stderr
    with pytest.raises(subprocess.CalledProcessError) as exc:
        invoke_cli(['csv://-', '-o', 'sqlite:///tmp/db.db'], use_subprocess=True, stdin=EXAMPLE_CSV_RAW, capfd=capfd, monkeypatch=monkeypatch)
        assert 'Invalid SQLite URL' in exc.stderr


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
