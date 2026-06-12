import re
from typing import Any

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin
from tableconv.exceptions import InvalidParamsError, SourceParseError

ALIGNMENT_CELL_PATTERN = re.compile(r"^:?-{3,}:?$")


def _ends_with_unescaped_pipe(line: str) -> bool:
    if not line.endswith("|"):
        return False
    backslash_count = 0
    index = len(line) - 2
    while index >= 0 and line[index] == "\\":
        backslash_count += 1
        index -= 1
    return backslash_count % 2 == 0


def _split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if _ends_with_unescaped_pipe(line):
        line = line[:-1]

    cells = []
    cell = []
    escaping = False
    code_tick_count = 0
    index = 0
    while index < len(line):
        char = line[index]
        if escaping:
            cell.append(char if char == "|" else f"\\{char}")
            escaping = False
            index += 1
            continue
        if char == "\\":
            escaping = True
            index += 1
            continue
        if char == "`":
            run_end = index
            while run_end < len(line) and line[run_end] == "`":
                run_end += 1
            tick_count = run_end - index
            cell.append(line[index:run_end])
            if code_tick_count == 0:
                code_tick_count = tick_count
            elif code_tick_count == tick_count:
                code_tick_count = 0
            index = run_end
            continue
        if char == "|" and code_tick_count == 0:
            cells.append("".join(cell).strip())
            cell = []
            index += 1
            continue
        cell.append(char)
        index += 1
    if escaping:
        cell.append("\\")
    cells.append("".join(cell).strip())
    return cells


def _is_alignment_row(cells: list[str], column_count: int) -> bool:
    return len(cells) == column_count and all(ALIGNMENT_CELL_PATTERN.fullmatch(cell.strip()) for cell in cells)


def _normalize_row(cells: list[str], column_count: int) -> list[str | None]:
    if len(cells) < column_count:
        cells = cells + [""] * (column_count - len(cells))
    return [cell or None for cell in cells[:column_count]]


def _normalize_columns(cells: list[str]) -> list[str]:
    columns = []
    seen_counts: dict[str, int] = {}
    for index, cell in enumerate(cells):
        column = cell or f"Unnamed: {index}"
        seen_count = seen_counts.get(column, 0)
        columns.append(column if seen_count == 0 else f"{column}.{seen_count}")
        seen_counts[column] = seen_count + 1
    return columns


def _infer_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    for column in df.columns:
        non_null_values = df[column].notna()
        if not non_null_values.any():
            continue
        converted = pd.to_numeric(df[column], errors="coerce")
        if converted[non_null_values].notna().all():
            df[column] = converted
    return df


def _build_dataframe(header_cells: list[str], rows: list[list[str | None]]) -> pd.DataFrame:
    df = pd.DataFrame.from_records(rows, columns=_normalize_columns(header_cells))
    return _infer_numeric_columns(df)


def _is_code_fence(line: str) -> str | None:
    stripped_line = line.lstrip()
    if stripped_line.startswith("```"):
        return "```"
    if stripped_line.startswith("~~~"):
        return "~~~"
    return None


def _extract_tables(data: str) -> list[pd.DataFrame]:
    tables = []
    lines = data.splitlines()
    line_index = 0
    active_code_fence = None
    while line_index < len(lines) - 1:
        code_fence = _is_code_fence(lines[line_index])
        if active_code_fence:
            if code_fence == active_code_fence:
                active_code_fence = None
            line_index += 1
            continue
        if code_fence:
            active_code_fence = code_fence
            line_index += 1
            continue

        header_line = lines[line_index]
        delimiter_line = lines[line_index + 1]
        if "|" not in header_line or "|" not in delimiter_line:
            line_index += 1
            continue
        header_cells = _split_table_row(header_line)
        delimiter_cells = _split_table_row(delimiter_line)
        if not header_cells or not _is_alignment_row(delimiter_cells, len(header_cells)):
            line_index += 1
            continue

        rows = []
        body_line_index = line_index + 2
        while body_line_index < len(lines) and lines[body_line_index].strip() and "|" in lines[body_line_index]:
            rows.append(_normalize_row(_split_table_row(lines[body_line_index]), len(header_cells)))
            body_line_index += 1
        tables.append(_build_dataframe(header_cells, rows))
        line_index = body_line_index
    return tables


def _parse_table_index(params: dict[str, Any]) -> int:
    table_index_param = params.pop("table_index", 0)
    try:
        table_index = int(table_index_param)
    except ValueError as exc:
        raise InvalidParamsError("?table_index must be an integer") from exc
    if table_index < 0:
        raise InvalidParamsError("?table_index must be zero or greater")
    return table_index


@register_adapter(["md", "markdown"])
class MarkdownAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def get_example_url(scheme: str) -> str:
        return f"example.{scheme}"

    @staticmethod
    def load_text_data(scheme: str, data: str, params: dict[str, Any]) -> pd.DataFrame:
        table_index = _parse_table_index(params)
        tables = _extract_tables(data)
        if not tables:
            raise SourceParseError("Unable to find a Markdown table")
        if table_index >= len(tables):
            raise SourceParseError(f"Markdown table_index {table_index} out of range; found {len(tables)} table(s)")
        return tables[table_index]

    @staticmethod
    def dump_text_data(df: pd.DataFrame, scheme: str, params: dict[str, Any]) -> str:
        from tabulate import tabulate

        return tabulate(
            df.values.tolist(),
            list(df.columns),
            tablefmt="github",
            disable_numparse=True,
        )
