from collections.abc import Iterator

import pandas as pd

from tableconv.in_memory_query import query_in_memory


class NoConfigurationOptionsAvailable(Exception):
    pass


class Adapter:
    @classmethod
    def get_configuration_options_description(cls):
        raise NoConfigurationOptionsAvailable(str(cls.__name__))

    @classmethod
    def set_configuration_options(cls, args):
        raise NoConfigurationOptionsAvailable(str(cls.__name__))

    @classmethod
    def _query_in_memory(cls, df, query):
        if query:
            return query_in_memory([("data", df)], query)
        return df

    @classmethod
    def get_example_url(cls, scheme: str) -> str:
        raise NotImplementedError(f"get_example_url not defined for {scheme}")

    @classmethod
    def load(cls, uri: str, query: str | None) -> pd.DataFrame:
        raise NotImplementedError

    @classmethod
    def dump(cls, df: pd.DataFrame, uri: str) -> str | None:
        raise NotImplementedError

    @classmethod
    def load_multitable(cls, uri: str) -> Iterator[tuple[str, pd.DataFrame]]:
        raise NotImplementedError

    @classmethod
    def dump_multitable(cls, df_multitable: Iterator[tuple[str, pd.DataFrame]], uri: str) -> str:
        raise NotImplementedError


adapters: dict[str, type[Adapter]] = {}
read_adapters: dict[str, type[Adapter]] = {}
write_adapters: dict[str, type[Adapter]] = {}


def _ensure_scheme_is_available(scheme: str, cls: type[Adapter]) -> None:
    registered_adapter = adapters.get(scheme)
    if registered_adapter and registered_adapter is not cls:
        raise RuntimeError(
            f'Scheme "{scheme}" is already registered to {registered_adapter.__name__}; '
            f"cannot also register {cls.__name__}."
        )


def register_adapter(schemes: list[str], write_only: bool = False, read_only: bool = False):
    """
    TODO: better decorator api proposal:
    @register_write_adapter(
        protocol='sql_values', aliases=[], parameters={}, example_url='', file_based=True)
    """

    def decorator(cls):
        global read_adapters
        global write_adapters
        for scheme in schemes:
            _ensure_scheme_is_available(scheme, cls)
            adapters[scheme] = cls
            if not write_only:
                read_adapters[scheme] = cls
            if not read_only:
                write_adapters[scheme] = cls
        return cls

    return decorator
