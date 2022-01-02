import tableconv
from tests.fixtures.simple import EXAMPLE_TSV_RAW, EXAMPLE_CSV_RAW


def test_tsv_to_csv(tmp_path):
    with open(f'{tmp_path}/test.tsv', 'w') as f:
        f.write(EXAMPLE_TSV_RAW)
    tableconv.load_url(f'tsv://{tmp_path}/test.tsv').dump_to_url(f'csv://{tmp_path}/test.csv')
    assert open(f'{tmp_path}/test.csv').read() == EXAMPLE_CSV_RAW + '\n'
