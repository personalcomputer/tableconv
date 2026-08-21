import json
import os
import sys
from typing import Any

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin
from tableconv.exceptions import InvalidParamsError, SourceParseError, TableAlreadyExistsError


def raw_array_to_df(raw_array, source_label, params, format_label="JSON"):
    """Convert a list of object records (the shared JSON data model used by the json/jsonl/msgpack/har/yaml adapters)
    into a DataFrame, applying element validation and optional flattening via pandas.json_normalize.

    `source_label` is the scheme name used in error messages (e.g. "json", "yaml", "har").
    `format_label` is the type vocabulary used in error messages (e.g. "JSON", "YAML").
    """
    for i, item in enumerate(raw_array):
        if not isinstance(item, dict):
            if isinstance(item, (int, float)):
                json_type = "number"
            elif isinstance(item, str):
                json_type = "string"
            elif isinstance(item, list):
                json_type = "array"
            else:
                json_type = str(type(item))
            raise SourceParseError(
                f"Every element of the input {source_label} must be a {format_label} object. "
                f"(element {i + 1} in input was a {format_label} {json_type})"
            )
    preserve_nesting = params.get("preserve_nesting", "false").lower() == "true"
    nesting_sep = params.get("nesting_sep", ".")
    if preserve_nesting:
        return pd.DataFrame.from_records(raw_array)
    return pd.json_normalize(raw_array, sep=nesting_sep)


def resolve_if_exists(params):
    if "if_exists" in params:
        if_exists = params["if_exists"]
        if if_exists == "error":
            if_exists = "fail"
        assert if_exists in {"fail", "append", "replace"}
    elif "append" in params and params["append"].lower() != "false":
        if_exists = "append"
    elif "overwrite" in params and params["overwrite"].lower() != "false":
        if_exists = "replace"
    else:
        if_exists = "fail"
    return if_exists


def resolve_indent(params):
    if "indent" in params:
        return int(params["indent"])
    return None


def resolve_orient(params):
    return params.get("format_mode", params.get("orient", params.get("mode", "records")))


