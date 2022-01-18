import logging
import os
import re
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import ciso8601
import pandas as pd
from pandas.errors import EmptyDataError as pd_EmptyDataError

from tableconv.adapters.df import read_adapters, write_adapters
from tableconv.adapters.df.base import Adapter
from tableconv.exceptions import (EmptyDataError, InvalidLocationReferenceError, InvalidURLSyntaxError,
                                  UnrecognizedFormatError, SchemaCoercionError)
from tableconv.in_memory_query import query_in_memory
from tableconv.uri import parse_uri

logger = logging.getLogger(__name__)


def resolve_query_arg(query: Optional[str]) -> Optional[str]:
    if not query:
        return None

    if query.startswith('file://'):
        # Note: python 3.9+ has str.removeprefix. Is there a backport/polyfill?
        query = query[len('file://'):]

    potential_snippet_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'snippets', query
    )
    if os.path.exists(potential_snippet_path):
        with open(potential_snippet_path) as f:
            return f.read().strip()

    if os.path.exists(query):
        with open(query) as f:
            return f.read().strip()

    return query


class IntermediateExchangeTable:
    def __init__(self, df=None, from_df: pd.DataFrame = None, from_dict_records: Optional[List[Dict[str, Any]]] = None):
        """
        tableconv's abstract intermediate tabular data type.

        Normally you should acquire a ``IntermediateExchangeTable`` by loading in data from a URL using :ref:load_url.
        However, if your data is already in a python native datatype, you can directly put it into a
        ``IntermediateExchangeTable`` by passing it in using one of the two available Python native forms:

        :param from_df:
            Wrap the provided Pandas Dataframe in a IntermediateExchangeTable.
        :param from_dict_records:
            Wrap the provided List of Dict records in a IntermediateExchangeTable.

        :raises tableconv.EmptyDataError:
            Raised if the supplied datasource is empty.
        """
        if sum([df is not None, from_df is not None, from_dict_records is not None]) != 1:
            raise ValueError('Please pass one and only one of either df, from_df, or from_dict_records')
        if df is not None:
            self.df = df
        if from_df is not None:
            self.df = from_df
        if from_dict_records is not None:
            self.df = pd.DataFrame.from_records(from_dict_records)
        if self.df.empty:
            raise EmptyDataError

    def dump_to_url(self, url: str, params: Optional[Dict[str, Any]] = None) -> str:
        """
        Export the table in the format and location identified by url.

        :return:
            A "permalink" url that can be used to access the exported data. This URL is normally identical to the URL
            that was passed in, but not always in cases where e.g. a new ID needed to be dynamically generated during
            the export, or in cases when the passed in URL was relative or otherwise vague.

        :raises tableconv.InvalidURLError:
            Raised if the provided URL itself is invalid. (either an unsupported/unrecognized data format, an incorrect
            URL syntax, or incorrect URL parameters).
        :raises tableconv.DataError:
            Raised if the data is incompatible with sending to that URL for any reason. (e.g. appending to an existing
            table and there is a schema mismatch)
        """
        scheme = parse_uri(url).scheme
        try:
            write_adapter = write_adapters[scheme]
        except KeyError:
            raise UnrecognizedFormatError(f'Unsupported scheme {scheme}.')

        if params:
            # TODO: This is a total hack! Implementing real structured table references, including structured passing of
            # params to adapters, is still pending. Right now everything is stringly-typed internally.
            assert '?' not in url
            url += f'?{urllib.parse.urlencode(params)}'
        write_adapter_name = write_adapter.__qualname__  # type: ignore[attr-defined]
        logger.debug(f'Exporting data out via {write_adapter_name} to {url}')
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

    def transform_in_memory(self, sql):
        # TODO refactor to use this
        pass

    def as_dict_records(self) -> List[Dict[str, Any]]:
        """
        Expose the loaded data as a List of Dict records.
        """
        return self.as_pandas_df().to_dict(orient='records')

    def as_pandas_df(self) -> pd.DataFrame:
        """
        Expose the loaded data as a Pandas Dataframe.

        Warning: Mutating the provided DataFrame may corrupt the internal state of the ``IntermediateExchangeTable``
        and prevent the ``IntermediateExchangeTable`` from being used further. If you want to expose as a DataFrame,
        mutate it, and then also continue to use the same ``IntermediateExchangeTable`` afterwards, then please take a
        copy (copy.deepcopy) of the exposed DataFrame.
        """
        return self.df


