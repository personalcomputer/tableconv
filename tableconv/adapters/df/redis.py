import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.exceptions import InvalidParamsError, TableAlreadyExistsError
from tableconv.uri import parse_uri


@register_adapter(["redis"])
class RedisAdapter(Adapter):
    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}://127.0.0.1:6379?db=0"

    @staticmethod
    def _validate_uri_path(parsed_uri):
        if parsed_uri.path not in {"", "/"}:
            raise InvalidParamsError(
                "Redis adapter reads/writes an entire redis database. URI path must be empty, "
                "example: redis://127.0.0.1:6379?db=0"
            )

    @staticmethod
    def _get_client(parsed_uri):
        import redis

        authority = parsed_uri.authority or "127.0.0.1:6379"
        if ":" in authority:
            host, port_raw = authority.rsplit(":", 1)
            port = int(port_raw)
        else:
            host = authority
            port = 6379
        options = {"host": host, "port": port, "decode_responses": True}
        if "db" in parsed_uri.query:
            options["db"] = int(parsed_uri.query["db"])
        # if "username" in parsed_uri.query:
        #     options["username"] = parsed_uri.query["username"]
        # if "password" in parsed_uri.query:
        #     options["password"] = parsed_uri.query["password"]
        # if "ssl" in parsed_uri.query:
        #     options["ssl"] = strtobool(parsed_uri.query["ssl"])
        return redis.Redis(**options)

    @staticmethod
    def _resolve_if_exists(params):
        if "if_exists" in params:
            if_exists = params["if_exists"]
            if if_exists == "error":
                if_exists = "fail"
        elif "append" in params and params["append"].lower() != "false":
            if_exists = "append"
        elif "overwrite" in params and params["overwrite"].lower() != "false":
            if_exists = "replace"
        else:
            if_exists = "fail"
        if if_exists not in {"fail", "replace", "append"}:
            raise InvalidParamsError("`if_exists` must be one of fail, replace, append.")
        return if_exists

    @staticmethod
    def _has_any_keys(client):
        for _ in client.scan_iter(match="*"):
            return True
        return False

    @classmethod
    def load(cls, uri: str, query: str | None) -> pd.DataFrame:
        parsed_uri = parse_uri(uri)
        cls._validate_uri_path(parsed_uri)
        client = cls._get_client(parsed_uri)
        keys = sorted(client.scan_iter(match="*"))
        rows = [{"key": key, "value": client.get(key)} for key in keys]
        df = pd.DataFrame.from_records(rows, columns=["key", "value"])
        return cls._query_in_memory(df, query)

    @classmethod
    def dump(cls, df: pd.DataFrame, uri: str) -> str:
        parsed_uri = parse_uri(uri)
        cls._validate_uri_path(parsed_uri)
        if_exists = cls._resolve_if_exists(parsed_uri.query)
        client = cls._get_client(parsed_uri)
        if "key" not in df.columns or "value" not in df.columns:
            raise InvalidParamsError("Redis dump requires dataframe columns `key` and `value`.")

        db_not_empty = cls._has_any_keys(client)
        if db_not_empty and if_exists == "fail":
            raise TableAlreadyExistsError("Redis database is not empty.")
        if if_exists == "replace":
            client.flushdb()

        for row in df[["key", "value"]].to_dict(orient="records"):
            client.set(str(row["key"]), str(row["value"]))
        return f"{parsed_uri.authority or '127.0.0.1:6379'}?db={parsed_uri.query.get('db', '0')}"
