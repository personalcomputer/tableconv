import configparser
import copy
import logging
import os

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.exceptions import (
    AppendSchemeConflictError,
    InvalidParamsError,
    InvalidQueryError,
    InvalidURLError,
    TableAlreadyExistsError,
)
from tableconv.uri import encode_uri, parse_uri

logger = logging.getLogger(__name__)


PD_VERSION = [int(i) for i in pd.__version__.split(".")]


def resolve_pgcli_uri_alias(dsn: str) -> str | None:
    """
    Hidden feature: Use configured database uri aliases. Currently only supported for aliases configured for postgres
    and configured in the pgcli config format.
    """
    config = configparser.ConfigParser()
    config.read(os.path.expanduser("~/.config/pgcli/config"))
    if "alias_dsn" in config and dsn in config["alias_dsn"]:
        return config["alias_dsn"][dsn]
    return None


@register_adapter(["postgres", "postgis", "postgresql", "sqlite", "sqlite3", "mysql", "mssql", "oracle"])
class RDBMSAdapter(Adapter):
    @staticmethod
    def get_example_url(scheme):
        if scheme.startswith("sqlite"):
            return f"{scheme}:///tmp/example.db"
        else:
            return f"{scheme}://127.0.0.1:5432/example_db"

    @staticmethod
    def _get_engine_and_table_from_uri(parsed_uri):
        from sqlalchemy import create_engine  # sqlalchemy imports are inlined for startup performance

        database_is_filename = (
            ".." in parsed_uri.path
            or "~" in parsed_uri.path
            or os.path.splitext(parsed_uri.path)[1] in (".db", ".sqlite3", ".sqlite", ".sql")
        )
        if database_is_filename:
            parsed_uri.path = os.path.abspath(os.path.expanduser(parsed_uri.path))
        table = None
        if parsed_uri.authority is None:
            # local file specified via path only (no hostname)
            assert (
                parsed_uri.path.endswith(".sqlite3")
                or parsed_uri.path.endswith(".sqlite")
                or parsed_uri.scheme in ("sqlite", "sqlite3")
            )
            alchemy_uri = f"sqlite:///{parsed_uri.path}"
        else:
            # Resolve scheme aliases
            if parsed_uri.scheme == "sqlite3":
                parsed_uri.scheme = "sqlite"
            if parsed_uri.scheme in ("postgres", "postgis"):
                parsed_uri.scheme = "postgresql"

            if parsed_uri.scheme == "postgresql" and resolve_pgcli_uri_alias(parsed_uri.authority):
                alchemy_uri = resolve_pgcli_uri_alias(parsed_uri.authority).replace("postgres://", "postgresql://")
            else:
                if database_is_filename:
                    database = parsed_uri.path
                else:
                    if os.path.split(parsed_uri.path.strip("/"))[0]:
                        database, table = os.path.split(parsed_uri.path.strip("/"))
                    else:
                        database = parsed_uri.path
                    database = database.strip("/")
                alchemy_uri = f"{parsed_uri.scheme}://{parsed_uri.authority}/{database}"
        if not table and "table" in parsed_uri.query:
            table = parsed_uri.query["table"]
        logger.debug(f"Connecting with SQLAlchemy: {alchemy_uri}")
        engine = create_engine(alchemy_uri)
        return engine, table

    @staticmethod
    def load(uri, query):
        import sqlalchemy.exc  # sqlalchemy imports are inlined for startup performance

        engine, table = RDBMSAdapter._get_engine_and_table_from_uri(parse_uri(uri))

        if query:
            try:
                # if PD_VERSION[0] >= 2 and PD_VERSION[1] >= 2 and PD_VERSION[2] >= 2:
                #     with engine.connect() as conn:
                #         return pd.read_sql(sql=query, con=conn.connection)
                # else:
                return pd.read_sql(sql=query, con=engine)
            except sqlalchemy.exc.ProgrammingError as exc:
                raise InvalidQueryError(*exc.args) from exc
        elif table:
            try:
                return pd.read_sql_table(table, engine)
            except sqlalchemy.exc.OperationalError as exc:
                raise InvalidURLError(*exc.args) from exc
            except ValueError as exc:
                if exc.args[0] == f"Table {table} not found":
                    raise InvalidURLError(*exc.args) from exc
                raise
        else:
            raise InvalidParamsError(
                "Please pass a SELECT SQL query to run (-q <sql>), or include a `table` in the URI"
                " query string to dump a whole table."
            )

    @staticmethod
    def dump(df, uri):
        import sqlalchemy.exc  # sqlalchemy imports are inlined for startup performance

        parsed_uri = parse_uri(uri)
        engine, table = RDBMSAdapter._get_engine_and_table_from_uri(parsed_uri)
        if not table:
            raise InvalidParamsError(
                "Please pass table name, in format <engine>://<host>:<post>/<db>/<table> or "
                "<engine>://<host>:<post>/<db>?table=<table>"
            )
        if "if_exists" in parsed_uri.query:
            if_exists = parsed_uri.query["if_exists"]
            if if_exists == "error":
                if_exists = "fail"
        elif "append" in parsed_uri.query and parsed_uri.query["append"].lower() != "false":
            if_exists = "append"
        elif "overwrite" in parsed_uri.query and parsed_uri.query["overwrite"].lower() != "false":
            if_exists = "replace"
        else:
            if_exists = "fail"
        try:
            df.to_sql(table, engine, index=False, if_exists=if_exists)
        except ValueError as exc:
            if if_exists == "fail" and exc.args[0] == f"Table '{table}' already exists.":
                raise TableAlreadyExistsError(*exc.args) from exc
            raise
        except sqlalchemy.exc.OperationalError as exc:
            raise InvalidURLError(*exc.args) from exc
        except (sqlalchemy.exc.ProgrammingError, sqlalchemy.exc.IntegrityError) as exc:
            if if_exists == "append":
                raise AppendSchemeConflictError(*exc.args) from exc
            raise

    @classmethod
    def load_multitable(cls, uri):
        """Experimental feature. Undocumented. Low Quality."""
        from sqlalchemy import MetaData  # sqlalchemy imports are inlined for startup performance

        parsed_uri = parse_uri(uri)
        engine, table = RDBMSAdapter._get_engine_and_table_from_uri(parse_uri(uri))
        assert table is None
        with engine.connect() as conn:
            metadata = MetaData()
            metadata.reflect(bind=conn)
            for table_name in metadata.tables:
                table_uri_parsed = copy.copy(parsed_uri)
                table_uri_parsed.query["table"] = table_name
                logger.info(f"Loading table {encode_uri(table_uri_parsed)}")
                df = cls.load(encode_uri(table_uri_parsed), query=None)
                yield table_name, df

    @classmethod
    def dump_multitable(cls, df_multitable, uri):
        """Experimental feature. Undocumented. Low Quality."""
        parsed_uri = parse_uri(uri)
        for table_name, df in df_multitable:
            table_uri_parsed = copy.copy(parsed_uri)
            table_uri_parsed.query["table"] = table_name
            logger.info(f"Dumping table {encode_uri(table_uri_parsed)}")
            cls.dump(df, encode_uri(table_uri_parsed))
