import json

from tests.fixtures.example_raw import EXAMPLE_CSV_RAW

COERCION_TESTS_JSON_RAW = (
    "["
    '{"id":"1.0","name":"Anatoly"},'
    '{"id":"2 ","name":"Bobby"},'
    '{"id":null,"name":"Alice"},'
    '{"id":"","name":"Sofia"}'
    "]"
)


def jsmin(data: str) -> str:
    return data.replace(": ", ":").replace(", ", ",")


def test_coerce_control(invoke_cli):
    """Test no coercion (control test)"""
    cmd = ["json:-", "-o", "json:-"]
    assert invoke_cli(cmd, COERCION_TESTS_JSON_RAW) == COERCION_TESTS_JSON_RAW


def test_coerce_strings(invoke_cli):
    cmd = ["json:-", "--coerce-schema", "{id: str, name: str}", "-o", "json:-"]
    assert invoke_cli(cmd, stdin=COERCION_TESTS_JSON_RAW) == jsmin(
        json.dumps(
            [
                {"id": "1.0", "name": "Anatoly"},
                {"id": "2 ", "name": "Bobby"},
                {"id": None, "name": "Alice"},
                {"id": "", "name": "Sofia"},
            ]
        )
    )


def test_coerce_integers(invoke_cli):
    """
    Note: Setting schema to 'int' will actually give us floats for the COERCION_TESTS_JSON_RAW sample data set.
    This is a bug, unfortunately, and not desired.

    This test serves more as docummentation of existing behavior, rather than verifying there are no bugs. This is a
    bug...

    Details at https://github.com/personalcomputer/tableconv/blob/f9f9f3c/tableconv/core.py#L209
    """
    cmd = ["json:-", "--coerce-schema", "{id: int, name: str}", "-o", "json:-"]
    assert invoke_cli(cmd, stdin=COERCION_TESTS_JSON_RAW) == jsmin(
        json.dumps(
            [
                {"id": 1.0, "name": "Anatoly"},
                {"id": 2.0, "name": "Bobby"},
                {"id": None, "name": "Alice"},
                {"id": None, "name": "Sofia"},
            ]
        )
    )


def test_coerce_integers_invalid(invoke_cli):
    cmd = ["json:-", "--coerce-schema", "{id: int, name: int}", "-o", "json:-"]
    _, stderr = invoke_cli(
        cmd,
        stdin=COERCION_TESTS_JSON_RAW,
        assert_nonzero_exit_code=True,
        capture_stderr=True,
        use_subprocess=True,
    )
    assert "error" in stderr.lower()
    assert "schema" in stderr.lower()


def test_coerce_floats(invoke_cli):
    cmd = ["json:-", "--coerce-schema", "{id: float, name: str}", "-o", "json:-"]
    assert invoke_cli(cmd, stdin=COERCION_TESTS_JSON_RAW) == jsmin(
        json.dumps(
            [
                {"id": 1.0, "name": "Anatoly"},
                {"id": 2.0, "name": "Bobby"},
                {"id": None, "name": "Alice"},
                {"id": None, "name": "Sofia"},
            ]
        )
    )


def test_coerce_datetimes(invoke_cli):
    """
    This is not exactly the desireable behavior! Nothing depends on the current behavior of datetime coercing. This
    test is just here as documentation of current behavior, or here to be used as a base for editing later once the
    datetime coercing code has had more thought put into it.
    """
    cmd = ["json:-", "--coerce-schema", "{id: int, time: datetime}", "-o", "json:-"]
    assert json.loads(
        invoke_cli(
            cmd,
            stdin=json.dumps(
                [
                    {"id": 1, "time": "2022-01-18T22:00:00+00:00"},
                    {"id": 2, "time": "2022-01-17T22:00:00+00:00"},
                ]
            ),
        )
    ) == [
        {"id": 1, "time": 1642543200000},
        {"id": 2, "time": 1642456800000},
    ]


def test_restrict_scheme(invoke_cli):
    """Test ignoring extraneous columns in a file (ignoring "id" column)"""
    cmd = [
        "csv:-",
        "--schema",
        "{name: str, date: int}",
        "--restrict-schema",
        "-o",
        "json:-",
    ]
    assert json.loads(invoke_cli(cmd, stdin=EXAMPLE_CSV_RAW)) == [
        {"name": "George", "date": 2023},
        {"name": "Steven", "date": 1950},
        {"name": "Rachel", "date": 1995},
    ]


def test_missing_column(invoke_cli):
    """
    Test the schema including a column missing from the data. The "missing" colummn should be manifested in the
    results (with empty data).
    """
    cmd = [
        "csv:-",
        "--schema",
        "{id: int, name: str, date: int, test: str}",
        "-o",
        "json:-",
    ]
    assert json.loads(invoke_cli(cmd, stdin=EXAMPLE_CSV_RAW)) == [
        {"id": 1, "name": "George", "date": 2023, "test": None},
        {"id": 2, "name": "Steven", "date": 1950, "test": None},
        {"id": 3, "name": "Rachel", "date": 1995, "test": None},
    ]
