import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin


@register_adapter(["leveldblog"], read_only=True)
class LevelDBLogAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}:output-0"

    @staticmethod
    def load_file(scheme, path, params):
        from leveldb_export import parse_leveldb_documents  # inlined for startup performance

        docs = list(parse_leveldb_documents(path))
        # breakpoint()
        return pd.DataFrame.from_records(docs)