@register_adapter(["json", "jsonl", "jsonlines", "ldjson", "ndjson"])
class JSONAdapter(FileAdapterMixin, Adapter):

    @staticmethod
    def load_file(scheme, path, params):
        if scheme in ("jsonlines", "ldjson", "ndjson"):
            scheme = "jsonl"
        # NOTE: The below is a custom json parser wrapper, alternative to pd.read_json(), in order to let us flatten
        # (b.c. preserve_nesting=False) via json_normalize. It's not obvious why pandas doesn't offer a combined
        # read_json + json_normalize path; possibly a missing flag. The shared raw_array_to_df() helper centralizes
        # the array->DataFrame conversion for all json-data-model adapters (json/jsonl/msgpack/har/...).
        if hasattr(path, "read"):
            raw_json = path.read()
        else:
            raw_json = open(path).read()
        if scheme == "json":
            raw_array = json.loads(raw_json)
            if not isinstance(raw_array, list):
                raise SourceParseError("Input must be a JSON array")
        elif scheme == "jsonl":
            raw_array = []
            for line_number, line in enumerate(raw_json.splitlines()):
                try:
                    raw_array.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    # Edit the exception to have a better error message that references the real line number.
                    exc.args = (exc.args[0].replace(": line 1 column", f": line {line_number + 1} column"),)
                    exc.lineno = line_number + 1
                    raise exc
        else:
            raise AssertionError
        return raw_array_to_df(raw_array, scheme, params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        if scheme in ("jsonlines", "ldjson", "ndjson"):
            scheme = "jsonl"

        if_exists = resolve_if_exists(params)
        indent = resolve_indent(params)
        unnest = params.get("unnest", "false").lower() == "true"
        orient = resolve_orient(params)
        # `orient` Options are
        #    'split': dict like {'index' -> [index], 'columns' -> [columns], 'data' -> [values]}
        #    'records': list like [{column -> value}, ... , {column -> value}]
        #    'index': dict like {index -> {column -> value}}
        #    'columns': dict like {column -> {index -> value}}
        #    'values': just the values array
        #    'table': dict like {'schema': {schema}, 'data': {data}}
        if scheme == "jsonl" and orient != "records":
            raise InvalidParamsError("?orient must be records for jsonl")
        if unnest:
            if orient != "records":
                raise NotImplementedError("?unnest is only supported with orient=records")
            if scheme != "json":
                raise NotImplementedError("?unnest is not supported with jsonl")

        exists = os.path.exists(path) and path != "/dev/fd/1"
        if exists and if_exists == "fail":
            raise TableAlreadyExistsError(f"{path} already exists")
        assert not exists or if_exists in {"append", "replace"}
        if unnest:
            records = unnest_df(df, nesting_sep=params.get("nesting_sep", "."))
            with open(path, "r+") as buf:
                if exists and if_exists == "append":
                    buf.seek(0)
                    records = json.load(buf) + records
                buf.truncate(0)
                json.dump(records, buf, default=json_encoder_default, indent=indent)
        else:
            if orient in ["split", "index", "columns"]:
                # Index required. Use first column as index.
                df.set_index(df.columns[0], inplace=True)

            if exists and if_exists == "append":
                if scheme == "json":
                    records = df.to_dict(orient=orient)
                    with open(path, "r+") as buf:
                        if exists and if_exists == "append":
                            buf.seek(0)
                            records = json.load(buf) + records
                        buf.truncate(0)
                        buf.seek(0)
                        json.dump(records, buf, default=json_encoder_default, indent=indent)
                else:
                    with open(path, "a") as buf:
                        df.to_json(buf, lines=(scheme == "jsonl"), date_format="iso", indent=indent, orient=orient)
            else:
                df.to_json(path, lines=(scheme == "jsonl"), date_format="iso", indent=indent, orient=orient)

        if scheme == "json" and path == "/dev/fd/1" and sys.stdout.isatty():
            print()


def json_encoder_default(obj):
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj


def unnest_df(df, nesting_sep) -> list[dict]:
    """
    WARNING: extremely inefficient and weak/untested
    """
    # detect if unnesting has a naming conflict
    columns = set(df.columns)
    for column in columns:
        if nesting_sep in column:
            subkeys = column.split(nesting_sep)
            subkeys_materialized = {".".join(subkeys[: x + 1]) for x in range(len(subkeys[:-1]))}
            if subkeys_materialized.intersection(columns):
                conflict_col = list(subkeys_materialized.intersection(columns))[0]
                raise ValueError(f'Unnesting key conflict: column "{column}" conflicts with column "{conflict_col}"')
                # TODO: rename the conflict in this case, somewhere.
                # e.g. rename the conflict column to "{name}_unexpanded" or something?
    # unnest
    new_records = []
    records = df.to_dict(orient="records")
    for record in records:
        new_record: dict[str, Any] = dict()
        for key, value in record.items():
            sub_keys = key.split(nesting_sep)
            leaf_key = sub_keys[-1]
            branch = new_record
            for subkey in sub_keys[:-1]:
                if subkey not in branch:
                    branch[subkey] = dict()
                branch = branch[subkey]
            branch[leaf_key] = value
        new_records.append(new_record)
    return new_records


@register_adapter(["msgpack"])
class MsgpackAdapter(FileAdapterMixin, Adapter):
    """Msgpack shares the JSON data model; load delegates to raw_array_to_df() for validation/normalization.

    TODO: See also: BSON.
    """

    @staticmethod
    def load_file(scheme, path, params):
        import msgpack

        if hasattr(path, "read"):
            raw_bytes = path.read()
        else:
            raw_bytes = open(path, "rb").read()
        raw_array = msgpack.unpackb(raw_bytes)
        if not isinstance(raw_array, list):
            raise SourceParseError("Input must be a JSON array")
        return raw_array_to_df(raw_array, scheme, params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        import msgpack

        assert params.get("if_exists") in {None, "replace"}

        records = df.to_dict(orient=params.get("orient", "records"))

        with open(path, "wb") as buf:
            buf.write(msgpack.packb(records))


@register_adapter(["bson"])
class BsonAdapter(FileAdapterMixin, Adapter):
    """BSON shares the JSON data model; load delegates to raw_array_to_df() for validation/normalization.

    A BSON file is a sequence of concatenated BSON documents (the convention used by mongodump). On load, all documents
    are decoded into a list and normalized; on dump, each record is encoded as one BSON document and concatenated.
    """

    @staticmethod
    def load_file(scheme, path, params):
        import bson

        if hasattr(path, "read"):
            raw_bytes = path.read()
        else:
            raw_bytes = open(path, "rb").read()
        raw_array = bson.decode_all(raw_bytes)
        return raw_array_to_df(raw_array, scheme, params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        import bson

        assert params.get("if_exists") in {None, "replace"}

        records = df.to_dict(orient=params.get("orient", "records"))
        with open(path, "wb") as buf:
            if isinstance(records, list):
                for record in records:
                    buf.write(bson.encode(record))
            else:
                # Non-records orient yields a single dict; encode it as one document.
                buf.write(bson.encode(records))
