import argparse
import io
import logging
import logging.config
import os
import subprocess
import sys
import textwrap

from duckdb import __version__ as DUCKDB_VERSION_STR
from pandas import __version__ as PD_VERSION_STR

from tableconv.__version__ import __version__
from tableconv.adapters.df import adapters, read_adapters, write_adapters
from tableconv.adapters.df.base import NoConfigurationOptionsAvailable
from tableconv.core import (
    dump_multitable_to_url,
    load_multitable_from_url,
    load_url,
    parse_source_url,
    resolve_query_arg,
    validate_coercion_schema,
)
from tableconv.exceptions import DataError, InvalidQueryError, InvalidURLError
from tableconv.interactive import os_open, run_interactive_shell
from tableconv.uri import parse_uri

logger = logging.getLogger(__name__)

PROG = os.path.basename(sys.argv[0])
PY_VERSION_STR = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def get_supported_schemes_list_str() -> str:
    descriptions = []
    for scheme, adapter in adapters.items():
        disclaimer = ""
        if scheme not in write_adapters:
            disclaimer = "(source only)"
        elif scheme not in read_adapters:
            disclaimer = "(dest only)"
        example = adapter.get_example_url(scheme)
        descriptions.append(f"{example} {disclaimer}")
    return textwrap.indent("\n".join(sorted(descriptions)), "  ")


def set_up_logging():
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S %Z",
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "level": "DEBUG",
                    "formatter": "default",
                    "stream": "ext://sys.stderr",
                },
            },
            "loggers": {
                "googleapiclient.discovery_cache": {
                    "level": "ERROR",
                },
                "numexpr": {
                    "level": "ERROR",
                },
                "botocore": {
                    "level": "WARNING",
                },
                "thrift.transport.TSocket": {
                    "level": "CRITICAL",
                },
            },
            "root": {
                "level": "INFO",
                "handlers": ["default"],
            },
        }
    )


class NoExitArgParser(argparse.ArgumentParser):
    """
    Py <= 3.8 polyfill for `exit_on_error=False`
    """

    def __init__(self, *args, **kwargs):
        assert kwargs["exit_on_error"] is False
        del kwargs["exit_on_error"]
        super().__init__(*args, **kwargs)

    def error(self, message):
        raise argparse.ArgumentError(None, message)


def abort_with_usage_error(error: str | Exception, usage=None):
    """Display an argparse-style error message."""
    from rich.console import Console

    console = Console(file=sys.stderr)

    if usage:
        console.print(f"usage: {usage % dict(prog=PROG)}", style="magenta", highlight=False)
    if isinstance(error, Exception):
        logger.debug(error, exc_info=True)
    if isinstance(error, str):
        error_msg = error
    else:
        error_msg = f"{str(error)}\n({error.__class__.__name__})"
    console.print(f"error: {error_msg}", style="magenta", highlight=False)
    sys.exit(1)


def run_configuration_mode(argv):
    # Special parser mode for this hidden feature. Each adapter can specify its own "configure" args, so we cannot
    # use the main argparse parser.
    CONFIGURE_USAGE = "usage: %(prog)s configure ADAPTER [options]"
    try:
        if len(argv) < 2 or argv[1].startswith("--"):
            raise argparse.ArgumentError(None, "Must specify adapter")
        if argv[1] not in adapters:
            raise argparse.ArgumentError(None, f'Unrecognized adapter "{argv[1]}"')
        adapter = adapters[argv[1]]
        required_args = adapter.get_configuration_options_description()
        adapter_config_parser = NoExitArgParser(exit_on_error=False)
        adapter_config_parser.add_argument("configure")
        adapter_config_parser.add_argument("ADAPTER")
        for arg, description in required_args.items():
            adapter_config_parser.add_argument(f"--{arg.replace('_', '-')}", help=description, required=True)
        args = vars(adapter_config_parser.parse_args(argv))
        args = {name: value for name, value in args.items() if value is not None and name in required_args}
        adapter.set_configuration_options(args)
    except NoConfigurationOptionsAvailable as exc:
        abort_with_usage_error(f"{exc.args[0]} has no configuration options", CONFIGURE_USAGE)
    except argparse.ArgumentError as exc:
        abort_with_usage_error(exc, CONFIGURE_USAGE)


