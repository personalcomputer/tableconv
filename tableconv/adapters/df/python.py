import ast

import numpy as np
import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin
from tableconv.exceptions import SourceParseError


@register_adapter(["py", "python"])
class PythonAdapter(FileAdapterMixin, Adapter):
    text_based = True

    @staticmethod
    def load_text_data(scheme, data, params):
        if params.get("preserve_nesting", False):
            raise NotImplementedError()

        raw_array = ast.literal_eval(data)
        if not isinstance(raw_array, list):
            raise SourceParseError("Input must be a Python list)")
        for i, item in enumerate(raw_array):
            if not isinstance(item, dict):
                raise SourceParseError(
                    f"Every element of the input {scheme} must be a Python dict. "
                    f"(element {i + 1} in input was a Python {type(item)})"
                )
        return pd.json_normalize(raw_array)

    @staticmethod
    def dump_text_data(df, scheme, params):
        import black

        if params.get("orient") == "index":
            df.set_index(df.columns[0], inplace=True)
        df.replace({np.nan: None}, inplace=True)
        output_py = repr(df.to_dict(orient=params.get("orient", "records")))

        black_opts = {}
        if "line_length" in params:
            black_opts["line_length"] = int(params["line_length"])
        if "target_versions" in params:
            black_opts["target_versions"] = bool(params["target_versions"])
        if "string_normalization" in params:
            black_opts["string_normalization"] = bool(params["string_normalization"])
        if "magic_trailing_comma" in params:
            black_opts["magic_trailing_comma"] = bool(params["magic_trailing_comma"])
        return black.format_str(output_py, mode=black.Mode(**black_opts))
