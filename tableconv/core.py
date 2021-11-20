import logging
import os
import sys
import tempfile
from typing import Any, Dict, Tuple

from pandas.errors import EmptyDataError

from .uri import parse_uri
from .adapters.df import read_adapters, write_adapters
from .adapters.df.base import Adapter
from .in_memory_query import query_in_memory

logger = logging.getLogger(__name__)


def resolve_query_arg(query: str) -> str:
    if not query:
        return None

    if sys.version_info.major > 3 or (sys.version_info.major == 3 and sys.version_info.minor >= 9):
        query = query.removeprefix('file://')
    else:
        if query.startswith('file://'):
            query = query[len('file://'):]

    potential_snippet_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'snippets', query)
    if os.path.exists(potential_snippet_path):
        with open(potential_snippet_path) as f:
            return f.read().strip()

    if os.path.exists(query):
        with open(query) as f:
            return f.read().strip()

    return query


class SuppliedDataError(RuntimeError):
    pass


class IntermediateExchangeTable:
    def __init__(self, df):
        self.df = df

    def dump_to_url(self, url: str, params: Dict[str, Any] = None) -> str:
        scheme = parse_uri(url).scheme
        try:
            write_adapter = write_adapters[scheme]
        except KeyError:
            logger.error(f'Unsupported scheme {scheme}. Please see --help.')
            sys.exit(1)

        logger.debug(f'Exporting data out via {write_adapter.__qualname__} to {url}')
        return write_adapter.dump(self.df, url)

    def get_json_schema(self):
        """
        Warning: This is just experimental / exploratory. The current implementation is also buggy.
        """
        # Consider instead using https://github.com/pandas-dev/pandas/blob/v1.3.2/pandas/io/json/_table_schema.py
        from genson import SchemaBuilder
        builder = SchemaBuilder()
        builder.add_schema({'type': 'object', 'properties': {}})
        for row in self.df.to_dict(orient='records'):
            builder.add_object(row)
        return builder.to_schema()

    def query_in_memory(self):
        # TODO refactor to use this
        pass


FSSPEC_SCHEMES = {'https', 'http', 'ftp', 's3', 'gcs', 'sftp', 'scp', 'abfs'}


def parse_source_url(url: str) -> Tuple[str, Adapter]:
    """ Returns source_scheme, read_adapter """
    parsed_url = parse_uri(url)
    source_scheme = parsed_url.scheme

    if source_scheme in FSSPEC_SCHEMES:
        source_scheme = os.path.splitext(parsed_url.path)[1][1:]

    if source_scheme is None:
        logger.error(f'Unable to parse URL "{url}". Please see --help.')
        sys.exit(1)

    try:
        read_adapter = read_adapters[source_scheme]
    except KeyError:
        logger.error(f'Unsupported scheme {source_scheme}. Please see --help.')
        sys.exit(1)

    return source_scheme, read_adapter


def process_and_rewrite_remote_source_url(url: str) -> str:
    """
    If source is a remote file, download a local copy of it first and then rewrite the URL to reference the downloaded file.
    Note: This is an experimental undocumented feature that probably will not continue to be supported in the future.
    Note: This implementation is pretty hacky.
    """
    import fsspec
    logger.info('Source URL is a remote file - attempting to create local copy (via fsspec)')
    temp_file = tempfile.NamedTemporaryFile()
    parsed_url = parse_uri(url)
    with fsspec.open(f'{parsed_url.scheme}://{parsed_url.authority}{parsed_url.path}') as network_file:
        temp_file.write(network_file.read())
    temp_file.flush()
    encoded_query_params = '?' + '&'.join((f'{key}={value}' for key, value in parsed_url.query.items()))
    new_url = f'{os.path.splitext(parsed_url.path)[1][1:]}://{temp_file.name}{encoded_query_params if url.query else ""}'
    logger.info(f'Cached remote file as {new_url}')
    return new_url


def load_url(url: str, params: Dict[str, Any] = None, query: str = None, filter_sql: str = None
             ) -> IntermediateExchangeTable:
    if parse_uri(url).scheme in FSSPEC_SCHEMES:
        url = process_and_rewrite_remote_source_url(url)

    source_scheme, read_adapter = parse_source_url(url)
    query = resolve_query_arg(query)
    filter_sql = resolve_query_arg(filter_sql)

    logger.debug(f'Loading data in via {read_adapter.__qualname__} from {url}')
    try:
        df = read_adapter.load(url, query)
    except EmptyDataError as e:
        raise SuppliedDataError(f'Empty data source {url}: {str(e)}') from e
    if df.empty:
        raise SuppliedDataError(f'Empty data source {url}')

    # Run in-memory filters
    if filter_sql:
        logger.debug('Running intermediate filter sql query in-memory')
        df = query_in_memory(df, filter_sql)

    if df.empty:
        raise SuppliedDataError('No rows returned by intermediate filter sql query')

    table = IntermediateExchangeTable(df)
    table.source_scheme = source_scheme

    return table
