import sys

import pandas as pd

from ...uri import parse_uri


class FileAdapterMixin():

    @staticmethod
    def get_example_url(scheme):
        return f'example.{scheme}'

    @classmethod
    def load(cls, uri, query) -> pd.DataFrame:
        uri = parse_uri(uri)
        if uri.authority == '-' or uri.path == '-' or uri.path == '/dev/fd/0':
            uri.path = sys.stdin
        df = cls.load_file(uri.scheme, uri.path, uri.query)
        return cls._query_in_memory(df, query)

    @classmethod
    def dump(cls, df, uri):
        uri = parse_uri(uri)
        if uri.authority == '-' or uri.path == '-' or uri.path == '/dev/fd/1':
            uri.path = '/dev/fd/1'
        try:
            cls.dump_file(df, uri.scheme, uri.path, uri.query)
        except BrokenPipeError:
            if uri.path == '/dev/fd/1':
                # Ignore broken pipe error when outputting to stdout
                return
            raise
        if uri.path != '/dev/fd/1':
            return uri.path

    @classmethod
    def load_file(cls, scheme, path, query_args) -> pd.DataFrame:
        if hasattr(path, 'read'):
            text = path.read()
        else:
            with open(path, 'r') as f:
                text = f.read()
        return cls.load_text_data(scheme, text, query_args)

    @classmethod
    def dump_file(cls, df, scheme, path, query_args) -> None:
        with open(path, 'w', newline='') as f:
            data = cls.dump_text_data(df, scheme, query_args)
            try:
                f.write(data)
            except BrokenPipeError:
                if path == '/dev/fd/1':
                    # Ignore broken pipe error when outputting to stdout
                    return
                raise
        if data[-1] != '\n' and '/dev/fd/1' and sys.stdout.isatty():
            print()

    @classmethod
    def load_text_data(cls, scheme, data: str, query_args) -> pd.DataFrame:
        raise NotImplementedError

    @classmethod
    def dump_text_data(cls, df, scheme, query_args) -> str:
        raise NotImplementedError
