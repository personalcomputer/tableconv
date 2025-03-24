import copy
import logging
import os
import shlex
import shutil
import subprocess
import sys
from io import IOBase
from typing import Any

import pandas as pd

from tableconv.uri import encode_uri, parse_uri

logger = logging.getLogger(__name__)


class FileAdapterMixin:

    @staticmethod
    def get_example_url(scheme):
        return f"example.{scheme}"

    @classmethod
    def load(cls, uri: str, query: str | None) -> pd.DataFrame:
        parsed_uri = parse_uri(uri)
        if parsed_uri.authority == "-" or parsed_uri.path == "-" or parsed_uri.path == "/dev/fd/0":
            path: str | IOBase = sys.stdin  # type: ignore[assignment]
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
        parsed_uri.path, ext = os.path.splitext(parsed_uri.path)
        if ext:
            if ext in [".zip", ".tar", ".tar.zstd", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2"]:
                # TODO: this archiving tool is not packaged with tableconv. Find a good one..
                cmd(["extract", parsed_uri.path + ext, "--output", parsed_uri.path])
            else:
                raise ValueError(
                    f"Unsupported format: {ext}. Multitable file output only supports folders or common "
                    "archive formats."
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

        archive_format = None
        parsed_uri.path, ext = os.path.splitext(parsed_uri.path)
        if ext:
            if ext in [".zip", ".tar", ".tar.zstd", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2"]:
                archive_format = ext.strip(".")
            else:
                raise ValueError(
                    f"Unsupported format: {ext}. Multitable file output only supports folders or common "
                    "archive formats."
                )

        os.makedirs(parsed_uri.path, exist_ok=False)
        try:
            for table_name, df in df_multitable:
                table_uri_parsed = copy.copy(parsed_uri)
                table_uri_parsed.path = os.path.join(table_uri_parsed.path, f"{table_name}.{parsed_uri.scheme}")
                logger.info(f"Dumping table {encode_uri(table_uri_parsed)}")
                cls.dump(df, encode_uri(table_uri_parsed))

            if archive_format:
                # TODO: this archiving tool is not packaged with tableconv. Find a good one..
                cmd(["package.py", archive_format, parsed_uri.path, "--output", parsed_uri.path + ext])
        finally:
            if archive_format or not os.listdir(parsed_uri.path):
                logging.debug(f"Removing temp directory {parsed_uri.path}")
                shutil.rmtree(parsed_uri.path)


def cmd(args, **kwargs):
    logging.info(f"Running command: {shlex.join(args)}")
    return subprocess.run(args, check=True, **kwargs)
