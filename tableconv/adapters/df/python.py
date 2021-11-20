import ast
import subprocess

import pandas as pd

from .base import Adapter, register_adapter
from .file_adapter_mixin import FileAdapterMixin


@register_adapter(['py', 'python'])
class PythonAdapter(FileAdapterMixin, Adapter):
    text_based = True

    @staticmethod
    def load_text_data(scheme, data, kwargs):
        if kwargs.get('preserve_nesting', False):
            raise NotImplementedError()

        raw_array = ast.literal_eval(data)
        if not isinstance(raw_array, list):
            raise ValueError('Input must be a Python list)')
        for i, item in enumerate(raw_array):
            if not isinstance(item, dict):
                raise ValueError(
                    f'Every element of the input {scheme} must be a Python dict. '
                    f'(element {i + 1} in input was a Python {type(item)})')
        return pd.json_normalize(raw_array)

    @staticmethod
    def dump_text_data(df, scheme, kwargs):
        raw = str(df.to_dict(orient='records'))
        # TODO: This is not an acceptable way to invoke Black. Black also should be an optional dependency.
        process = subprocess.Popen(['black', '-'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        process.communicate(raw.encode('utf-8'))
        process.wait()
        output, stderr = process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode())
        return output.decode()
