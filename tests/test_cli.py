import ast
import copy
import filecmp
import json
import logging
import re
import shlex
import sqlite3
import subprocess

import pytest

from tests.conftest import FIXTURES_DIR
from tests.fixtures.example_raw import (
    EXAMPLE_CSV_RAW,
    EXAMPLE_JSON_RAW,
    EXAMPLE_LIST_RAW,
    EXAMPLE_TSV_RAW,
)


def test_csv_to_tsv(invoke_cli):
    stdout = invoke_cli(["csv:-", "-o", "tsv:-"], stdin=EXAMPLE_CSV_RAW)
    assert stdout == EXAMPLE_TSV_RAW + "\n"


def test_tsv_to_csv(invoke_cli):
    stdout = invoke_cli(["tsv:-", "-o", "csv:-"], stdin=EXAMPLE_TSV_RAW)
    assert stdout == EXAMPLE_CSV_RAW + "\n"


def test_tsv_to_csv_files(tmp_path, invoke_cli):
    invoke_cli([FIXTURES_DIR / "example.tsv", "-o", f"csv://{tmp_path}/test.csv"])
    assert filecmp.cmp(f"{tmp_path}/test.csv", FIXTURES_DIR / "example.csv")


def test_tsv_to_csv_files_inferred_scheme(tmp_path, invoke_cli):
    invoke_cli([FIXTURES_DIR / "example.tsv", "-o", f"{tmp_path}/test.csv"])
    assert filecmp.cmp(f"{tmp_path}/test.csv", FIXTURES_DIR / "example.csv")


def test_tsv_query(invoke_cli):
    stdout = invoke_cli(
        ["tsv:-", "-q", "SELECT COUNT(*) AS count FROM data", "-o", "json:-"],
        stdin=EXAMPLE_TSV_RAW,
    )
    assert json.loads(stdout) == [{"count": 3}]


def test_inferred_numbers_from_ascii_format(invoke_cli):
    stdout = invoke_cli(["tsv:-", "-o", "json:-"], stdin=EXAMPLE_TSV_RAW)
    id_val = json.loads(stdout)[0]["id"]
    assert isinstance(id_val, int)
    assert id_val == 1


@pytest.mark.skip
def test_join(invoke_cli):
    stdout = invoke_cli(
        [
            f'{FIXTURES_DIR / "example.tsv"} AS tab1, {FIXTURES_DIR / "example_2.csv"} AS tab2',
            "-F",
            "SELECT name, preference FROM tab1 JOIN tab2 ON tab2.id=tab1.id ORDER BY id",
            "-o",
            "json:-",
        ]
    )
    assert json.loads(stdout) == [
        {"name": "George", "preference": "Strawberry"},
        {"name": "Steven", "preference": "Chocolate"},
        {"name": "Rachel", "preference": "Vanilla"},
    ]

    # tc 'example.tsv AS tab1, example2.tsv AS tab2' \
    # -F 'SELECT name, preference FROM tab1 JOIN tab2 ON tab2.id=tab1.id ORDER BY id'


def test_interactive(tmp_path):
    cmd = ["tableconv"] + [
        str(FIXTURES_DIR / "example.tsv"),
        "-i",
        "-o",
        "asciipretty:-",
    ]
    logging.warning(f"Running cmd `{shlex.join(cmd)}`")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    stdout, _ = proc.communicate("SELECT date FROM DATA WHERE date > '2015'\n", timeout=1)
    stdout_lines = stdout.splitlines()
    assert re.match(r"/.{6}\[\.\.\.\]ixtures/example\.tsv=> ", stdout_lines.pop(0))
    assert stdout_lines.pop(0) == "| date |"
    assert stdout_lines.pop(0) == "+------+"
    assert stdout_lines.pop(0) == "| 2023 |"

    # NOTE: this test is weak because it is not using a real TTY. The interactive mode only needs to work correctly on a
    # real TTY. Here, we should have a linebreak between the end of the query output and the next prompt. However, lack
    # of real TTY in this test can break tableconv and cause it to miss the linebreak. Not strictly a bug, but needs to
    # be fixed so that this test can be completed (TODO).
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


def help_test_util(invoke_cli, use_subprocess=False):
    stdout = invoke_cli(["-h"], use_subprocess=use_subprocess)
    MINIMUM_SUPPORED_SCHEMES = [
        "csv ",
        "json ",
        "jsonl ",
        "python ",
        "tsv ",
        "xlsx ",
        "ascii",
        "gsheets",
    ]
    for scheme in MINIMUM_SUPPORED_SCHEMES:
        assert scheme in stdout.lower()
    assert "usage" in stdout.lower()
    assert "-o" in stdout.lower()
    assert "://" in stdout.lower()


def test_help(invoke_cli):
    help_test_util(invoke_cli)


def test_launch_process(invoke_cli):
    help_test_util(invoke_cli, use_subprocess=True)


def test_no_arguments(invoke_cli):
    _, stderr = invoke_cli([], assert_nonzero_exit_code=True, capture_stderr=True)
    assert "traceback" not in stderr.lower()
    assert "usage:" in stderr.lower()
    assert "error" in stderr.lower()
    assert "arguments are required" in stderr.lower()


def test_invalid_filename(invoke_cli):
    _, stderr = invoke_cli(
        ["/tmp/does_not_exist_c3b8c2ecd34a.csv"],
        assert_nonzero_exit_code=True,
        capture_stderr=True,
    )
    assert "traceback" not in stderr.lower()
    assert "error" in stderr.lower()
    assert "does_not_exist_c3b8c2ecd34a.csv" in stderr.lower()
    assert "not found" in stderr.lower() or "no such file" in stderr.lower()


