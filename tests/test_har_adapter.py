import json

HAR_RAW = json.dumps(
    {
        "log": {
            "version": "1.2",
            "creator": {"name": "test", "version": "1.0"},
            "entries": [
                {
                    "startedDateTime": "2024-01-01T00:00:00Z",
                    "time": 12.3,
                    "request": {"method": "GET", "url": "https://a.example/"},
                    "response": {"status": 200, "statusText": "OK"},
                },
                {
                    "startedDateTime": "2024-01-01T00:00:01Z",
                    "time": 45.6,
                    "request": {"method": "POST", "url": "https://b.example/"},
                    "response": {"status": 500, "statusText": "ERR"},
                },
            ],
        }
    }
)

# The flattened representation that the json-data-model adapters produce from HAR_RAW by default
# (preserve_nesting=False, the same default as the json/jsonl adapters).
FLATTENED_ENTRIES = [
    {
        "startedDateTime": "2024-01-01T00:00:00Z",
        "time": 12.3,
        "request.method": "GET",
        "request.url": "https://a.example/",
        "response.status": 200,
        "response.statusText": "OK",
    },
    {
        "startedDateTime": "2024-01-01T00:00:01Z",
        "time": 45.6,
        "request.method": "POST",
        "request.url": "https://b.example/",
        "response.status": 500,
        "response.statusText": "ERR",
    },
]


def test_har_load_flattens_entries(invoke_cli):
    stdout = invoke_cli(["har:-", "-o", "json:-"], stdin=HAR_RAW)
    assert json.loads(stdout) == FLATTENED_ENTRIES


def test_har_load_preserve_nesting(invoke_cli):
    stdout = invoke_cli(["har:-?preserve_nesting=true", "-o", "json:-"], stdin=HAR_RAW)
    assert json.loads(stdout) == json.loads(HAR_RAW)["log"]["entries"]


def test_har_roundtrip(tmp_path, invoke_cli):
    # har->json->har->json confirms the extracted entries survive a round-trip through another format.
    json_out = tmp_path / "mid.json"
    invoke_cli(["har:-", "-o", f"json:{json_out}"], stdin=HAR_RAW)
    stdout = invoke_cli([f"json:{json_out}", "-o", "json:-"])
    assert json.loads(stdout) == FLATTENED_ENTRIES


def test_har_load_missing_log_field(invoke_cli):
    _, stderr = invoke_cli(
        ["har:-", "-o", "json:-"], stdin=json.dumps({"foo": 1}), assert_nonzero_exit_code=True, capture_stderr=True
    )
    assert "traceback" not in stderr.lower()
    assert "log" in stderr.lower()


def test_har_load_entries_not_array(invoke_cli):
    _, stderr = invoke_cli(
        ["har:-", "-o", "json:-"],
        stdin=json.dumps({"log": {"entries": {}}}),
        assert_nonzero_exit_code=True,
        capture_stderr=True,
    )
    assert "traceback" not in stderr.lower()
    assert "array" in stderr.lower()