FSSPEC_SCHEMES = {'https', 'http', 'ftp', 's3', 'gcs', 'sftp', 'scp', 'abfs'}


def parse_source_url(url: str) -> Tuple[str, Adapter]:
    """ Returns source_scheme, read_adapter """
    parsed_url = parse_uri(url)
    source_scheme = parsed_url.scheme

    if source_scheme in FSSPEC_SCHEMES:
        source_scheme = os.path.splitext(parsed_url.path)[1][1:]

    if source_scheme is None:
        raise InvalidURLSyntaxError(f'Unable to parse URL "{url}".')

    try:
        read_adapter = read_adapters[source_scheme]
    except KeyError:
        raise UnrecognizedFormatError(f'Unsupported scheme {source_scheme}.')

    return source_scheme, read_adapter


def process_and_rewrite_remote_source_url(url: str) -> str:
    """
    If source is a remote file, download a local copy of it first and then rewrite the URL to reference the downloaded
    file.

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
    if parsed_url.query:
        encoded_query_params = '?' + '&'.join((f'{key}={value}' for key, value in parsed_url.query.items()))
    else:
        encoded_query_params = ''
    new_url = f'{os.path.splitext(parsed_url.path)[1][1:]}://{temp_file.name}{encoded_query_params}'
    logger.info(f'Cached remote file as {new_url}')
    return new_url


def validate_coercion_schema(schema: Dict[str, str]) -> None:
    SCHEMA_COERCION_SUPPORTED_TYPES = {'datetime', 'str', 'int', 'float'}
    unsupported_schema_types = set(schema.values()) - SCHEMA_COERCION_SUPPORTED_TYPES
    if unsupported_schema_types:
        raise ValueError(f'Unsupported schema type(s): {", ".join(unsupported_schema_types)}')


def coerce_schema(df: pd.DataFrame, schema: Dict[str, str], restrict_schema: bool) -> pd.DataFrame:
    validate_coercion_schema(schema)

    # Add missing columns
    for col in set(schema.keys()) - set(df.columns):
        df[col] = None

    # Coerce the type of pre-existing columns
    for col in set(schema.keys()).intersection(set(df.columns)):
        try:
            if schema[col] == 'datetime':
                df[col] = df.apply(
                    lambda r: ciso8601.parse_datetime(r[col]) if r[col] not in (None, '') else None, axis=1
                )
            elif schema[col] == 'str':
                df[col] = df[col].astype('string')
            elif schema[col] == 'int':
                """
                Important bug to be aware of: because of using pandas dataframes as the internal datastructure, if an
                integer column contains any nulls, pandas forces it to actually be a float column so it can store the
                nulls as NaNs.. So schema coercing to "int" won't actually always result in integers.
                """
                # Remove trailing 0s after decimal point (int() errors on '1.0' input)
                re_decimal = re.compile(r'\.0*\s*$')
                df[col] = df.apply(
                    lambda r: (
                        int(re_decimal.sub('', str(r[col])))
                        if (r[col] not in (None, '') and not pd.isna(r[col]))
                        else None),
                    axis=1
                )
                # df[col] = pd.to_numeric(df[col], downcast='integer')
            elif schema[col] == 'float':
                df[col] = df.apply(
                    lambda r: float(r[col]) if (r[col] not in (None, '') and not pd.isna(r[col])) else None, axis=1
                )
        except (ValueError, TypeError) as exc:
            raise SchemaCoercionError(
                f'Error in coercing schema: Error while coercing "{col}" to {schema[col]}: {exc.args[0]}') from exc

    if restrict_schema:
        # Drop all other columns
        df = df[schema.keys()]

    return df


def warn_if_location_too_large(uri: str):
    """
    If we can determine in advance that the URL points to a large amount of data that is slow to parse, show a warning.
    If we're not able to confirm, or don't know, do nothing. We only makes a weak heuristic attempt to detect and warn.
    """
    path = parse_uri(uri).path
    if os.path.exists(path):
        TWO_GIBIBYTES = 2 * (1024 ** 3)
        if os.stat(path).st_size > TWO_GIBIBYTES:
            # TODO: make this adapter specific
            logger.warning('This looks like a huge table, expect heavy RAM and CPU usage.')


def load_url(url: Union[str, Path], params: Optional[Dict[str, Any]] = None, query: Optional[str] = None,
             filter_sql: Optional[str] = None, schema_coercion: Optional[Dict[str, str]] = None,
             restrict_schema: bool = False) -> IntermediateExchangeTable:
    """
    Load the data referenced by ``url`` into tableconv's abstract intermediate tabular data type
    (:ref:`IntermediateExchangeTable`).

    :param url:
        This can be any URL referencing tabular or psuedo-tabular data. Refer to :ref:Adapters for the supported
        formats.
    :param params:
        These are URL query parameters to add into the URL, for setting various Adapter options. Refer to the
         :ref:Adapters documentation for details.
    :param query:
        To extract only some of the data, provide a query here, to run on the data. This will need to be written in the
        native query language of whatever ddata format you are extracting data from (e.g. SQL for a SQL database), or
        for formats without a native query language (e.g. CSV), the DuckDB SQL syntax is normally supported. Refer to
        the :ref:Adapters documentation for details.
    :param fiter_sql:
        You can transform the data in-memory after loading it by passing in a ``filter_sql`` SELECT query.
        Transformations are powered by DuckDB and uses the DuckDB SQL syntax. Reference the table named ``data`` for
        the raw imported data.
    :param schema_coercion:
        This is an experimental feature. Subject to change. Docummentation unavailable.
    :param restrict_schema:
        This is an experimental feature. Subject to change. Docummentation unavailable.

    :raises tableconv.InvalidURLError:
        Raised if the provided URL cannot be accessed. (anything from an unsupported/unrecognized data format, an
        incorrect URL syntax, a non-existent / non-responsive location, or incorrect URL parameters).
    :raises tableconv.DataError:
        Raised if the data WITHIN the table referenced by the URL is invalid in any way.
    :raises tableconv.EmptyDataError:
        Specific type of DataError that is raised if data can theoretically be loaded, but there are zero records
        available for loading. tableconv doesn't supporting loading an empty schema.
    :raises tableconv.InvalidQueryError:
        Raised if the ``query`` is invalid.
    """
    if isinstance(url, Path):
        url = str(url)
    scheme = parse_uri(url).scheme
    if scheme in FSSPEC_SCHEMES:
        url = process_and_rewrite_remote_source_url(url)

    source_scheme, read_adapter = parse_source_url(url)
    # TODO: Dynamic file resolution is great for CLI but it isn't appropriate for the Python API.
    query = resolve_query_arg(query)
    filter_sql = resolve_query_arg(filter_sql)

    if params:
        # TODO: This is a total hack! Implementing real structured table references, including structured passing of
        # params to adapters, is still pending. Right now everything is stringly-typed internally.
        assert '?' not in url
        url += f'?{urllib.parse.urlencode(params)}'

    read_adapter_name = read_adapter.__qualname__  # type: ignore[attr-defined]
    logger.debug(f'Loading data in via {read_adapter_name} from {url}')
    warn_if_location_too_large(url)
    try:
        df = read_adapter.load(url, query)
    except pd_EmptyDataError as exc:
        raise EmptyDataError(f'Empty data source {url}: {str(exc)}') from exc
    except FileNotFoundError as exc:
        raise InvalidLocationReferenceError(f'{url} not found: {str(exc)}') from exc
    if df.empty:
        raise EmptyDataError(f'Empty data source {url}')

    # Schema coercion
    if schema_coercion:
        df = coerce_schema(df, schema_coercion, restrict_schema)

    # Run in-memory filters
    if filter_sql:
        logger.debug('Running intermediate filter sql query in-memory')
        df = query_in_memory(df, filter_sql)

    if df.empty:
        raise EmptyDataError('No rows returned by intermediate filter sql query')

    table = IntermediateExchangeTable(df)

    return table
