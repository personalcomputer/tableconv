import json

import marko
import numpy as np
import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin
from tableconv.exceptions import SourceParseError


@register_adapter(["nestedlist"])
class NestedListAdapter(FileAdapterMixin, Adapter):
    """This is a super strange adapter. Much more experimental. It converts structured nested lists into tables."""

    text_based = True

    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}:-"

    @staticmethod
    def _traverse(list_elem, heritage):
        records = []
        for list_member in list_elem:
            name = list_member.children[0].children[0].children
            if isinstance(name, list):
                name = name[0].children
            if len(list_member.children) > 1:
                records.extend(NestedListAdapter._traverse(list_member.children[1].children, heritage + [name]))
            else:
                records.append(heritage + [name])
        return records

    @staticmethod
    def load_text_data(scheme, data, params):
        document = marko.parse(data.strip())  # Parse the list hierarchy in using markdown.
        if len(document.children) != 1 or not isinstance(document.children[0], marko.block.List):
            raise SourceParseError("Unable to parse nested list")

        # nesting_sep = params.get('nesting_sep', 'columns')
        # if nesting_sep == 'columns':
        # elif nesting_sep == 'dots':
        #     nesting_sep = '.'
        # elif nesting_sep in ('chevrons', 'arrows'):
        #     nesting_sep = ' > '

        records = NestedListAdapter._traverse(document.children[0].children, [])
        max_depth = max([len(record) for record in records])
        return pd.DataFrame.from_records(records, columns=[f"level{i}" for i in range(max_depth)])

    @staticmethod
    def dump_text_data(df, scheme, params):
        df.replace({np.nan: None}, inplace=True)
        resultlines = []
        # result_nested_dict = {}
        rows = [row for _, row in df.iterrows()]
        xpath = []
        num_columns = len(df.columns)
        for row in rows:
            for i in range(num_columns):
                if len(xpath) < i + 1 or row.iloc[i] != xpath[i]:
                    xpath = xpath[:i]
                    xpath.append(row.iloc[i])
                    if row.iloc[i]:
                        resultlines.append(f"{i * '    '}* {xpath[i]}")
        return "\n".join(resultlines)


@register_adapter(["jsondict"], read_only=True)
class JsonDictAdapter(FileAdapterMixin, Adapter):
    """This is a super strange adapter. Much more experimental. It converts structured nested lists into tables."""

    text_based = True

    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}:-"

    @staticmethod
    def _traverse(list_elem, heritage):
        records = []
        for child_name, child_value in list_elem.items():
            if isinstance(child_value, dict):
                records.extend(JsonDictAdapter._traverse(child_value, heritage + [child_name]))
            else:
                records.append(heritage + [child_name] + [child_value])
        return records

    @staticmethod
    def load_text_data(scheme, data, params):
        data = json.loads(data)
        records = JsonDictAdapter._traverse(data, [])
        max_depth = max([len(record) for record in records])
        return pd.DataFrame.from_records(records, columns=[f"level{i}" for i in range(max_depth)])
