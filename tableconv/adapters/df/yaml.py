import yaml

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin
from tableconv.adapters.df.json import raw_array_to_df
from tableconv.exceptions import SourceParseError


@register_adapter(["yaml", "yml"])
class YAMLAdapter(FileAdapterMixin, Adapter):
    """YAML shares the JSON data model; load delegates to raw_array_to_df() for validation/normalization."""

    @staticmethod
    def load_file(scheme, path, params):
        if not hasattr(path, "read"):
            path = open(path)
        raw_array = yaml.safe_load(path)
        if not isinstance(raw_array, list):
            raise SourceParseError('Input must be a YAML sequence ("list"/"array")')
        return raw_array_to_df(raw_array, scheme, params, format_label="YAML")

    @staticmethod
    def dump_file(df, scheme, path, params):
        yaml_text = yaml.dump(df.to_dict(orient="records"), sort_keys=False, indent=4)
        with open(path, "w") as f:
            f.write(yaml_text)
