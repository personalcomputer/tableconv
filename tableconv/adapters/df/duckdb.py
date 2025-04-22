import logging
import os
import re

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.exceptions import InvalidQueryError
from tableconv.uri import parse_uri

logger = logging.getLogger(__name__)


@register_adapter(["duckdb"], read_only=True)
class DuckDBFile(Adapter):
    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}://example.duckdb"

    @staticmethod
    def load(uri, query):
        import duckdb

        parsed_uri = parse_uri(uri)
        db_path = os.path.abspath(os.path.expanduser(parsed_uri.path))
        conn = duckdb.connect(database=db_path)

        if not query:
            table = parsed_uri.query["table"]
            # TODO: escape this. Or use some other duckdb->pandas api. Prepared statements won't work.
            # df = conn.execute(f"SELECT * FROM \"{table}\"").fetchdf()
            query = f'SELECT * FROM "{table}"'

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
