""" File for all Adapters that are just minimal wrappers of pandas supported io formats """
import pandas as pd

from .base import register_adapter, Adapter
from .file_adapter_mixin import FileAdapterMixin


@register_adapter(['csv', 'tsv'])
class CSVAdapter(FileAdapterMixin, Adapter):
    text_based = True

    @staticmethod
    def load_file(scheme, path, params):
        params['skipinitialspace'] = params.get('skipinitialspace', True)
        params['sep'] = params.get('sep', '\t' if scheme == 'tsv' else ',')
        return pd.read_csv(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        params['index'] = params.get('index', False)
        params['sep'] = params.get('sep', '\t' if scheme == 'tsv' else ',')
        df.to_csv(path, **params)


@register_adapter(['xls', 'xlsx'])
class ExcelAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        params['sheet_name'] = params.get('sheet_name', 0)  # TODO: table naming support - extract it from URI
        return pd.read_excel(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        params['sheet_name'] = params.get('sheet_name', 'Sheet1')  # TODO: table naming support - extract it from URI
        params['index'] = params.get('index', False)
        df.to_excel(path, **params)


@register_adapter(['parquet'])
class ParquetAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_parquet(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        params['index'] = params.get('index', False)
        df.to_parquet(path, **params)


@register_adapter(['h5', 'hdf5'])
class HDF5Adapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_hdf(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        params['format'] = params.get('format', 'table')
        df.to_hdf(path, **params)


@register_adapter(['feather'])
class FeatherAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_feather(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        params['index'] = params.get('index', False)
        df.to_feather(path, **params)


@register_adapter(['orc'], read_only=True)
class ORCAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_orc(path, **params)


@register_adapter(['dta'])
class StataAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        return pd.read_stata(path, **params)

    @staticmethod
    def dump_file(df, scheme, path, params):
        params['write_index'] = params.get('write_index', False)
        df.to_stata(path, **params)
