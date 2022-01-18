# URL Errors

class InvalidURLError(RuntimeError):
    """
    Exposed in public API.
    Anything related to accessing the URL is considered a URL error.
    """
    pass


class InvalidParamsError(InvalidURLError):
    """ the parameters passed in are invalid/unsupported/unrecognized """
    pass


class IncapableDestinationError(InvalidURLError):
    """ dumping data to a destination, but the data requires features not supported by the destination """
    pass


class InvalidLocationReferenceError(InvalidURLError):
    """ the uri does not specify a complete extant location """
    pass


class InvalidURLSyntaxError(InvalidURLError):
    """ the uri cannot be parsed """
    pass


class UnrecognizedFormatError(InvalidURLError):
    """ the table format (aka scheme) specified is not supported """
    pass


# Query errors

class InvalidQueryError(RuntimeError):
    """
    Exposed in public API.
    The passed source/transform query is invalid or errored.
    """
    pass


class SchemaCoercionError(InvalidQueryError):
    pass


# Data Errors

class SuppliedDataError(RuntimeError):
    """ DEPRECATED. This is a backwards compatibility shim. Please reference DataError in new code. """
    pass


class DataError(SuppliedDataError):
    """
    Exposed in public API.
    Anything relating to the data WITHIN THE TABLE that is dynamically loaded in is considered a data error.
    """
    pass


class SourceDataError(DataError):
    pass


class EmptyDataError(SourceDataError):
    """
    Exposed in public API.
    The source data is empty.
    """
    pass


class SourceParseError(SourceDataError):
    """
    loading data from a source, and the data is corrupt or is not tabular
    (some flexible formats are sometimes tabular and sometimes not, e.g. YAML)
    """
    pass


class DestDataError(DataError):
    pass


class TableAlreadyExistsError(DestDataError):
    """ if_exists=fail, and the location reference already exists """
    pass


class AppendSchemeConflictError(DestDataError):
    """ if_exists=append, and the existing table's schema is incompatible with the new data """
    pass
