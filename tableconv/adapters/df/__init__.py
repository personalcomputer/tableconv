from .base import write_adapters, read_adapters, adapters  # noqa: F401

# TODO: Register adapters in a cleaner way (dynamic adapter loading?). Just get rid of the `import *`.
from .ascii import *  # noqa: F401
from .aws_athena import *  # noqa: F401
from .aws_dynamodb import *  # noqa: F401
from .gsheets import *  # noqa: F401
from .jira import *  # noqa: F401
from .json import *  # noqa: F401
from .nested_list import *  # noqa: F401
from .pandas_io import *  # noqa: F401
from .python import *  # noqa: F401
from .smart_sheet import *  # noqa: F401
from .sql import *  # noqa: F401
from .sql_literal import *  # noqa: F401
from .sumo_logic import *  # noqa: F401
from .text_array import *  # noqa: F401
from .yaml import *  # noqa: F401
