import logging

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.exceptions import InvalidParamsError, InvalidQueryError
from tableconv.uri import parse_uri

logger = logging.getLogger(__name__)


@register_adapter(["osquery"], read_only=True)
class OSQuery(Adapter):
    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}://processes"

    @staticmethod
    def load(uri, query):
        import osquery

        parsed_uri = parse_uri(uri)
        table = parsed_uri.authority or parsed_uri.path
        if not table and not query:
            raise InvalidParamsError(
                "Please pass a SELECT SQL query to run (-q <sql>), or include a table in the URI"
                " query string to dump a whole table."
            )
        if table and query:
            raise InvalidParamsError(
                "Please either pass a SELECT SQL query to run (-q <sql>), or include a table in the URI"
                " query string to dump a whole table. Do not pass both."
            )
        if table:
            query = f'SELECT * FROM "{table}"'

        instance = osquery.SpawnInstance()
        instance.open()
        result = instance.client.query(query)
        if result.status.code != 0:
            raise InvalidQueryError(result.status.message)
        return pd.DataFrame.from_records(result.response)
