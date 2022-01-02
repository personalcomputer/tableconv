import pandas as pd
import yaml

from tableconv.exceptions import SourceParseError
from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin


@register_adapter(['yaml', 'yml'])
class YAMLAdapter(FileAdapterMixin, Adapter):
    text_based = True

    @staticmethod
    def load_file(scheme, path, params):
        if params.get('preserve_nesting', False):
            raise NotImplementedError()

        if not hasattr(path, 'read'):
            path = open(path)
        raw_array = yaml.safe_load(path)
        if not isinstance(raw_array, list):
            raise SourceParseError('Input must be a YAML sequence (list/array)')
        for i, item in enumerate(raw_array):
            if not isinstance(item, dict):
                if isinstance(item, int) or isinstance(item, float):
                    yaml_type = 'number'
                elif isinstance(item, str):
                    yaml_type = 'string'
                elif isinstance(item, list):
                    yaml_type = 'sequence'
                else:
                    yaml_type = str(type(item))
                raise SourceParseError(
                    f'Every element of the input {scheme} must be a YAML mapping (dictionary). '
                    f'(element {i + 1} in input was a YAML {yaml_type})')
        return pd.json_normalize(raw_array)

    @staticmethod
    def dump_file(df, scheme, path, params):
        yaml_text = yaml.dump(
            df.to_dict(orient='records'),
            sort_keys=False, indent=4
        )
        with open(path, 'w') as f:
            f.write(yaml_text)
