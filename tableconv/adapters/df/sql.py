import configparser
import logging
import os

import pandas as pd

from ...uri import parse_uri
from .base import Adapter, register_adapter

logger = logging.getLogger(__name__)


def resolve_pgcli_uri_alias(dsn):
    """
    Hidden feature: Use configured database uri aliases. Currently only supported for aliases configured for postgres
    and configured in the pgcli config format.
    """
    config = configparser.ConfigParser()
    config.read(os.path.expanduser('~/.config/pgcli/config'))
    if 'alias_dsn' in config and dsn in config['alias_dsn']:
        return config['alias_dsn'][dsn]
    return None


@register_adapter(['postgres', 'postgis', 'postgresql', 'sqlite', 'sqlite3', 'mysql', 'mssql', 'oracle'])
class SQLAdapter(Adapter):

    @staticmethod
    def get_example_url(scheme):
        if scheme.startswith('sqlite'):
            return f'{scheme}:///tmp/example.db'
        else:
            return f'{scheme}://127.0.0.1:5432/example_db'

    @staticmethod
    def _get_engine_and_table_from_uri(parsed_uri):
        from sqlalchemy import create_engine
        database_is_filename = (
            '..' in parsed_uri.path
            or '~' in parsed_uri.path
            or os.path.splitext(parsed_uri.path)[1] in ('.db', '.sqlite3', '.sqlite', '.sql')
        )
        if database_is_filename:
            parsed_uri.path = os.path.abspath(os.path.expanduser(parsed_uri.path))
        table = None
        if parsed_uri.authority is None:
            # local file specified via path only (no hostname)
            assert parsed_uri.path.endswith('.sqlite3') or parsed_uri.path.endswith('.sqlite') or parsed_uri.scheme in ('sqlite', 'sqlite3')
            alchemy_uri = f'sqlite:///{parsed_uri.path}'
        else:
            # Resolve scheme aliases
            if parsed_uri.scheme == 'sqlite3':
                parsed_uri.scheme = 'sqlite'
            if parsed_uri.scheme in ('postgres', 'postgis'):
                parsed_uri.scheme = 'postgresql'

            if parsed_uri.scheme == 'postgresql' and resolve_pgcli_uri_alias(parsed_uri.authority):
                alchemy_uri = resolve_pgcli_uri_alias(parsed_uri.authority).replace('postgres://', 'postgresql://')
            else:
                if database_is_filename:
                    database = parsed_uri.path
                else:
                    if os.path.split(parsed_uri.path.strip('/'))[0]:
                        database, table = os.path.split(parsed_uri.path.strip('/'))
                    else:
                        database = parsed_uri.path
                    database = database.strip('/')
                alchemy_uri = f'{parsed_uri.scheme}://{parsed_uri.authority}/{database}'
        if not table and 'table' in parsed_uri.query:
            table = parsed_uri.query['table']
        logger.debug(F'Connecting with SQLAlchemy: {alchemy_uri}')
        engine = create_engine(alchemy_uri)
        return engine, table

    @staticmethod
    def load(uri, query):
        from sqlalchemy import text as sqlalchemy_text
        engine, table = SQLAdapter._get_engine_and_table_from_uri(parse_uri(uri))
        if query:
            return pd.read_sql(sqlalchemy_text(query), engine)
        elif table:
            return pd.read_sql_table(table, engine)
        else:
            raise ValueError('Please pass a SELECT SQL query to run (-q <sql>), or include a `table` in the URI query string to dump a whole table.')

    @staticmethod
    def dump(df, uri):
        parsed_uri = parse_uri(uri)
        engine, table = SQLAdapter._get_engine_and_table_from_uri(parsed_uri)
        if not table:
            raise ValueError('Please pass table name, in format <engine>://<host>:<post>/<db>/<table> or <engine>://<host>:<post>/<db>?table=<table>')
        if 'if_exists' in parsed_uri.query:
            if_exists = parsed_uri.query['if_exists']
        elif 'append' in parsed_uri.query and parsed_uri.query['append'].lower() != 'false':
            if_exists = 'append'
        elif 'overwrite' in parsed_uri.query and parsed_uri.query['overwrite'].lower() != 'false':
            if_exists = 'replace'
        else:
            if_exists = 'fail'
        df.to_sql(table, engine, index=False, if_exists=if_exists)
