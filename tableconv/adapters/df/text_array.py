import ast
import io
import json
import os
import re

import pandas as pd
import yaml

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin
from tableconv.exceptions import IncapableDestinationError
from tableconv.uri import parse_uri


@register_adapter(["list", "csa", "tsa", "jsonarray", "pythonlist", "pylist", "yamlsequence"])
class TextArrayAdapter(FileAdapterMixin, Adapter):
    text_based = True

    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}:-"

    @staticmethod
    def load_text_data(scheme, data, params):
        data = data.strip()
        if scheme == "jsonarray":
            array = [(item,) for item in json.loads(data)]
        elif scheme in ("pythonlist", "pylist"):
            array = [(item,) for item in ast.literal_eval(data)]
        elif scheme == "yamlsequence":
            data_stream = io.StringIO(data)
            array = [(item,) for item in yaml.safe_load(data_stream)]
        elif scheme in ("csa", "tsa", "list"):
            param_separator = params.get("separator", params.get("sep"))
            if param_separator:
                separator = param_separator
                if separator == "\\t":
                    separator = "\t"
            else:
                separator = {"csa": ",", "list": "\n", "tsa": "\t"}[scheme]
            if separator[-1] == "\n" and data[-1] == "\n":
                data = data[:-1]
            array = ((item,) for item in data.split(separator))
            if params.get("strip_whitespace", True):
                array = ((item[0].strip(),) for item in array)
        else:
            raise AssertionError
        return pd.DataFrame.from_records(list(array), columns=["value"])

    @staticmethod
    def dump_text_data(df, scheme, params):
        if len(df.columns) > 1:
            raise IncapableDestinationError(
                f"Table has multiple columns; unable to condense into an array for {scheme}"
            )
        array = list(df[df.columns[0]].values)
        serialized_array = [str(item) for item in array]
        if scheme == "jsonarray":
            return json.dumps(array)
        elif scheme in ("pythonlist", "pylist"):
            return repr(array)
        elif scheme == "yamlsequence":
            return yaml.safe_dump(serialized_array)
        elif scheme in ("csa", "list"):
            param_separator = params.get("separator", params.get("sep"))
            if param_separator:
                separator = param_separator
                separator_word = param_separator
            else:
                separator = {"csa": ",", "list": "\n"}[scheme]
                separator_word = {
                    ",": "comma",
                    "\n": "new-line",
                }[separator]
            if any(separator in item for item in serialized_array):
                raise IncapableDestinationError(
                    f"Cannot write as {scheme}, one or more values contain a {separator_word}"
                )
            return separator.join(serialized_array)
        else:
            raise AssertionError


@register_adapter(["file_per_row"])
class FilePerRowOutputAdapter(Adapter):
    """
    Very experimental adapter. Definitely not proper. I'm struggling to figure out a good product design / story for
    solving this specific usecase. What other tool/script can we pipe tableconv output/input through to handle this
    usecase? How can we inject a custom mini python script to handle this usecase? etc. What is
    the composable solution?
    """

    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}:///tmp/example (each file is considered a (filename,value) record)"

    @classmethod
    def load(cls, uri: str, query: str | None) -> pd.DataFrame:
        parsed_uri = parse_uri(uri)
        path = parsed_uri.path
        if not os.path.exists(path):
            raise ValueError(f"Unable to load {path}, path does not exist")
        filenames = os.listdir(path)
        if not filenames:
            raise ValueError(f"Unable to load {path}, no files in {path}")
        data = []
        for filename in os.listdir(path):
            with open(filename) as f:
                value = f.read()
            data.append({"filename": filename, "value": value})
        df = pd.DataFrame.from_records(data)
        return cls._query_in_memory(df, query)

    @classmethod
    def dump(cls, df, uri: str):
        parsed_uri = parse_uri(uri)
        if set(df.columns) != set(["filename", "value"]):
            raise IncapableDestinationError('Table must have only two columns: "filename" and "value"')
        path = parsed_uri.path
        if parsed_uri.authority:
            if path:
                path = os.path.join(parsed_uri.authority, path)
            else:
                path = parsed_uri.authority
        if os.path.exists(path):
            if not os.path.isdir(path):
                raise IncapableDestinationError(
                    f'Destination must be an empty folder. "{os.path.abspath(path)}" is a pre-existing file.'
                )
            if os.listdir(path):
                raise IncapableDestinationError(
                    f'Destination folder must be empty. "{os.path.abspath(path)}" is not empty.'
                )
        os.makedirs(path, exist_ok=True)
        data = df.to_dict(orient="records")
        for filename in (record["filename"] for record in data):
            filename = str(filename)
            if re.search(r'[<>:"|?*\\/]', filename):
                raise IncapableDestinationError(
                    "Filenames must not contain special characters, please slugify them using SQL. Example errant "
                    f'filename: "{filename}"'
                )
        for record in data:
            with open(os.path.join(path, str(record["filename"])), "w") as f:
                f.write(record["value"])
