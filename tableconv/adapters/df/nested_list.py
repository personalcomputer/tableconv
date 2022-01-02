import marko
import pandas as pd

from tableconv.exceptions import SourceParseError
from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin


@register_adapter(['nestedlist'], read_only=True)
class NestedListAdapter(FileAdapterMixin, Adapter):
    text_based = True

    @staticmethod
    def get_example_url(scheme):
        return f'{scheme}:-'

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
        document = marko.parse(data.strip())
        if len(document.children) != 1 or not isinstance(document.children[0], marko.block.List):
            raise SourceParseError('Unable to parse nested list')

        # nesting_sep = params.get('nesting_sep', 'columns')
        # if nesting_sep == 'columns':
        # elif nesting_sep == 'dots':
        #     nesting_sep = '.'
        # elif nesting_sep in ('chevrons', 'arrows'):
        #     nesting_sep = ' > '

        records = NestedListAdapter._traverse(document.children[0].children, [])
        max_depth = max([len(record) for record in records])
        return pd.DataFrame.from_records(records, columns=[f'level{i}' for i in range(max_depth)])
