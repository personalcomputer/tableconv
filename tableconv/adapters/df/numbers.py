import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.file_adapter_mixin import FileAdapterMixin


@register_adapter(["numbers"], read_only=True)
class NumbersAdapter(FileAdapterMixin, Adapter):
    @staticmethod
    def load_file(scheme, path, params):
        try:
            import numbers_parser
        except ImportError as exc:
            raise RuntimeError(
                "Interfacing with .numbers files requires installing additional packages!\n"
                " - `uv run --with numbers-parser tableconv`\n"
                " - Also required: `brew install snappy` (mac) or `sudo apt-get install libsnappy-dev` (ubuntu)\n"
                "(See also, additional install errors troubleshooting guide: "
                "https://github.com/andrix/python-snappy#frequently-asked-questions)"
            ) from exc
        doc = numbers_parser.Document(path)
        if params.get("sheet"):
            sheets_by_name = {item.name: item for item in doc.sheets}
            try:
                sheet = sheets_by_name[params.get("sheet")]
            except KeyError as exc:
                available_sheets_str = ", ".join([f'"{name}"' for name in sheets_by_name.keys()])
                raise KeyError(f'"{params.get("sheet")}" not found. Available sheets: {available_sheets_str}') from exc
        else:
            sheet = doc.sheets[0]
        data = sheet.tables[0].rows(values_only=True)
        return pd.DataFrame(data[1:], columns=data[0])