def test_no_data_file(tmp_path, invoke_cli):
    filename = f"{tmp_path}/test.tsv"
    with open(filename, "w") as f:
        f.write("")
    _, stderr = invoke_cli([filename], assert_nonzero_exit_code=True, capture_stderr=True)
    assert "traceback" not in stderr.lower()
    assert "error" in stderr.lower()
    assert "empty" in stderr.lower()


def test_no_data_sqlite3(tmp_path, invoke_cli):
    path = f"{tmp_path}/test.sqlite3"
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE wasd (name TEXT NOT NULL, id INT NOT NULL)")
    conn.close()

    _, stderr = invoke_cli([f"{path}?table=wasd"], assert_nonzero_exit_code=True, capture_stderr=True)
    assert "traceback" not in stderr.lower()
    assert "error" in stderr.lower()
    assert "empty" in stderr.lower()


def test_full_roundtrip_file_adapters(tmp_path, invoke_cli):
    """Go from json -> tsv -> csv -> python -> yaml -> jsonl -> parquet -> xlsx -> json and verify the json at the end
    is semantically identical to the json we started with."""
    urls = [
        "json://-",
        "tsv://-",
        "csv://-",
        "python://-",
        "yaml://-",
        "jsonl://-",
        f"{tmp_path}/test.parquet",
        f"{tmp_path}/test.xlsx",
        "json://-",
    ]
    last_call_stdout = None
    for i, url_b in enumerate(urls[1:]):
        url_a = urls[i]
        if i == 0:
            # Initialize
            stdin = EXAMPLE_JSON_RAW
        else:
            stdin = copy.copy(last_call_stdout)
        last_call_stdout = invoke_cli([url_a, "-o", url_b], stdin=stdin)

    assert json.loads(EXAMPLE_JSON_RAW) == json.loads(last_call_stdout)


def test_sqlite_file_missing_table(tmp_path, invoke_cli):
    _, stderr = invoke_cli(
        ["csv://-", "-o", f"{tmp_path}/db.sqlite3"],
        stdin=EXAMPLE_CSV_RAW,
        assert_nonzero_exit_code=True,
        capture_stderr=True,
    )
    assert "traceback" not in stderr.lower()
    assert "error" in stderr.lower()
    assert "table" in stderr.lower()


def test_sqlite_file_roundtrip(tmp_path, invoke_cli):
    invoke_cli(["csv://-", "-o", f"{tmp_path}/db.sqlite3?table=test"], stdin=EXAMPLE_CSV_RAW)
    stdout = invoke_cli([f"{tmp_path}/db.sqlite3?table=test", "-o", "csv:-"])
    assert stdout == EXAMPLE_CSV_RAW + "\n"


def test_sqlite_roundtrip(tmp_path, invoke_cli):
    invoke_cli(["csv:-", "-o", f"sqlite://{tmp_path}/db.db?table=test"], stdin=EXAMPLE_CSV_RAW)
    stdout = invoke_cli([f"sqlite://{tmp_path}//db.db?table=test", "-o", "csv:-"])
    assert stdout == EXAMPLE_CSV_RAW + "\n"


def test_sqlite_roundtrip_query(tmp_path, invoke_cli):
    invoke_cli(["csv:-", "-o", f"sqlite://{tmp_path}/db.db?table=test"], stdin=EXAMPLE_CSV_RAW)
    stdout = invoke_cli(
        [
            f"sqlite://{tmp_path}//db.db",
            "-q",
            "SELECT * FROM test ORDER BY id ASC",
            "-o",
            "csv:-",
        ]
    )
    assert stdout == EXAMPLE_CSV_RAW + "\n"


def test_sqlite_query_and_filter(tmp_path, invoke_cli):
    invoke_cli(["csv:-", "-o", f"sqlite://{tmp_path}/db.db?table=test"], stdin=EXAMPLE_CSV_RAW)
    stdout = invoke_cli(
        [
            f"sqlite://{tmp_path}//db.db",
            "-q",
            "SELECT * FROM test ORDER BY id ASC",
            "-F",
            "SELECT COUNT(*) as zzzz FROM data WHERE name != 'Steven'",
            "-o",
            "csv:-",
        ]
    )
    assert stdout == "zzzz\n2" + "\n"


def test_array_formats(invoke_cli):
    """Test conversions between the array types: list, jsonarray, csa, and pylist."""
    stdout = invoke_cli(["list:-", "-o", "jsonarray:-"], stdin=EXAMPLE_LIST_RAW)
    assert json.loads(stdout) == ["a", "b", "c"]
    stdout = invoke_cli(["list:-", "-o", "csa:-"], stdin=EXAMPLE_LIST_RAW)
    assert stdout == "a,b,c"
    stdout = invoke_cli(["list:-", "-o", "pylist:-"], stdin=EXAMPLE_LIST_RAW)
    assert ast.literal_eval(stdout) == ["a", "b", "c"]
    stdout = invoke_cli(["jsonarray:-", "-o", "list:-"], stdin='["a","b","c"]')
    assert stdout == "a\nb\nc"


def test_array_to_table(invoke_cli):
    """Test array (list) to table (json) conversion"""
    stdout = invoke_cli(["list:-", "-o", "json:-"], stdin=EXAMPLE_LIST_RAW)
    assert json.loads(stdout) == [
        {"value": "a"},
        {"value": "b"},
        {"value": "c"},
    ]


def test_table_to_array(invoke_cli):
    """Test table (csv) to to array (csa) conversion"""
    stdout = invoke_cli(["csv:-", "-q", "SELECT name from data", "-o", "csa:-"], stdin=EXAMPLE_CSV_RAW)
    assert stdout == "George,Steven,Rachel"
