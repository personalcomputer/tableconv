import logging

# One gripe of python is some libraries immediately start logging unhelp stuff the moment you import them.
# This triggers flake8 E402 (code before imports error). How are you supposed to resolve this cleanly?
logging.getLogger("numexpr").setLevel(logging.ERROR)

from .__version__ import __version__  # noqa: E402
from .core import IntermediateExchangeTable, load_url  # noqa: E402
from .exceptions import DataError, EmptyDataError, InvalidQueryError, InvalidURLError, SuppliedDataError  # noqa: E402

__all__ = [
    "IntermediateExchangeTable",
    "load_url",
    "EmptyDataError",
    "DataError",
    "InvalidQueryError",
    "InvalidURLError",
    "SuppliedDataError",
    "__version__",
]
