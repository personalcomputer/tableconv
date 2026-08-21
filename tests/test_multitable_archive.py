import pandas as pd
import pytest

from tableconv.adapters.df.file_adapter_mixin import _archive_ext
from tableconv.core import dump_multitable_to_url, load_multitable_from_url


def test_archive_ext_matches_compound_extensions():
    assert _archive_ext("/tmp/data.tar.gz") == ".tar.gz"
    assert _archive_ext("/tmp/data.tar.zstd") == ".tar.zstd"
    assert _archive_ext("/tmp/data.tar.bz2") == ".tar.bz2"
    assert _archive_ext("/tmp/data.tgz") == ".tgz"
    assert _archive_ext("/tmp/data.tbz2") == ".tbz2"
    assert _archive_ext("/tmp/data.tar") == ".tar"
    assert _archive_ext("/tmp/data.zip") == ".zip"
    assert _archive_ext("/tmp/data.csv") is None
    assert _archive_ext("/tmp/data") is None


@pytest.mark.parametrize("ext", [".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2"])
def test_multitable_archive_round_trip(tmp_path, ext):
    df = pd.DataFrame({"id": [1, 2], "name": ["alpha", "beta"]})
    uri = f"csv://{tmp_path}/out{ext}"
    dump_multitable_to_url(iter([("users", df)]), uri)
    assert (tmp_path / f"out{ext}").exists()
    tables = dict(load_multitable_from_url(uri))
    assert list(tables["users"]["name"]) == ["alpha", "beta"]


def test_multitable_archive_unsupported_format(tmp_path):
    df = pd.DataFrame({"id": [1]})
    with pytest.raises(ValueError, match="Unsupported format"):
        dump_multitable_to_url(iter([("users", df)]), f"csv://{tmp_path}/out.bogus")


def test_multitable_tar_zstd_missing_dep_error(tmp_path):
    try:
        import zstandard  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("zstandard is installed; cannot exercise missing-dependency path")
    df = pd.DataFrame({"id": [1]})
    with pytest.raises(RuntimeError, match="zstandard"):
        dump_multitable_to_url(iter([("users", df)]), f"csv://{tmp_path}/out.tar.zstd")


def test_multitable_tar_zstd_round_trip(tmp_path):
    pytest.importorskip("zstandard")
    df = pd.DataFrame({"id": [1, 2], "name": ["alpha", "beta"]})
    uri = f"csv://{tmp_path}/out.tar.zstd"
    dump_multitable_to_url(iter([("users", df)]), uri)
    assert (tmp_path / "out.tar.zstd").exists()
    tables = dict(load_multitable_from_url(uri))
    assert list(tables["users"]["name"]) == ["alpha", "beta"]
