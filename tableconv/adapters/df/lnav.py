import os
import shutil
import subprocess
import tempfile

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.pandas_io import CSVAdapter
from tableconv.uri import parse_uri


@register_adapter(["lnav"], read_only=True)
class LnavAdapter(Adapter):
    """
    Lnav is a neat tool. This Adapter fails to expose its capabilities properly though, it is just a start, a reminder
    to revisit this later.

    Example:
    tc lnav:/var/log/syslog.1 -Q 'select *, log_body from data limit 10'
    """

    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}:/var/log/example.log"

    @classmethod
    def load(cls, uri: str, query: str | None) -> pd.DataFrame:
        if shutil.which("lnav") is None:
            raise RuntimeError(
                "lnav is not installed or not available in PATH.\n"
                "Refer to https://github.com/tstack/lnav?tab=readme-ov-file#installation"
            )

        parsed_uri = parse_uri(uri)
        params = parsed_uri.query

        format_result = subprocess.run(
            ["lnav", parsed_uri.path, "-nc", ";select format from lnav_file"],
            text=True,
            capture_output=True,
            check=True,
        )
        format = format_result.stdout.splitlines()[1].strip()

        if not query:
            query = "select * from data"
        query = query.replace("from data", f"from {format}", 1)

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_filename = os.path.join(temp_dir, "lnav.csv")
            subprocess.run(
                ["lnav", parsed_uri.path, "-nqc", f";{query}", "-c", f":write-csv-to {csv_filename}"],
                text=True,
                check=True,
            )
            df = CSVAdapter.load_file("csv", csv_filename, params)

        return df
