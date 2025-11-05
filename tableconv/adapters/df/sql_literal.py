import datetime
import json
import math
from decimal import Decimal
from typing import Any

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin


@register_adapter(["sql_values", "sql_literal"], write_only=True)
class SQLLiteralAdapter(FileAdapterMixin, Adapter):
    """Currently only supports the PostgreSQL-flavored VALUES syntax"""

    text_based = True

    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}:-"

    @staticmethod
    def _render_sql_literal_value(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if math.isfinite(value):
                return repr(value)
            if math.isnan(value):
                return "'NaN'::float8"
            return "'Infinity'::float8" if value > 0 else "'-Infinity'::float8"
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, datetime.datetime):
            if value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None:
                iso = value.isoformat(sep=" ")
                return f"TIMESTAMPTZ '{iso.replace("'", "''")}'"
            iso = value.replace(tzinfo=None).isoformat(sep=" ")
            return f"TIMESTAMP '{iso.replace("'", "''")}'"
        if isinstance(value, datetime.date):
            return f"DATE '{value.isoformat()}'"
        if isinstance(value, datetime.time):
            return f"TIME '{value.isoformat()}'"
        if isinstance(value, bytes):
            hexstr = value.hex()
            return f"decode('{hexstr}', 'hex')"
        if isinstance(value, str):
            # According to LLM:
            # - PostgreSQL uses single-quote doubling.
            # - Null character is not allowed; replace with U+FFFD.
            s = value.replace("\x00", "\ufffd").replace("'", "''")
            return f"'{s}'"
        if isinstance(value, (list, dict)):
            s = json.dumps(value, separators=(",", ":"))
            s = s.replace("'", "''")
            return f"'{s}'"
        return f"'{str(value).replace("'", "''")}'"

    @staticmethod
    def dump_text_data(df, scheme, params):
        data = df.to_dict(orient="split")

        table_name = params.get("table_name", params.get("table", "data"))
        columns_str = ", ".join([f'"{name}"' for name in data["columns"]])
        rendered_tuples = [
            [SQLLiteralAdapter._render_sql_literal_value(value) for value in item] for item in data["data"]
        ]
        values_str = ", ".join([f"({', '.join(items)})" for items in rendered_tuples])

        return f"(VALUES {values_str}) {table_name}({columns_str})"