def parse_schema_coercion_arg(args):
    if not args.schema_coercion:
        return None
    import yaml

    iostr = io.StringIO()
    iostr.write(resolve_query_arg(args.schema_coercion))
    iostr.seek(0)
    FORMAT_ERR_MSG = (
        "Coercion schema must be specified as a valid YAML map of field names (string) to type names (string)"
    )
    try:
        schema_coercion = yaml.safe_load(iostr)
    except yaml.YAMLError:
        abort_with_usage_error(FORMAT_ERR_MSG)
    if not isinstance(schema_coercion, dict):
        abort_with_usage_error(FORMAT_ERR_MSG)
    for val in list(schema_coercion.values()) + list(schema_coercion.keys()):
        if not isinstance(val, str):
            abort_with_usage_error(FORMAT_ERR_MSG)
    try:
        validate_coercion_schema(schema_coercion)
    except ValueError as exc:
        abort_with_usage_error(exc)
    return schema_coercion


def parse_dest_arg(args):
    if args.DEST_URL:
        return args.DEST_URL
    try:
        source_scheme, _ = parse_source_url(args.SOURCE_URL)
    except InvalidURLError as exc:
        abort_with_usage_error(exc)

    if source_scheme in write_adapters and write_adapters[source_scheme].text_based and not args.interactive:
        # Default to outputting to console, in same format as input
        dest = f"{source_scheme}:-"
    else:
        # Otherwise, default to ascii output to console
        dest = "ascii:-"
    logger.debug(f"No output destination specified, defaulting to {parse_uri(dest).scheme} output to stdout")
    return dest


