""" File for all Adapters that are just minimal wrappers of pandas supported io formats """
import pandas as pd

from .base import register_adapter, Adapter
from .file_adapter_mixin import FileAdapterMixin


@register_adapter(['csv', 'tsv'])
class CSVAdapter(FileAdapterMixin, Adapter):
    text_based = True

    @staticmethod
    def load_file(scheme, path, query_args):
        query_args['skipinitialspace'] = query_args.get('skipinitialspace', True)
        query_args['sep'] = query_args.get('sep', '\t' if scheme == 'tsv' else ',')
        return pd.read_csv(path, **query_args)

    @staticmethod
    def dump_file(df, scheme, path, query_args):
        query_args['index'] = query_args.get('index', False)
        query_args['sep'] = query_args.get('sep', '\t' if scheme == 'tsv' else ',')
        df.to_csv(path, **query_args)


@register_adapter(['xls', 'xlsx'])
class ExcelAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, query_args):
        query_args['sheet_name'] = query_args.get('sheet_name', 0)  # TODO: table naming support - extract it from URI
        return pd.read_excel(path, **query_args)

    @staticmethod
    def dump_file(df, scheme, path, query_args):
        query_args['sheet_name'] = query_args.get('sheet_name', 'Sheet1')  # TODO: table naming support - extract it from URI
        query_args['index'] = query_args.get('index', False)
        df.to_excel(path, **query_args)


@register_adapter(['parquet'])
class ParquetAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, query_args):
        return pd.read_parquet(path, **query_args)

    @staticmethod
    def dump_file(df, scheme, path, query_args):
        query_args['index'] = query_args.get('index', False)
        df.to_parquet(path, **query_args)


@register_adapter(['h5', 'hdf5'])
class HDF5Adapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, query_args):
        return pd.read_hdf(path, **query_args)

    @staticmethod
    def dump_file(df, scheme, path, query_args):
        query_args['format'] = query_args.get('format', 'table')
        df.to_hdf(path, **query_args)


@register_adapter(['feather'])
class FeatherAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, query_args):
        return pd.read_feather(path, **query_args)

    @staticmethod
    def dump_file(df, scheme, path, query_args):
        query_args['index'] = query_args.get('index', False)
        df.to_feather(path, **query_args)


@register_adapter(['orc'], read_only=True)
class ORCAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, query_args):
        return pd.read_orc(path, **query_args)


@register_adapter(['dta'])
class StataAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, query_args):
        return pd.read_stata(path, **query_args)

    @staticmethod
    def dump_file(df, scheme, path, query_args):
        query_args['write_index'] = query_args.get('write_index', False)
        df.to_stata(path, **query_args)
