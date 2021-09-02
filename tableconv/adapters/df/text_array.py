import ast
import json

import pandas as pd
import yaml

from .base import Adapter, register_adapter
from .file_adapter_mixin import FileAdapterMixin


@register_adapter(['list', 'csa', 'jsonarray', 'pylist', 'yamlsequence'])
class TextArrayAdapter(FileAdapterMixin, Adapter):
    text_based = True

    @staticmethod
    def get_example_url(scheme):
        return f'{scheme}:-'

    @staticmethod
    def load_text_data(scheme, data, kwargs):
        data = data.strip()
        if scheme == 'jsonarray':
            array = [(item,) for item in json.loads(data)]
        elif scheme == 'pylist':
            array = [(item,) for item in ast.literal_eval(data)]
        elif scheme == 'yamlsequence':
            array = [(item,) for item in yaml.loads(data)]
        elif scheme in ('csa', 'list'):
            seperator = {
                'csa': ',',
                'list': '\n'
            }[scheme]
            if seperator[-1] == '\n' and data[-1] == '\n':
                data = data[:-1]
            array = [(item,) for item in data.split(seperator)]
        else:
            raise AssertionError
        return pd.DataFrame.from_records(array, columns=['value'])

    @staticmethod
    def dump_text_data(df, scheme, kwargs):
        if len(df.columns) > 1:
            raise ValueError(f'Table has multiple columns; unable to condense into an array for {scheme}')
        array = list(df[df.columns[0]].values)
        serialized_array = [str(item) for item in array]
        if scheme == 'jsonarray':
            return json.dumps(array)
        elif scheme == 'pylist':
            return repr(array)
        elif scheme == 'yamlsequence':
            return yaml.safe_dump(serialized_array)
        elif scheme in ('csa', 'list'):
            seperator = {
                'csa': ',',
                'list': '\n'
            }[scheme]
            seperator_word = {
                ',': 'comma',
                '\n': 'new-line',
            }[seperator]
            if any((seperator in item for item in serialized_array)):
                raise ValueError(f'Cannot write as {scheme}, one or more values contain a {seperator_word}')
            return seperator.join(serialized_array)
        else:
            raise AssertionError
