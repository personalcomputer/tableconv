import logging

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


def query_in_memory(df: pd.DataFrame, query: str) -> pd.DataFrame:
    import duckdb
    flatten_arrays_for_duckdb(df)
    duck_conn = duckdb.connect(database=':memory:', read_only=False)
    duck_conn.register('data', df)
    try:
        duck_conn.execute(query)
    except RuntimeError as exc:
        raise InvalidQueryError(*exc.args) from exc
    result_df = duck_conn.fetchdf()
    return result_df
