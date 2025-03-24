import json
import os
import sys
from typing import Any

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin
from tableconv.exceptions import InvalidParamsError, SourceParseError, TableAlreadyExistsError


@register_adapter(["json", "jsonl", "jsonlines", "ldjson", "ndjson"])
class JSONAdapter(FileAdapterMixin, Adapter):
    text_based = True

    # @staticmethod
    # def _flatten_map(map):
    #     flat_map = {}
    #     for key, value in map.items():
    #         if isinstance(value, dict):
    #             sub_map = JSONAdapter._flatten_map(value)
    #             flat_map.update({f'{key}.{sub_key}': sub_value for sub_key, sub_value in sub_map.items()})
    #         else:
    #             flat_map[key] = value
    #     return flat_map
    #
    # @staticmethod
    # def _get_keys(flat_array):
    #     value_keys = set()
    #     null_keys = set()
    #     for item in flat_array:
    #         for key, value in item.items():
    #             if value is None:
    #                 if key not in value_keys:
    #                     null_keys.add(key)
    #             else:
    #                 if key in null_keys:
    #                     null_keys.remove(key)
    #                 value_keys.add(key)
    #
    #     # Remove any null keys which are actually object keys where the object is not always null
    #     invalid_null_keys = set()
    #     for null_key in null_keys:
    #         if any((key.startswith(null_key + '.') for key in value_keys | null_keys)):
    #             invalid_null_keys.add(null_key)
    #     all_keys = value_keys | (null_keys - invalid_null_keys)
    #
    #     return sorted(all_keys)
    #
    # @staticmethod
    # def _normalize_json(raw_array):
    #     flat_array = [JSONAdapter._flatten_map(raw_item) for raw_item in raw_array]
    #     keys = JSONAdapter._get_keys(flat_array)
    #     records = ({k: v for k, v in item.items() if k in keys} for item in flat_array)
    #     return pd.DataFrame.from_records(records)

    @staticmethod
    def load_file(scheme, path, params):
        if scheme in ("jsonlines", "ldjson", "ndjson"):
            scheme = "jsonl"

        preserve_nesting = params.get("preserve_nesting", "false").lower() == "true"
        nesting_sep = params.get("nesting_sep", ".")
        if preserve_nesting:
            pd.read_json(
                path,
                lines=(scheme == "jsonl"),
                orient="records",
            )
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
                    f"Every element of the input {scheme} must be a JSON object. "
                    f"(element {i + 1} in input was a JSON {json_type})"
                )
        return pd.json_normalize(raw_array, sep=nesting_sep)

    @staticmethod
    def dump_file(df, scheme, path, params):
        if scheme in ("jsonlines", "ldjson", "ndjson"):
            scheme = "jsonl"

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

        if "indent" in params:
            indent = int(params["indent"])
        else:
            indent = None
        unnest = params.get("unnest", "false").lower() == "true"
        orient = params.get("format_mode", params.get("orient", params.get("mode", "records")))
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
