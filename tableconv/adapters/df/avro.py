from io import IOBase
from typing import IO, Any, cast

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin


def _pandas_dtype_to_avro_type(dtype) -> dict[str, str] | str:
    if pd.api.types.is_integer_dtype(dtype):
        return "long"
    elif pd.api.types.is_float_dtype(dtype):
        return "double"
    elif pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    elif pd.api.types.is_datetime64_any_dtype(dtype):
        return {"type": "long", "logicalType": "timestamp-micros"}
    elif pd.api.types.is_object_dtype(dtype):  # Defaulting object to string
        return "string"
    return "string"


def _infer_avro_schema_from_df(
    df: pd.DataFrame, schema_name: str = "DynamicSchema", namespace: str = "pandas.avro"
) -> dict:
    fields: list[dict] = []
    for column_name, dtype in df.dtypes.items():
        avro_type = _pandas_dtype_to_avro_type(dtype)
        # Make all fields nullable by default, union with null
        # Check if column has NaN values to decide if it should be nullable.
        # A more robust way might be to always make them nullable or provide an option.
        is_nullable = df[column_name].isnull().any()
        if is_nullable:
            field_type: Any = ["null", avro_type]
            # Ensure "null" is the first type in the union if a default is to be provided
            # and that default is null, or if a type is "null" itself.
            # For simplicity here, just making it nullable.
        else:
            field_type = avro_type

        fields.append({"name": str(column_name), "type": field_type})

    return {
        "type": "record",
        "name": schema_name,
        "namespace": namespace,
        "fields": fields,
    }


@register_adapter(["avro"])
class AvroAdapter(FileAdapterMixin, Adapter):

    @classmethod
    def load_file(cls, scheme: str, path: str | IOBase, params: dict[str, Any]) -> pd.DataFrame:
        import fastavro

        def buf_to_df(buf: IO) -> pd.DataFrame:  # TODO: Why doesn't FileAdapterMixin cover this normalization?
            records = []
            for record in fastavro.reader(buf):
                records.append(record)
            return pd.DataFrame(records)

        if isinstance(path, IOBase):
            buf = cast(IO, path)
            return buf_to_df(buf)
        else:
            with open(path, "rb") as buf:
                return buf_to_df(buf)

    @classmethod
    def dump_file(cls, df: pd.DataFrame, scheme: str, path: str, params: dict[str, Any]) -> None:
        import fastavro

        # Infer schema from DataFrame
        schema = fastavro.parse_schema(_infer_avro_schema_from_df(df, schema_name="default"))

        records = df.to_dict(orient="records")
        with open(path, "wb") as f:
            fastavro.writer(f, schema, records)
