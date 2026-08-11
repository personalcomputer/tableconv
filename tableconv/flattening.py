import logging
from collections.abc import Iterable

logger = logging.getLogger(__name__)


def log_flattened_columns(columns: Iterable, context: str) -> None:
    columns = list(columns)
    if not columns:
        return
    flattened_display = ", ".join([str(column) for column in columns])
    logger.warning(f"Flattened some columns into strings for {context}: {flattened_display}")
