import datetime
import math
from decimal import Decimal
from typing import Any

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin


@register_adapter(["dzn"], write_only=True)
class MiniZincDznAdapter(FileAdapterMixin, Adapter):
    text_based = True

    @staticmethod
    def get_example_url(scheme):
        return f"example.{scheme}"

    @staticmethod
    def _render_dzn_value(value: Any) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return "?"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if math.isfinite(value):
                return repr(value)
            if math.isnan(value):
                return "?"
            return "infinity" if value > 0 else "-infinity"
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
            return f'"{value.isoformat()}"'
        if isinstance(value, str):
            s = value.replace('"', '\\"')
            return f'"{s}"'
        return f'"{str(value).replace('"', '\\"')}"'

    @staticmethod
    def dump_text_data(df, scheme, params):
        lines = []
        for column_name in df.columns:
            values = df[column_name].tolist()
            rendered_values = [MiniZincDznAdapter._render_dzn_value(value) for value in values]
            array_str = ", ".join(rendered_values)
            lines.append(f"{column_name} = [{array_str}];")
        return "\n".join(lines)
