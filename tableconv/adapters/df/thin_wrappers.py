"""
"Thin wrapper" adapters: formats whose data model is a thin variation on an already-supported format, where the only
real difference is a fixed envelope/wrapper around an otherwise-standard payload. Each adapter here delegates the
heavy lifting to the canonical adapter for the underlying data model, so that behavior stays consistent and there is no
logic duplication.
"""

import json

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin
from tableconv.adapters.df.json import raw_array_to_df
from tableconv.exceptions import SourceParseError


@register_adapter(["har"], read_only=True)
class HarAdapter(FileAdapterMixin, Adapter):
    """HTTP Archive (HAR) adapter (read-only)."""

    # Path to the records array within the HAR document.
    _ENTRIES_PATH = ("log", "entries")

    @staticmethod
    def _read_raw(path):
        if hasattr(path, "read"):
            return path.read()
        return open(path).read()

    @classmethod
    def _extract_entries(cls, doc, source_label):
        if not isinstance(doc, dict):
            raise SourceParseError(f"Input {source_label} must be a JSON object (expected a HAR document)")
        node = doc
        for i, key in enumerate(cls._ENTRIES_PATH[:-1]):
            node = node.get(key)
            if not isinstance(node, dict):
                missing = ".".join(cls._ENTRIES_PATH[: i + 1])
                raise SourceParseError(f"Input {source_label} is missing required HAR field '{missing}'")
        entries = node.get(cls._ENTRIES_PATH[-1])
        if not isinstance(entries, list):
            here = ".".join(cls._ENTRIES_PATH)
            raise SourceParseError(f"Input {source_label} HAR field '{here}' must be a JSON array")
        return entries

    @staticmethod
    def load_file(scheme, path, params):
        raw_json = HarAdapter._read_raw(path)
        try:
            doc = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise SourceParseError(f"Input har is not valid JSON: {exc}") from exc
        entries = HarAdapter._extract_entries(doc, "har")
        return raw_array_to_df(entries, "har", params)
