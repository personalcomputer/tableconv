import logging
import os
import re
import uuid

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.exceptions import InvalidQueryError
from tableconv.in_memory_query import flatten_arrays_for_duckdb
from tableconv.uri import parse_uri

logger = logging.getLogger(__name__)


@register_adapter(["duckdb"])
class DuckDBFileAdapter(Adapter):
    @staticmethod
    def get_example_url(scheme):
        return f"example.{scheme}"

    @classmethod
    def load(cls, uri, query):
        import duckdb

        parsed_uri = parse_uri(uri)
        db_path = os.path.abspath(os.path.expanduser(parsed_uri.path))
        conn = duckdb.connect(database=db_path)

        if not query:
            table_bame = parsed_uri.query.get("table", parsed_uri.query.get("table_name", "data"))
            # TODO: escape this. Or use some other duckdb->pandas api. Prepared statements won't work.
            # df = conn.execute(f"SELECT * FROM \"{table_bame}\"").fetchdf()
            query = f'SELECT * FROM "{table_bame}"'

        try:
            df = conn.execute(query).fetchdf()
        except (RuntimeError, duckdb.ParserException, duckdb.CatalogException) as exc:
            raise InvalidQueryError(*exc.args) from exc
        except duckdb.BinderException as exc:
            if re.search(r"Referenced column .+ not found in FROM clause!", exc.args[0]):
                raise InvalidQueryError(*exc.args) from exc
            if "No function matches the given name" in exc.args[0]:
                raise InvalidQueryError(*exc.args) from exc
            raise

        return df

    @classmethod
    def dump(cls, df, uri):
        import duckdb

        parsed_uri = parse_uri(uri)
        table_name = parsed_uri.query.get("table", parsed_uri.query.get("table_name", "data"))
        db_path = os.path.abspath(os.path.expanduser(parsed_uri.path))
        conn = duckdb.connect(database=db_path, read_only=False)

        flatten_arrays_for_duckdb(df)
        temp_table = str(uuid.uuid4().hex)
        conn.register(temp_table, df)
        conn.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM "{temp_table}"')
        return db_path
