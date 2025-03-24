import logging
import re

import numpy as np
import pandas as pd

from tableconv.exceptions import InvalidQueryError

logger = logging.getLogger(__name__)


def flatten_arrays_for_duckdb(df: pd.DataFrame) -> None:
    """
    I've struggled to make DuckDB support creating columns of arrays. In my attempts, it returns the values always as
    NaN. So, as a workaround, convert all array columns to string.

    The docs aren't clear to me, so my understanding is incomplete. Some references:
    - https://duckdb.org/docs/sql/data_types/nested
    - https://github.com/duckdb/duckdb/issues/1421
    """
    flattened = set()
    for col_name, dtype in zip(df.dtypes.index, df.dtypes, strict=False):
        if dtype == np.dtype("O"):
            # "Object" type. anything non-numeric, or of mixed-type, is type Object in pandas. So we need to further
            # specifically inspect for arrays.
            if df[col_name].apply(lambda x: isinstance(x, list)).any():
                df[col_name] = df[col_name].astype(str)
                flattened.add(col_name)
    if flattened:
        flattened_display = ", ".join([str(column) for column in flattened])
        logger.warning(f"Flattened some columns into strings for in-memory query: {flattened_display}")


def pre_process(dfs, query) -> tuple:
    """
    Preprocess the SQL query, to allow us to extend the DuckDB query language. Supported extensions:
    - omitting `FROM data` clause
    - omitting `SELECT` verb
    - transpose()
    - from_unix()
    - from_iso8601()

    Warning: this function preprocesses both the query and the dfs, i.e. it actually mutates `dfs` too!
    Warning: this is very poorly implemented! Uses ultra-basic parsing to match parenthesis and find arguments.
    """
    # infer missing `FROM data``
    if not re.search(r"\bFROM\b", query, re.IGNORECASE):
        post_from_clauses = ["ORDER BY", "LIMIT", "GROUP BY", "HAVING", "WHERE"]
        insert_position = len(query)
        for clause in post_from_clauses:
            pos = query.upper().find(clause)
            if pos != -1 and pos < insert_position:
                insert_position = pos
        query = f"{query[:insert_position]} FROM data {query[insert_position:]}"
        logger.debug("Query was missing any FROM clause. Inferring `FROM data` clause..")

    # infer missing `SELECT`
    if not re.search(r"\bSELECT\b", query, re.IGNORECASE):
        query = f"SELECT {query}"
        if query.startswith("SELECT  FROM "):
            query = query.replace("SELECT  FROM ", "SELECT * FROM ")
            logger.debug("Query was missing any SELECT statement. Inferring `SELECT *` at start of query..")
        else:
            logger.debug("Query was missing any SELECT statement. Inferring `SELECT` at start of query..")

    # Expand `transpose()` macro
    if "transpose(data)" in query:
        ANTI_CONFLICT_STR = "027eade341cf"  # (rare/unique sentinel string to avoid name conflicts)
        transposed_data_table_name = f"transposed_data_{ANTI_CONFLICT_STR}"
        query = query.replace("transpose(data)", f'"{transposed_data_table_name}"')
        for table_name, df in dfs:
            if table_name == "data":
                data_df = df
                break
        transposed_data_df = data_df.transpose(copy=True).reset_index()
        transposed_data_df.columns = transposed_data_df.iloc[0].values
        transposed_data_df = transposed_data_df.iloc[1:].reset_index(drop=True)

        dfs.append((transposed_data_table_name, transposed_data_df))
        logger.debug("Expanded `transpose(data)` macro")

    # Expand `from_unix()` macro
    old_query = query
    query = re.sub(
        r"\b(?:from_)?unix\((.+?)\)", r"(TIMESTAMP '1970-01-01 00:00:00' + to_seconds(\1))", query, flags=re.IGNORECASE
    )
    if old_query != query:
        logger.debug("Expanded `from_unix()` macro")

    # Expand `from_iso8601()` macro
    old_query = query
    query = re.sub(r"\b(?:from_)?iso8601\((.+?)\)", r"CAST(\1 AS TIMESTAMP)", query, flags=re.IGNORECASE)
    if old_query != query:
        logger.debug("Expanded `from_iso8601()` macro")

    return dfs, query


def query_in_memory(dfs: list[tuple[str, pd.DataFrame]], query: str) -> pd.DataFrame:
    """Warning: Has a side effect of mutating the dfs"""
    import duckdb  # inline import for performance

    duck_conn = duckdb.connect(database=":memory:", read_only=False)
    dfs, query = pre_process(dfs, query)
    for table_name, df in dfs:
        flatten_arrays_for_duckdb(df)
        duck_conn.register(table_name, df)
    logger.debug(f"Running query in duckdb: {query}")
    try:
        duck_conn.execute(query)
    except (RuntimeError, duckdb.ParserException, duckdb.CatalogException) as exc:
        raise InvalidQueryError(*exc.args) from exc
    # except duckdb.StandardException as exc:  # type: ignore[attr-defined]  # backwards-compat with old duckdb
    #     if "Parser Error" in exc.args[0]:
    #         raise InvalidQueryError(*exc.args) from exc
    #     raise
    except duckdb.BinderException as exc:
        if re.search(r"Referenced column .+ not found in FROM clause!", exc.args[0]):
            raise InvalidQueryError(*exc.args) from exc
        if "No function matches the given name" in exc.args[0]:
            raise InvalidQueryError(*exc.args) from exc
        raise
    result_df = duck_conn.fetchdf()
    return result_df
