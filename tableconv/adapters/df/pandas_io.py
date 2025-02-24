"""File for all Adapters that are just minimal wrappers of pandas supported io formats"""

import collections
import csv
import io
import logging
import os
import re

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin

logger = logging.getLogger(__name__)


@register_adapter(["csv", "tsv"])
class CSVAdapter(FileAdapterMixin, Adapter):
    text_based = True

    @staticmethod
    def load_file(scheme, path, params):
        params["skipinitialspace"] = params.get("skipinitialspace", True)
        params["sep"] = params.get("sep", "\t" if scheme == "tsv" else ",")
        return pd.read_csv(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        params["index"] = params.get("index", False)
        params["sep"] = params.get("sep", "\t" if scheme == "tsv" else ",")
        path_or_buf = path
        if "if_exists" in params:
            if_exists = params.pop("if_exists")
            if os.path.exists(path):
                if if_exists == "replace":
                    path_or_buf = open(path, "w")
                elif if_exists == "append":
                    with open(path) as f:
                        existing_columns = next(csv.reader(f, delimiter=params["sep"]))
                    if list(existing_columns) != list(df.columns):
                        raise ValueError(
                            f"Cannot append to {path}, existing schema does not match. "
                            + f"(existing: {list(existing_columns)}. new: {list(df.columns)}))"
                        )
                    params["header"] = False
                    path_or_buf = open(path, "a")
                else:
                    assert if_exists == "fail"
                    # (continue, df.to_csv will fail)
        df.to_csv(path_or_buf, **params)


def normalize_pandas_multiindex(df, nesting_sep: str, truncate_redundant_hierarchy: bool) -> None:
    # This function is similar to pandas.json_normalize in that it takes a hierarchical column organization structure
    # and normalizes it such that each header is just one string. Example: the header ('colors', 'red') becomes
    # 'colors.red'
    if not isinstance(df.columns, pd.core.indexes.multi.MultiIndex):
        return

    if truncate_redundant_hierarchy and any(len(column) > 2 for column in df.columns):
        logger.warning(
            "Table hierarchy depth is over 2. Support for accurately truncating redundant header hierarchies"
            "deeper than 2 is not fully implemented"
        )
    if truncate_redundant_hierarchy:
        duplicate_top_headings = [
            heading
            for heading, count in collections.Counter([column[0] for column in df.columns]).items()
            if count >= 2
        ]
    new_columns = []
    for column in df.columns:
        assert isinstance(column, tuple)
        if (
            truncate_redundant_hierarchy
            and column[0] not in duplicate_top_headings
            and all(sub_heading == column[0] for sub_heading in column)
        ):
            # All sub-headings are the same
            new_columns.append(column[0])
        else:
            new_columns.append(nesting_sep.join(column))
    df.columns = new_columns


@register_adapter(["html"])
class HTMLAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        # If your html document has multiple tables in it, specify which one you want via table_index. The first table
        # is table_index=0, second is table_index=1, etc.
        table_index = int(params.pop("table_index", 0))
        nesting_sep = params.pop("nesting_sep", ".")
        truncate_redundant_hierarchy = params.pop("truncate_redundant_hierarchy", "true").lower() == "true"

        # I cannot figure out how to get pandas/tableconv to properly parse <br/> tags as being newlines without
        # monkeypatching/extending pandas. For now, here is a ridiculous and dangerous hack available to you (opt-in) if
        # importing <br/> as newlines is critical for your use case.
        newlines_workaround = params.pop("experimental_parse_br", "false").lower() == "true"
        consider_p_as_break = params.pop("experimental_consider_p_as_break", "false").lower() == "true"
        if newlines_workaround:
            # Replace the breaks with a unique passthrough sentinel value, in the raw HTML.
            NEWLINE_PLACHOLDER = "027eade341cf__NEWLINE_REPLACE_ME__"
            with open(path) as fd:
                data = fd.read()
            data = re.sub(r"\n", "", data)  # counteract pandas doing its newline to space conversion.
            data = re.sub(r"<br\s*?/?>", NEWLINE_PLACHOLDER, data)
            if consider_p_as_break:
                data = re.sub(r"<p\s*?>", NEWLINE_PLACHOLDER, data)
            buffer = io.StringIO()
            buffer.write(data)
            buffer.seek(0)
            df = pd.read_html(buffer, **params)[table_index]
            # Put back in newlines in the place of the passed through sentinel values, within the parsed data frame.
            for dtype, column in zip(df.dtypes, df.columns, strict=False):
                if dtype in ("object", str):
                    df[column] = df[column].str.replace(NEWLINE_PLACHOLDER, "\n", regex=False)
        else:
            df = pd.read_html(path, **params)[table_index]
        normalize_pandas_multiindex(df, nesting_sep, truncate_redundant_hierarchy)
        return df

    @staticmethod
    def dump_file(df, scheme, path, params):
        df.to_html(path, **params)


@register_adapter(["xls", "xlsx", "xlsm", "xlsb", "odf", "ods", "odt"])
class ExcelAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        params["sheet_name"] = params.get("sheet_name", 0)  # TODO: table naming support - extract it from URI
        return pd.read_excel(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        params["sheet_name"] = params.get("sheet_name", "Sheet1")  # TODO: table naming support - extract it from URI
        params["index"] = params.get("index", False)
        df.to_excel(path, **params)


@register_adapter(["parquet"])
class ParquetAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_parquet(path, **params)

    @staticmethod
    def _normalize_column_types(df):
        """
        Pandas to_parquet cannot handle derived classes of str, requires literal strings for column names or it can
        output corrupt parquet files or simply crash.
        """
        # example crash log, for reference:
        # TypeError: Expected unicode, got quoted_name
        # Exception ignored in: 'fastparquet.cencoding.write_list'
        # Traceback (most recent call last):
        #   File "fastparquet/writer.py", line 888, in write_simple
        #     foot_size = f.write(fmd.to_bytes())
        df.columns = [str(c) for c in df.columns]

    @staticmethod
    def dump_file(df, scheme, path, params):
        params["index"] = params.get("index", False)
        ParquetAdapter._normalize_column_types(df)
        df.to_parquet(path, **params)


@register_adapter(["h5", "hdf5"])
class HDF5Adapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_hdf(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        params["format"] = params.get("format", "table")
        df.to_hdf(path, **params)


@register_adapter(["fwf", "fixedwidth"])
class FWFAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_fwf(path, **params)

    def dump_text_data(df, scheme, params):
        from tabulate import tabulate

        return tabulate(
            df.values.tolist(),
            list(df.columns),
            tablefmt="plain",
            disable_numparse=True,
        )


@register_adapter(["feather"])
class FeatherAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_feather(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        params["index"] = params.get("index", False)
        df.to_feather(path, **params)


@register_adapter(["orc"], read_only=True)
class ORCAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_orc(path, **params)


@register_adapter(["dta"])
class StataAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_stata(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        params["write_index"] = params.get("write_index", False)
        df.to_stata(path, **params)


@register_adapter(["pickledf"])
class PicklePandasAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_pickle(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        return df.to_pickle(path, **params)
