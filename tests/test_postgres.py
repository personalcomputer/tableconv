import json
import subprocess

import pytest

from tests.fixtures.example_raw import EXAMPLE_CSV_RAW, EXAMPLE_LIST_RAW


@pytest.fixture
def clean_db_test_table():
    subprocess.run(
        ["psql", "-h", "localhost", "-p", "5432", "test"],
        input="DROP TABLE IF EXISTS test_table",
        text=True,
        check=True,
    )


@pytest.fixture
def initialize_db_test_table():
    subprocess.run(
        ["psql", "-h", "localhost", "-p", "5432", "test"],
        input=(
            "DROP TABLE IF EXISTS test_table;"
            "CREATE TABLE test_table (id INTEGER, name text);"
            "INSERT INTO test_table (id, name) VALUES (1,'hello');"
        ),
        text=True,
        check=True,
    )


def test_postgres_read(initialize_db_test_table, invoke_cli):
    stdout = invoke_cli(["postgresql://localhost:5432/test/test_table", "-o", "json:-"])
    assert json.loads(stdout)[0] == {"id": 1, "name": "hello"}


def test_postgres_read_kwarg_table(initialize_db_test_table, invoke_cli):
    stdout = invoke_cli(["postgresql://localhost:5432/test?table=test_table", "-o", "json:-"])
    assert json.loads(stdout)[0] == {"id": 1, "name": "hello"}


def test_postgres_write(clean_db_test_table, invoke_cli):
    invoke_cli(
        ["csv:-", "-o", "postgresql://localhost:5432/test/test_table"],
        stdin=EXAMPLE_CSV_RAW,
    )
    stdout = invoke_cli(
        [
            "postgresql://localhost:5432/test",
            "-q",
            "select name from test_table ORDER BY name",
            "-o",
            "json:-",
        ]
    )
    assert json.loads(stdout) == [
        {"name": "George"},
        {"name": "Rachel"},
        {"name": "Steven"},
    ]


def test_postgres_overwrite(clean_db_test_table, invoke_cli):
    invoke_cli(
        ["csv:-", "-o", "postgresql://localhost:5432/test/test_table"],
        stdin=EXAMPLE_CSV_RAW,
    )
    invoke_cli(
        ["list:-", "-o", "postgresql://localhost:5432/test/test_table?overwrite=True"],
        stdin=EXAMPLE_LIST_RAW,
    )
    stdout = invoke_cli(
        [
            "postgresql://localhost:5432/test",
            "-q",
            "select value from test_table ORDER BY value ASC LIMIT 1",
            "-o",
            "json:-",
        ]
    )
    assert json.loads(stdout) == [{"value": "a"}]


def test_postgres_append(clean_db_test_table, invoke_cli):
    invoke_cli(
        ["csv:-", "-o", "postgresql://localhost:5432/test/test_table"],
        stdin=EXAMPLE_CSV_RAW,
    )
    invoke_cli(
        ["csv:-", "-o", "postgresql://localhost:5432/test/test_table?append=True"],
        stdin=EXAMPLE_CSV_RAW,
    )
    stdout = invoke_cli(
        [
            "postgresql://localhost:5432/test",
            "-q",
            "select name from test_table ORDER BY name ASC",
            "-o",
            "json:-",
        ]
    )
    assert json.loads(stdout) == [
        {"name": "George"},
        {"name": "George"},
        {"name": "Rachel"},
        {"name": "Rachel"},
        {"name": "Steven"},
        {"name": "Steven"},
    ]
