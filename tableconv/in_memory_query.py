import logging
from typing import List, Tuple

import numpy as np
import pandas as pd

from tableconv.exceptions import InvalidQueryError

logger = logging.getLogger(__name__)


def flatten_arrays_for_duckdb(df: pd.DataFrame) -> None:
    """
    DuckDB doesn't support creating columns of arrays. It returns the values always as NaN. So, as a workaround, convert
    all array columns to string.

    The docs aren't clear to me, so this understanding may not be entirely correct. References:
    - https://duckdb.org/docs/sql/data_types/nested
    - https://github.com/duckdb/duckdb/issues/1421
    """
    flattened = set()
    for col_name, dtype in zip(df.dtypes.index, df.dtypes):
        if dtype == np.dtype('O'):
            # "Object" type. anything non-numeric, or of mixed-type, is type Object in pandas. So we need to further
            # specifically inspect for arrays.
            if df[col_name].apply(lambda x: isinstance(x, list)).any():
                df[col_name] = df[col_name].astype(str)
                flattened.add(col_name)
    if flattened:
        logger.warning(f'Flattened some columns into strings for in-memory query: {", ".join(flattened)}')


def pre_process(dfs, query) -> Tuple:
    """
    Very weak hack to add support for a new type of transformation within the existing language of SQL: gives us very
    weak version of a `transpose()` function. Warning: this actually mutates `df`s.
    """
    if "transpose(data)" not in query:
        return dfs, query

    ANTI_CONFLICT_STR = "2kMC"  # (random text)
    transposed_data_table_name = f"transposed_data_{ANTI_CONFLICT_STR}"
    query = query.replace("transpose(data)", f'"{transposed_data_table_name}"')
    for table_name, df in dfs:
        if table_name == "data":
            data_df = df
            break
    transposed_data_df = data_df.transpose(copy=True).reset_index()
    dfs.append((transposed_data_table_name, transposed_data_df))
    return dfs, query


def query_in_memory(dfs: List[Tuple[str, pd.DataFrame]], query: str) -> pd.DataFrame:
    """Warning: Has a side effect of mutating the dfs"""
    import duckdb
    duck_conn = duckdb.connect(database=':memory:', read_only=False)
    dfs, query = pre_process(dfs, query)
    for table_name, df in dfs:
        flatten_arrays_for_duckdb(df)
        duck_conn.register(table_name, df)
    try:
        duck_conn.execute(query)
    except RuntimeError as exc:
        raise InvalidQueryError(*exc.args) from exc
    result_df = duck_conn.fetchdf()
    return result_df
