import copy
import logging
import os
import shutil
import sys
import tarfile
import zipfile
from io import IOBase
from typing import Any

import pandas as pd

from tableconv.exceptions import URLInaccessibleError
from tableconv.uri import encode_uri, parse_uri

logger = logging.getLogger(__name__)

# Compound extensions listed longest-first so ".tar.gz" matches before ".gz" etc.
_ARCHIVE_EXTS: tuple[str, ...] = (
    ".tar.zstd",
    ".tar.gz",
    ".tar.bz2",
    ".tgz",
    ".tbz2",
    ".tar",
    ".zip",
)
_TAR_WRITE_MODES: dict[str, str] = {
    ".tar": "w:",
    ".tar.gz": "w:gz",
    ".tgz": "w:gz",
    ".tar.bz2": "w:bz2",
    ".tbz2": "w:bz2",
}


def _archive_ext(path: str) -> str | None:
    lower = path.lower()
    for ext in _ARCHIVE_EXTS:
        if lower.endswith(ext):
            return ext
    return None


def _iter_files(root: str):
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            abs_path = os.path.join(dirpath, name)
            yield abs_path, os.path.relpath(abs_path, root)


def _extract_archive(archive_path: str, dest_dir: str) -> None:
    ext = _archive_ext(archive_path)
    if ext == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(dest_dir)
    elif ext == ".tar.zstd":
        _extract_tar_zstd(archive_path, dest_dir)
    elif ext is not None:
        # "r:*" auto-detects gz/bz2/xz compression for .tar and the .tgz/.tbz2 variants.
        with tarfile.open(archive_path, "r:*") as tf:
            tf.extractall(dest_dir, filter="data")
    else:
        raise ValueError(
            f"Unsupported archive format: {archive_path}. Multitable archive I/O only supports: "
            f"{', '.join(_ARCHIVE_EXTS)}."
        )


def _pack_archive(src_dir: str, out_path: str, ext: str) -> None:
    if ext == ".zip":
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for abs_path, arcname in _iter_files(src_dir):
                zf.write(abs_path, arcname)
    elif ext == ".tar.zstd":
        _pack_tar_zstd(src_dir, out_path)
    else:
        with tarfile.open(out_path, _TAR_WRITE_MODES[ext]) as tf:  # type: ignore[call-overload]
            for abs_path, arcname in _iter_files(src_dir):
                tf.add(abs_path, arcname)


def _extract_tar_zstd(archive_path: str, dest_dir: str) -> None:
    try:
        import zstandard
    except ImportError as exc:
        raise RuntimeError(
            "Reading .tar.zstd archives requires the 'zstandard' package.\n"
            " - `uv run --with zstandard tableconv ...`\n"
            " - or `uv add zstandard`"
        ) from exc
    dctx = zstandard.ZstdDecompressor()
    with open(archive_path, "rb") as fh:
        with dctx.stream_reader(fh) as reader:
            # "r|" streams from a non-seekable fileobj, which zstandard's reader is.
            with tarfile.open(fileobj=reader, mode="r|") as tf:
                tf.extractall(dest_dir, filter="data")


def _pack_tar_zstd(src_dir: str, out_path: str) -> None:
    try:
        import zstandard
    except ImportError as exc:
        raise RuntimeError(
            "Writing .tar.zstd archives requires the 'zstandard' package.\n"
            " - `uv run --with zstandard tableconv ...`\n"
            " - or `uv add zstandard`"
        ) from exc
    cctx = zstandard.ZstdCompressor()
    with open(out_path, "wb") as fh:
        with cctx.stream_writer(fh) as writer:
            with tarfile.open(fileobj=writer, mode="w|") as tf:
                for abs_path, arcname in _iter_files(src_dir):
                    tf.add(abs_path, arcname)


