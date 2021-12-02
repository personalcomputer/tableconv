#!/usr/bin/env python3
import argparse
import logging
import logging.config
import os
import readline
import sys
import textwrap

from .__version__ import __version__
from .adapters.df import adapters, read_adapters, write_adapters
from .adapters.df.base import NoConfigurationOptionsAvailable
from .core import SuppliedDataError, load_url, parse_source_url
from .uri import parse_uri

logger = logging.getLogger(__name__)

INTERACTIVE_HIST_PATH = os.path.join(os.path.expanduser("~"), ".tableconv_history")
INTERACTIVE_PAGER_BIN = os.environ.get('PAGER', 'less')
INTERACTIVE_PAGER_CMD = \
    [INTERACTIVE_PAGER_BIN, '-S', '--shift', '10'] if INTERACTIVE_PAGER_BIN == 'less' else [INTERACTIVE_PAGER_BIN]


def get_supported_schemes_list_str() -> str:
    descriptions = []
    for scheme, adapter in adapters.items():
        disclaimer = ''
        if scheme not in write_adapters:
            disclaimer = '(source only)'
        elif scheme not in read_adapters:
            disclaimer = '(dest only)'
        example = adapter.get_example_url(scheme)
        descriptions.append(f'{example} {disclaimer}')
    return textwrap.indent('\n'.join(sorted(descriptions)), '  ')


def run_interactive_shell(original_source: str, source: str, dest: str, intermediate_filter_sql: str, open_dest: bool
                          ) -> None:
    # shell_dimensions_raw = subprocess.check_output(['stty', 'size']).split()
    # shell_height = int(shell_dimensions_raw[0])
    # shell_width = int(shell_dimensions_raw[1])
    try:
        readline.read_history_file(INTERACTIVE_HIST_PATH)
    except FileNotFoundError:
        open(INTERACTIVE_HIST_PATH, 'wb').close()
    readline.set_history_length(1000)

    if len(original_source) <= (7 + 5 + 19):
        prompt = f'{original_source}=> '
    else:
        prompt = f'{original_source[:7]}[...]{original_source[-19:]}=> '

    while True:
        try:
            raw_query = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        source_query = raw_query.strip()
        if not source_query:
            continue
        readline.append_history_file(1, INTERACTIVE_HIST_PATH)
        if source_query[0] in ('\\', '.', '/'):
            if source_query[1:] in ('schema', 'dt', 'd', 'd+', 'describe', 'show'):
                table = load_url(source)
                print('Table "data":')
                for column, column_data in table.get_json_schema()['properties'].items():
                    if 'type' in column_data:
                        if isinstance(column_data["type"], str):
                            types = [column_data["type"]]
                        elif isinstance(column_data["type"], list):
                            types = column_data["type"]
                        else:
                            raise AssertionError
                    else:
                        assert('anyOf' in column_data)
                        types = [i['type'] for i in column_data['anyOf']]
                    print(f'  "{column}" {", ".join(types)}')
                continue
        try:
            # Read source
            table = load_url(url=source, query=source_query, filter_sql=intermediate_filter_sql)
            # Write destination
            output = table.dump_to_url(url=dest)
            if output:
                logger.info(f'Wrote out {output}')
            if output and open_dest:
                os.system(f'open "{output}"')
        except SuppliedDataError:
            print('(0 rows)')
        except Exception as exc:
            print(exc)


def set_up_logging():
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(name)s](%(levelname)s) %(message)s',
            }
        },
        'handlers': {
            'default': {
                'class': 'logging.StreamHandler',
                'level': 'DEBUG',
                'formatter': 'standard',
                'stream': 'ext://sys.stderr',
            }
        },
        'loggers': {
            '': {
                'level': 'INFO',
                'handlers': ['default'],
            },
            'googleapiclient.discovery_cache': {
                'level': 'ERROR',
            },
            'botocore': {
                'level': 'WARNING',
            },
        },
    })


class NoExitArgParser(argparse.ArgumentParser):
    """
    Py <= 3.8 polyfill for `exit_on_error=False`
    """
    def __init__(self, *args, **kwargs):
        assert(kwargs['exit_on_error'] is False)
        del kwargs['exit_on_error']
        super().__init__(*args, **kwargs)

    def error(self, message):
        raise argparse.ArgumentError(None, message)


