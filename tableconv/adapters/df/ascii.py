from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin


def _render_value(value):
    if value is None:
        return ''
    return str(value).replace('\n', '\\n')


def _get_serialized_rows(rows):
    return [{key: _render_value(value) for key, value in row.items()} for row in rows]


def _get_column_max_lengths(rows, column_names):
    return {column: max([len(row[column]) for row in rows] + [len(column)]) for column in column_names}


def render_asciilite(ordered_fields, rows):
    """ Text table rendering inspired by sqlite CLI. """
    output_lines = []
    for row in rows:
        sorted_values = [row[field] for field in ordered_fields]
        serialized_value = [_render_value(value) for value in sorted_values]
        output_lines.append('|'.join(serialized_value))
    return '\n'.join(output_lines)


def render_unicodebox(ordered_fields, rows):
    """ Text table rendering inspired by ClickHouse. """
    serialized_rows = _get_serialized_rows(rows)
    max_lengths = _get_column_max_lengths(serialized_rows, ordered_fields)

    output_lines = []
    output_lines.append('┌─' + '─┬─'.join([field.ljust(max_lengths[field], '─') for field in ordered_fields]) + '─┐')
    for row in serialized_rows:
        rendered_values_list = []
        for field in ordered_fields:
            rendered_values_list.append(row[field].ljust(max_lengths[field]))
        output_lines.append('│ ' + ' │ '.join(rendered_values_list) + ' │')
    output_lines.append('└─' + '─┴─'.join(['─' * max_lengths[field] for field in ordered_fields]) + '─┘')
    return '\n'.join(output_lines)


@register_adapter(
    [
        'ascii',
        'asciiplain',
        'asciisimple',
        'asciigrid',
        'asciifancygrid',
        'asciipipe',
        'asciipresto',
        'asciipretty',
        'asciipsql',
        'asciilite',
        'asciibox',
        'mediawikiformat',
        'moinmoinformat',
        'jiraformat',
        'markdown',
        'md',
        'rst',
        'html',
        'latex',
        'tex',
    ], write_only=True
)
class ASCIIAdapter(FileAdapterMixin, Adapter):
    """
    Adapter focused on outputting ascii art style table renderings, such as those found in database CLIs.
    """
    text_based = True

    # @staticmethod
    # def _transform_df(df):
    #     def transform(obj):
    #         if isinstance(obj, datetime.datetime):
    #             if obj.tzinfo is not None:
    #                 obj = obj.astimezone(datetime.timezone.utc)
    #             # Warning: Interpret naive TS as being UTC.
    #             return obj.strftime('%Y-%m-%d %H:%M:%S')
    #         elif isinstance(obj, list) or isinstance(obj, dict):
    #             return str(obj)
    #         return obj
    #     df = df.applymap(transform)
    #     df = df.replace({np.nan: None})

    @staticmethod
    def get_example_url(scheme):
        return f'{scheme}:-'

    @staticmethod
    def dump_text_data(df, scheme, params):
        TABULATE_TABLEFMT = {
            'ascii': 'simple',
            'asciiplain': 'plain',
            'asciisimple': 'simple',
            'md': 'github',
            'markdown': 'github',
            'asciigrid': 'grid',
            'asciifancygrid': 'fancy_grid',
            'asciipipe': 'pipe',
            'asciipresto': 'presto',
            'asciipretty': 'pretty',
            'asciipsql': 'psql',
            'mediawikiformat': 'mediawiki',
            'moinmoinformat': 'moinmoin',
            'jiraformat': 'jira',
            'rst': 'rst',
            'latex': 'latex',
            'tex': 'latex',
        }
        if scheme in TABULATE_TABLEFMT:
            from tabulate import tabulate
            return tabulate(df.values.tolist(), list(df.columns), tablefmt=TABULATE_TABLEFMT[scheme])
        elif scheme == 'asciilite':
            return render_asciilite(list(df.columns), df.to_dict('records'))
        elif scheme == 'asciibox':
            return render_unicodebox(list(df.columns), df.to_dict('records'))
        else:
            raise AssertionError()
