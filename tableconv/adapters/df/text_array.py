import ast
import io
import json

import pandas as pd
import yaml

from tableconv.exceptions import IncapableDestinationError
from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin


@register_adapter(['list', 'csa', 'jsonarray', 'pythonlist', 'pylist', 'yamlsequence'])
class TextArrayAdapter(FileAdapterMixin, Adapter):
    text_based = True

    @staticmethod
    def get_example_url(scheme):
        return f'{scheme}:-'

    @staticmethod
    def load_text_data(scheme, data, params):
        data = data.strip()
        if scheme == 'jsonarray':
            array = [(item,) for item in json.loads(data)]
        elif scheme in ('pythonlist', 'pylist'):
            array = [(item,) for item in ast.literal_eval(data)]
        elif scheme == 'yamlsequence':
            data_stream = io.StringIO(data)
            array = [(item,) for item in yaml.safe_load(data_stream)]
        elif scheme in ('csa', 'list'):
            separator = {
                'csa': ',',
                'list': '\n'
            }[scheme]
            if separator[-1] == '\n' and data[-1] == '\n':
                data = data[:-1]
            array = [(item,) for item in data.split(separator)]
        else:
            raise AssertionError
        return pd.DataFrame.from_records(array, columns=['value'])

    @staticmethod
    def dump_text_data(df, scheme, params):
        if len(df.columns) > 1:
            raise IncapableDestinationError(
                f'Table has multiple columns; unable to condense into an array for {scheme}')
        array = list(df[df.columns[0]].values)
        serialized_array = [str(item) for item in array]
        if scheme == 'jsonarray':
            return json.dumps(array)
        elif scheme in ('pythonlist', 'pylist'):
            return repr(array)
        elif scheme == 'yamlsequence':
            return yaml.safe_dump(serialized_array)
        elif scheme in ('csa', 'list'):
            separator = {
                'csa': ',',
                'list': '\n'
            }[scheme]
            separator_word = {
                ',': 'comma',
                '\n': 'new-line',
            }[separator]
            if any((separator in item for item in serialized_array)):
                raise IncapableDestinationError(
                    f'Cannot write as {scheme}, one or more values contain a {separator_word}')
            return separator.join(serialized_array)
        else:
            raise AssertionError