def main(argv=None):
    set_up_logging()
    # Process arguments
    parser = NoExitArgParser(
        usage="%(prog)s SOURCE_URL [-q QUERY_SQL] [-o DEST_URL]",
        formatter_class=argparse.RawDescriptionHelpFormatter,  # Necessary for \n in epilog
        epilog=(
            f"supported url schemes:\n{get_supported_schemes_list_str()}\n\n"
            "help & support:\n  https://github.com/personalcomputer/tableconv/issues/new"
        ),
        exit_on_error=False,
    )
    parser.add_argument("SOURCE_URL", type=str, help="Specify the data source URL.")
    parser.add_argument(
        "-q",
        "-Q",
        "--query",
        dest="source_query",
        default=None,
        help="Query to run on the source. Even for non-SQL datasources (e.g. csv or json), SQL querying is still "
        "supported, try `SELECT * FROM data`.",
    )
    parser.add_argument(
        "-F",
        "--filter",
        dest="intermediate_filter_sql",
        default=None,
        help="Filter (i.e. transform) the input data using a SQL query operating on the dataset in memory using "
        "DuckDB SQL.",
    )
    parser.add_argument(
        "-o",
        "--dest",
        "--out",
        "--output",
        dest="DEST_URL",
        type=str,
        help="Specify the data destination URL. If this destination already exists, be aware that the default "
        "behavior is to overwrite.",
    )
    parser.add_argument("-i", "--interactive", action="store_true", help="Enter interactive REPL query mode.")
    parser.add_argument(
        "--open",
        dest="open_dest",
        action="store_true",
        help="Open resulting file/url in the operating system desktop environment. "
        "(not supported for all destination types)",
    )
    parser.add_argument(
        "--autocache", "--cache", action="store_true", help="Cache network data, and reuse cached data."
    )
    parser.add_argument(
        "-v",
        "--verbose",
        "--debug",
        dest="verbose",
        action="store_true",
        help="Show debug details, including API calls and error sources.",
    )
    version_str = f"{__version__} (Python {PY_VERSION_STR}, DuckDB {DUCKDB_VERSION_STR}, Pandas {PD_VERSION_STR})"
    if os.environ.get("TABLECONV_IS_DAEMON"):
        version_str += " (running from daemon)"
    parser.add_argument(
        "--version",
        action="version",
        help="Show version number and exit",
        version=f"{PROG} {version_str}",
    )
    parser.add_argument("--quiet", action="store_true", help="Only display errors.")
    parser.add_argument(
        "--print",
        "--print-dest",
        action="store_true",
        help="Print resulting URL/path to stdout, for chaining with other commands.",
    )
    parser.add_argument(
        "--debug-shell",
        "--pandas-debug-shell",
        "--debug-pandas-shell",
        "--debugshell",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--schema",
        "--coerce-schema",
        dest="schema_coercion",
        default=None,
        help="Coerce source schema according to a schema definition. (WARNING: experimental feature)",
    )
    parser.add_argument(
        "--restrict-schema",
        dest="restrict_schema",
        action="store_true",
        help="Exclude all columns not included in the SCHEMA_COERCION definition. (WARNING: experimental feature)",
    )
    parser.add_argument(
        "--daemonize",
        action="store_true",
        help="Tableconv startup time (python startup time) is slow. To mitigate that, you can first run tableconv as "
        "a daemon, and then all future invocations will be fast. (while daemon is still alive) "
        "(WARNING: experimental feature)",
    )
    parser.add_argument(
        "--multitable",
        "--multifile",
        action="store_true",
        help='Convert entire "database"s of tables from one format to another, such as folders with many csvs, a '
        "multi-tab spreadsheet, or an actual RDBMS (WARNING: This is an experimental mode, very rough, details "
        "undocumented)",
    )
    if argv and argv[0] in ("configure", "--configure"):
        # This is a hidden feature because it is very incomplete right now.
        run_configuration_mode(argv)
        sys.exit(0)

    try:
        args = parser.parse_args(argv)
        if args.quiet and args.verbose:
            raise argparse.ArgumentError(
                None, "Options --verbose and --quiet are incompatible, cannot specify both at once."
            )
        if args.source_query and args.interactive:
            raise argparse.ArgumentError(
                None, "Options --query and --interactive are incompatible, cannot specify both at once."
            )
        if not args.SOURCE_URL:
            raise argparse.ArgumentError(None, "SOURCE_URL empty")
    except argparse.ArgumentError as exc:
        abort_with_usage_error(exc, parser.usage)

    if args.verbose:
        logging.config.dictConfig(
            {
                "version": 1,
                "incremental": True,
                "root": {"level": "DEBUG"},
            }
        )
    if args.quiet:
        logging.config.dictConfig(
            {
                "version": 1,
                "incremental": True,
                "root": {"level": "ERROR"},
            }
        )

    schema_coercion = parse_schema_coercion_arg(args)
    dest = parse_dest_arg(args)

    try:
        # Execute interactive
        if args.interactive:
            run_interactive_shell(
                args.SOURCE_URL,
                dest,
                args.intermediate_filter_sql,
                args.open_dest,
                schema_coercion,
                args.restrict_schema,
                args.autocache,
            )
            return

        if args.multitable:
            # Crazy experimental feature. Undocumented. Low Quality.
            df_multi_table = load_multitable_from_url(args.SOURCE_URL)
            output = dump_multitable_to_url(df_multi_table, dest)
        else:
            # Load source
            table = load_url(
                url=args.SOURCE_URL,
                query=args.source_query,
                filter_sql=args.intermediate_filter_sql,
                schema_coercion=schema_coercion,
                restrict_schema=args.restrict_schema,
                autocache=args.autocache,
            )
            if args.debug_shell:
                df = table.as_pandas_df()  # noqa: F841
                breakpoint()

            # Dump to destination
            output = table.dump_to_url(url=dest)
    except (DataError, InvalidQueryError, InvalidURLError) as exc:
        abort_with_usage_error(exc)

    if output:
        logger.info(f"Wrote out {output}")
        if args.print:
            print(output)
        if args.open_dest:
            os_open(output)

    return 0


def main_wrapper(argv):
    """
    Wrapper to provide special traceback handling specifically for subprocess.CalledProcessError errors that are
    crashing the whole program: ensure that that the subprogram's raw output (presumably containing an error message)
    is also printed.
    """
    try:
        return main(argv)
    except subprocess.CalledProcessError as exc:
        if exc.stdout and exc.stdout.strip():
            print(exc.stdout.strip())
        if exc.stderr and exc.stderr.strip():
            print(exc.stderr.strip())
        raise


if __name__ == "__main__":
    main_wrapper(sys.argv[1:])
