import sys
from io import IOBase
from typing import Any, Dict, Optional, Union

import pandas as pd

from tableconv.uri import parse_uri


class FileAdapterMixin():

    @staticmethod
    def get_example_url(scheme):
        return f'example.{scheme}'

    @classmethod
    def load(cls, uri: str, query: Optional[str]) -> pd.DataFrame:
        parsed_uri = parse_uri(uri)
        if parsed_uri.authority == '-' or parsed_uri.path == '-' or parsed_uri.path == '/dev/fd/0':
            path: Union[str, IOBase] = sys.stdin  # type: ignore[assignment]
        else:
            path = parsed_uri.path
        df = cls.load_file(parsed_uri.scheme, path, parsed_uri.query)
        return cls._query_in_memory(df, query)  # type: ignore[attr-defined]

    @classmethod
    def dump(cls, df, uri: str):
        parsed_uri = parse_uri(uri)
        if parsed_uri.authority == '-' or parsed_uri.path == '-' or parsed_uri.path == '/dev/fd/1':
            parsed_uri.path = '/dev/fd/1'
        try:
            cls.dump_file(df, parsed_uri.scheme, parsed_uri.path, parsed_uri.query)
        except BrokenPipeError:
            if parsed_uri.path == '/dev/fd/1':
                # Ignore broken pipe error when outputting to stdout
                return
            raise
        if parsed_uri.path != '/dev/fd/1':
            return parsed_uri.path

    @classmethod
    def load_file(cls, scheme: str, path: Union[str, IOBase], params: Dict[str, Any]) -> pd.DataFrame:
        if isinstance(path, IOBase):
            text = path.read()
        else:
            with open(path, 'r') as f:
                text = f.read()
        return cls.load_text_data(scheme, text, params)

    @classmethod
    def dump_file(cls, df: pd.DataFrame, scheme: str, path: str, params: Dict[str, Any]) -> None:
        with open(path, 'w', newline='') as f:
            data = cls.dump_text_data(df, scheme, params)
            try:
                f.write(data)
            except BrokenPipeError:
                if path == '/dev/fd/1':
                    # Ignore broken pipe error when outputting to stdout
                    return
                raise
        if data[-1] != '\n' and path == '/dev/fd/1' and sys.stdout.isatty():
            print()

    @classmethod
    def load_text_data(cls, scheme: str, data: str, params: Dict[str, Any]) -> pd.DataFrame:
        raise NotImplementedError

    @classmethod
    def dump_text_data(cls, df: pd.DataFrame, scheme: str, params: Dict[str, Any]) -> str:
        raise NotImplementedError
