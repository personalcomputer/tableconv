from typing import List, Optional

import pandas as pd

from ...in_memory_query import query_in_memory


class Adapter:
    text_based = False

    @classmethod
    def _query_in_memory(cls, df, query):
        if query:
            return query_in_memory(df, query)
        return df

    @classmethod
    def get_example_url(cls, scheme: str) -> str:
        raise NotImplementedError(f'get_example_url not defined for {scheme}')

    @classmethod
    def load(cls, uri: str, query: str) -> pd.DataFrame:
        raise NotImplementedError

    @classmethod
    def dump(cls, df: pd.DataFrame, uri: str) -> Optional[str]:
        raise NotImplementedError


adapters = {}
read_adapters = {}
write_adapters = {}


def register_adapter(schemes: List[str], write_only: bool = False, read_only: bool = False):
    def decorator(cls):
        global read_adapters
        global write_adapters
        for scheme in schemes:
            adapters[scheme] = cls
            if not write_only:
                read_adapters[scheme] = cls
            if not read_only:
                write_adapters[scheme] = cls
        return cls
    return decorator