def raise_argparse_style_error(usage, error):
    print(f'usage: {usage % dict(prog=os.path.basename(sys.argv[0]))}', file=sys.stderr)
    print(f'error: {error}', file=sys.stderr)
    sys.exit(1)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    set_up_logging()

    # Process arguments
    parser = NoExitArgParser(
        usage='%(prog)s SOURCE_URL [-q QUERY_SQL] [-o DEST_URL]',
        formatter_class=argparse.RawDescriptionHelpFormatter,  # Necessary for \n in epilog
        epilog=f'supported url schemes:\n{get_supported_schemes_list_str()}',
        exit_on_error=False,
    )
    parser.add_argument('SOURCE_URL', type=str, help='Specify the data source URL.')
    parser.add_argument('-q', '--query', dest='source_query', default=None, help='Query to run on the source. Even for non-SQL datasources (e.g. csv or json), SQL querying is still supported, try `SELECT * FROM data`.')
    parser.add_argument('-F', '--filter', dest='intermediate_filter_sql', default=None, help='Filter (aka transform) the input data using a SQL query operating on the dataset in memory using DuckDB SQL.')
    parser.add_argument('-o', '--dest', '--out', dest='DEST_URL', type=str, help='Specify the data destination URL. If this destination already exists, be aware that the default behavior is to overwrite.')
    parser.add_argument('-i', '--interactive', action='store_true', help='Enter interactive REPL query mode')
    parser.add_argument('--open', dest='open_dest', action='store_true', help='Open resulting file/url (not supported for all destination types)')
    parser.add_argument('-v', '--verbose', '--debug', dest='verbose', action='store_true', help='Show debug details, including all API calls.')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('--quiet', action='store_true', help='Only display errors.')

    if argv and argv[0] in ('self-test', 'selftest', '--self-test', '--selftest'):
        # Hidden feature to self test
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.exit(os.system('flake8 --ignore E501,F403,W503 tests tableconv setup.py; pytest'))

    if argv and argv[0] in ('configure', '--configure'):
        # Special parser mode for this hidden feature. Each adapter can specify its own "configure" args, so we cannot
        # use the main argparse parser.
        USAGE = 'usage: %(prog)s configure ADAPTER [options]'
        try:
            if len(argv) < 2 or argv[1].startswith('--'):
                raise argparse.ArgumentError(None, 'Must specify adapter')
            if argv[1] not in adapters:
                raise argparse.ArgumentError(None, f'Unrecognized adapter "{argv[1]}"')
            adapter = adapters[argv[1]]
            args_list = adapter.get_configuration_options_description()
            adapter_config_parser = NoExitArgParser(exit_on_error=False)
            adapter_config_parser.add_argument('CONFIGURE')
            adapter_config_parser.add_argument('ADAPTER')
            for arg, description in args_list.items():
                adapter_config_parser.add_argument(f'--{arg}', help=description)
            args = vars(adapter_config_parser.parse_args(argv))
            args = {name: value for name, value in args.items() if value is not None and name in args_list}
            adapter.set_configuration_options(args)
        except NoConfigurationOptionsAvailable as exc:
            raise_argparse_style_error(USAGE, f'{exc.args[0]} has no configuration options')
        except argparse.ArgumentError as exc:
            raise_argparse_style_error(USAGE, exc)
        return

    try:
        args = parser.parse_args(argv)
        if args.quiet and args.verbose:
            raise argparse.ArgumentError(
                None, 'Options --verbose and --quiet are incompatible, cannot specify both at once.')
        if args.source_query and args.interactive:
            raise argparse.ArgumentError(
                None, 'Options --query and --interactive are incompatible, cannot specify both at once.')
        if not args.SOURCE_URL:
            raise argparse.ArgumentError(None, 'SOURCE_URL empty')
    except argparse.ArgumentError as exc:
        raise_argparse_style_error(parser.usage, exc)

    if args.verbose:
        logging.config.dictConfig({
            'version': 1,
            'incremental': True,
            'root': {'level': 'DEBUG'},
        })
    if args.quiet:
        logging.config.dictConfig({
            'version': 1,
            'incremental': True,
            'root': {'level': 'ERROR'},
        })

    # Set source
    source = args.SOURCE_URL
    original_source = source

    # Set dest
    dest = args.DEST_URL
    if dest is None:
        source_scheme, _ = parse_source_url(source)
        if source_scheme in write_adapters and write_adapters[source_scheme].text_based and not args.interactive:
            # Default to outputting to console, in same format as input
            dest = f'{source_scheme}:-'
        else:
            # Otherwise, default to ascii output to console
            dest = 'ascii:-'
        logger.debug(f'No output destination specified, defaulting to {parse_uri(dest).scheme} output to stdout')

    # Execute interactive
    if args.interactive:
        run_interactive_shell(original_source, source, dest, args.intermediate_filter_sql, args.open_dest)
        return

    # Read source (load source)
    try:
        table = load_url(url=source, query=args.source_query, filter_sql=args.intermediate_filter_sql)
    except SuppliedDataError as e:
        logger.error(str(e))
        sys.exit(1)

    # Write destination (dump to destination)
    output = table.dump_to_url(url=dest)

    if output:
        logger.info(f'Wrote out {output}')

    # Open
    if output and args.open_dest:
        os.system(f'open "{output}"')


if __name__ == '__main__':
    main()