class FileAdapterMixin:

    @staticmethod
    def get_example_url(scheme):
        return f"example.{scheme}"

    @classmethod
    def load(cls, uri: str, query: str | None) -> pd.DataFrame:
        parsed_uri = parse_uri(uri)
        if parsed_uri.authority == "-" or parsed_uri.path == "-" or parsed_uri.path == "/dev/fd/0":
            path: str | IOBase = sys.stdin  # type: ignore[assignment]
            if os.environ.get("TABLECONV_MY_DAEMON_SUPERVISOR_PID"):
                raise URLInaccessibleError(
                    "Error: STDIN does not yet work in daemon mode, sorry! Please restructure your command to buffer "
                    "the data to a file, or alternatively `tableconv --kill-daemon`"
                )
        else:
            path = os.path.expanduser(parsed_uri.path)
        df = cls.load_file(parsed_uri.scheme, path, parsed_uri.query)
        return cls._query_in_memory(df, query)  # type: ignore[attr-defined]

    @classmethod
    def dump(cls, df, uri: str):
        parsed_uri = parse_uri(uri)
        if parsed_uri.authority == "-" or parsed_uri.path == "-" or parsed_uri.path == "/dev/fd/1":
            parsed_uri.path = "/dev/fd/1"
        try:
            cls.dump_file(df, parsed_uri.scheme, parsed_uri.path, parsed_uri.query)
        except BrokenPipeError:
            if parsed_uri.path == "/dev/fd/1":
                # Ignore broken pipe error when outputting to stdout
                return
            raise
        if parsed_uri.path != "/dev/fd/1":
            return parsed_uri.path

    @classmethod
    def load_file(cls, scheme: str, path: str | IOBase, params: dict[str, Any]) -> pd.DataFrame:
        if isinstance(path, IOBase):
            text = path.read()
        else:
            with open(path) as f:
                text = f.read()
        return cls.load_text_data(scheme, text, params)

    @classmethod
    def dump_file(cls, df: pd.DataFrame, scheme: str, path: str, params: dict[str, Any]) -> None:
        data = cls.dump_text_data(df, scheme, params)
        with open(path, "w", newline="") as f:
            try:
                f.write(data)
            except BrokenPipeError:
                if path == "/dev/fd/1":
                    # Ignore broken pipe error when outputting to stdout
                    return
                raise
        # if path == "/dev/fd/1" and sys.stdout.isatty() and cls.text_based:
        #   TODO: pipe through a color-highlighter maybe, like either `bat` or python rich library?
        if data and data[-1] != "\n" and path == "/dev/fd/1" and sys.stdout.isatty():
            # TODO: this print should happen for literally every file, stdout or otherwise.
            # however, right now that is causing some sort of corruption in testcases where the \n gets printed at the
            # start of the buffer. Need to fix that first.
            print()

    @classmethod
    def load_text_data(cls, scheme: str, data: str, params: dict[str, Any]) -> pd.DataFrame:
        raise NotImplementedError

    @classmethod
    def dump_text_data(cls, df: pd.DataFrame, scheme: str, params: dict[str, Any]) -> str:
        raise NotImplementedError

    @classmethod
    def load_multitable(cls, uri):
        """Experimental feature. Undocumented. Low Quality."""
        parsed_uri = parse_uri(uri)
        ext = _archive_ext(parsed_uri.path)
        if ext is not None:
            archive_path = parsed_uri.path
            parsed_uri.path = parsed_uri.path[: -len(ext)]
            _extract_archive(archive_path, parsed_uri.path)
        elif os.path.splitext(parsed_uri.path)[1]:
            raise ValueError(
                f"Unsupported format: {os.path.splitext(parsed_uri.path)[1]}. "
                "Multitable file output only supports folders or common archive formats "
                f"({', '.join(_ARCHIVE_EXTS)})."
            )

        for file in os.listdir(parsed_uri.path):
            table_name = os.path.splitext(file)[0]
            table_uri_parsed = copy.copy(parsed_uri)
            table_uri_parsed.path = os.path.join(parsed_uri.path, file)
            logger.info(f"Loading table {encode_uri(table_uri_parsed)}")
            df = cls.load(encode_uri(table_uri_parsed), query=None)
            yield table_name, df

    @classmethod
    def dump_multitable(cls, df_multitable, uri):
        """Experimental feature. Undocumented. Low Quality."""
        parsed_uri = parse_uri(uri)

        ext = _archive_ext(parsed_uri.path)
        if ext is not None:
            parsed_uri.path = parsed_uri.path[: -len(ext)]
        elif os.path.splitext(parsed_uri.path)[1]:
            raise ValueError(
                f"Unsupported format: {os.path.splitext(parsed_uri.path)[1]}. "
                "Multitable file output only supports folders or common archive formats "
                f"({', '.join(_ARCHIVE_EXTS)})."
            )

        os.makedirs(parsed_uri.path, exist_ok=False)
        try:
            for table_name, df in df_multitable:
                table_uri_parsed = copy.copy(parsed_uri)
                table_uri_parsed.path = os.path.join(table_uri_parsed.path, f"{table_name}.{parsed_uri.scheme}")
                logger.info(f"Dumping table {encode_uri(table_uri_parsed)}")
                cls.dump(df, encode_uri(table_uri_parsed))

            if ext is not None:
                _pack_archive(parsed_uri.path, parsed_uri.path + ext, ext)
        finally:
            if ext is not None or not os.listdir(parsed_uri.path):
                logger.debug(f"Removing temp directory {parsed_uri.path}")
                shutil.rmtree(parsed_uri.path)
