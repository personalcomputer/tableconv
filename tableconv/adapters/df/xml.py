import os
import sys

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin
from tableconv.exceptions import SourceParseError


@register_adapter(["xml"], read_only=True)
class XMLAdapter(FileAdapterMixin, Adapter):

    @staticmethod
    def load_file(scheme, path, params):
        raise SourceParseError(
            "Error: Almost all XML files need pre-processing first to be tabular. Please pre-process your XML into a "
            "JSON array using e.g.\n```\n"
            f"xml2json {path} | jq .records | {os.path.basename(sys.argv[0])} json:-"
            "\n```\n(might need `npm install -g xml2json`)"
        )

    @staticmethod
    def dump_file(df, scheme, path, params):
        raise NotImplementedError("XML adapter is read-only")
