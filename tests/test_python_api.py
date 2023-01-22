import filecmp

import tableconv
from tests.conftest import FIXTURES_DIR
from tests.fixtures.example_raw import EXAMPLE_RECORDS


def test_tsv_to_csv(tmp_path):
    tableconv.load_url(FIXTURES_DIR / "example.tsv").dump_to_url(f"csv://{tmp_path}/test.csv")
    assert filecmp.cmp(f"{tmp_path}/test.csv", FIXTURES_DIR / "example.csv")


def test_export_as_dict_records(tmp_path):
    records = tableconv.load_url(FIXTURES_DIR / "example.tsv").as_dict_records()
    assert records == EXAMPLE_RECORDS
