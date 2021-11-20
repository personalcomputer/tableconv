
from .base import Adapter, register_adapter
from .file_adapter_mixin import FileAdapterMixin


@register_adapter(['sql_values'], write_only=True)
class SQLLiteralAdapter(FileAdapterMixin, Adapter):
    """ Currently only supports Postgres-flavored VALUES syntax"""
    text_based = True

    @staticmethod
    def dump_text_data(df, scheme, kwargs):
        data = df.to_dict(orient='split')

        table_name = 'data'
        columns_str = ', '.join([f'"{name}"' for name in data['columns']])
        rendered_tuples = [[repr(value) for value in item] for item in data['data']]
        # for raw_tuple in data['data']:
        #     r_tuple = []
        #     for value in raw_tuple:
        #         if isinstance(value, str):
        #             r_tuple.append(repr(value))
        values_str = ', '.join([f'({", ".join(items)})' for items in rendered_tuples])

        return f'(VALUES {values_str}) {table_name}({columns_str})'
