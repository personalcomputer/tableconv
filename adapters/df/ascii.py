import pandas as pd

from .base import register_adapter, Adapter
from .file_adapter_mixin import FileAdapterMixin


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


def render_asciiborderless(ordered_fields, rows):
    """ Text table rendering inspired by psql. """
    serialized_rows = _get_serialized_rows(rows)
    max_lengths = _get_column_max_lengths(serialized_rows, ordered_fields)

    output_lines = []
    output_lines.append(' ' + ' | '.join([field.center(max_lengths[field]) for field in ordered_fields]) + ' ')
    output_lines.append('-' + '-+-'.join(['-'*max_lengths[field] for field in ordered_fields]) + '-')
    for row in serialized_rows:
        rendered_values_list = []
        for field in ordered_fields:
            rendered_values_list.append(row[field].ljust(max_lengths[field]))
        output_lines.append(' ' + ' | '.join(rendered_values_list) + ' ')
    # Fully imitate psql by adding row count
    # if len(rows) == 1:
    #     output_lines.append(f'({len(rows)} row)')
    # else:
    #     output_lines.append(f'({len(rows)} rows)')
    return '\n'.join(output_lines)


def render_asciibox(ordered_fields, rows):
    """ Text table rendering inspired by SQLLine or pgcli. """
    serialized_rows = _get_serialized_rows(rows)
    max_lengths = _get_column_max_lengths(serialized_rows, ordered_fields)

    output_lines = []
    output_lines.append('+-' + '-+-'.join(['-'*max_lengths[field] for field in ordered_fields]) + '-+')
    output_lines.append('| ' + ' | '.join([field.center(max_lengths[field]) for field in ordered_fields]) + ' |')
    output_lines.append('|-' + '-+-'.join(['-'*max_lengths[field] for field in ordered_fields]) + '-|')
    for row in serialized_rows:
        rendered_values_list = []
        for field in ordered_fields:
            rendered_values_list.append(row[field].ljust(max_lengths[field]))
        output_lines.append('| ' + ' | '.join(rendered_values_list) + ' |')
    output_lines.append('+-' + '-+-'.join(['-'*max_lengths[field] for field in ordered_fields]) + '-+')
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
    output_lines.append('└─' + '─┴─'.join(['─'*max_lengths[field] for field in ordered_fields]) + '─┘')
    return '\n'.join(output_lines)


def render_markdown(ordered_fields, rows):
    """ Text table rendering compatible with Github-Flavored Markdown. """
    serialized_rows = _get_serialized_rows(rows)
    max_lengths = _get_column_max_lengths(serialized_rows, ordered_fields)

    output_lines = []
    output_lines.append('| ' + ' | '.join([field.center(max_lengths[field]) for field in ordered_fields]) + ' |')
    output_lines.append('| ' + ' | '.join(['-'*max_lengths[field] for field in ordered_fields]) + ' |')
    for row in serialized_rows:
        rendered_values_list = []
        for field in ordered_fields:
            rendered_values_list.append(row[field].ljust(max_lengths[field]))
        output_lines.append('| ' + ' | '.join(rendered_values_list) + ' |')
    return '\n'.join(output_lines)


@register_adapter(['asciilite', 'asciiborderless', 'asciibox', 'unicodebox', 'markdown', 'md'], write_only=True)
class ASCIIAdapter(FileAdapterMixin, Adapter):
    """
    Adapter focused on ascii art style table renderings, such as those found in database CLIs.
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
    def dump_text_data(df, scheme, kwargs):
        ordered_fields = list(df.columns)
        rows = df.to_dict('records')

        if scheme == 'asciilite':
            out_text = render_asciilite(ordered_fields, rows)
        elif scheme == 'asciiborderless':
            out_text = render_asciiborderless(ordered_fields, rows)
        elif scheme == 'asciibox':
            out_text = render_asciibox(ordered_fields, rows)
        elif scheme == 'unicodebox':
            out_text = render_unicodebox(ordered_fields, rows)
        elif scheme in ('markdown', 'md'):
            out_text = render_markdown(ordered_fields, rows)
        else:
            raise AssertionError()
        return out_text
