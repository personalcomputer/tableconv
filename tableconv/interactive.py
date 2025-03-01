import datetime
import logging
import os
import readline
import shlex
import shutil
import subprocess
import sys

from tableconv.core import IntermediateExchangeTable, load_url
from tableconv.exceptions import DataError, EmptyDataError, InvalidQueryError, InvalidURLError

logger = logging.getLogger(__name__)

INTERACTIVE_HIST_PATH = os.path.join(os.path.expanduser("~"), ".tableconv_history")

multiline = False


def os_open(url: str):
    for opener in {"xdg-open", "open", "start", "Invoke-Item"}:
        if shutil.which(opener):
            opener_cmd = [opener, url]
            logger.debug(f"Opening via `{shlex.join(opener_cmd)}`")
            subprocess.run(opener_cmd)
            return
    raise RuntimeError(f"Not sure how to open files/urls on {sys.platform}")


def handle_administrative_command(query: str, source: str, last_result: IntermediateExchangeTable | None):
    cmd_char = query[0]
    cmd = query[1:].split(" ")
    if cmd[0] in ("h", "help", "?"):
        print(
            "Commands:\n"
            + f"  {cmd_char}dt (describe table)\n"
            + f"  {cmd_char}ds (describe table, sorted)\n"
            + f"  {cmd_char}export URL (save results)\n"
            + f"  {cmd_char}m (toggle multiline mode (queries terminated by semicolon instead of newline))"
        )
    elif cmd[0] in ("schema", "dt", "dt+", "ds", "d", "d+", "describe", "show"):
        table = load_url(source)
        print('Table "data":', file=sys.stderr)
        columns = table.get_json_schema()["properties"].items()
        if cmd[0] == "ds":
            columns = sorted(columns)
        for column, column_data in columns:
            if "type" in column_data:
                if isinstance(column_data["type"], str):
                    types = [column_data["type"]]
                elif isinstance(column_data["type"], list):
                    types = column_data["type"]
                else:
                    raise AssertionError
            else:
                assert "anyOf" in column_data
                types = []
                for i in column_data["anyOf"]:
                    if isinstance(i["type"], str):
                        types.append(i["type"])
                    elif isinstance(i["type"], list):
                        types.extend(i["type"])
                    else:
                        raise AssertionError
            print(f'  "{column}" {", ".join(types)}')
    elif cmd[0] in ("m", "multiline"):
        global multiline
        multiline = not multiline
        print(f"(Multiline {'enabled' if multiline else 'disabled'})", file=sys.stderr)
    elif cmd[0] in ("save", "export", "copy", "out", "o"):
        if last_result is None:
            print("Error: No results to export. Run a query first.", file=sys.stderr)
            return
        if len(cmd) < 2:
            print("Error: Please specify export URL/path.", file=sys.stderr)
            return
        try:
            url = cmd[1]
            output = last_result.dump_to_url(url=url)
        except (InvalidURLError, DataError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return
        if not output:
            output = url
        print(f"(Wrote out {output})", file=sys.stderr)
    else:
        print(f"Unrecognized command {query}. For help, see {cmd_char}help", file=sys.stderr)


def create_empty_file(path):
    open(path, "wb").close()  # noqa: SIM115


def run_interactive_shell(
    source: str, dest: str, intermediate_filter_sql: str, open_dest: bool, schema_coercion, restrict_schema, autocache
) -> None:
    # shell_width, shell_height = shutil.get_terminal_size()
    try:
        readline.read_history_file(INTERACTIVE_HIST_PATH)
    except FileNotFoundError:
        create_empty_file(INTERACTIVE_HIST_PATH)
    except OSError as e:
        if e.args[0] == 22:  # "Invalid argument"
            # Corrupt file? I'm not sure how this happens, but it has happened to me.
            date_str = datetime.datetime.now().strftime("%Y%m%d")
            corrupt_path = INTERACTIVE_HIST_PATH + ".invalid." + date_str + ".bak"
            os.rename(INTERACTIVE_HIST_PATH, corrupt_path)
            create_empty_file(INTERACTIVE_HIST_PATH)
            logger.warning(
                f"Invalid interactive shell history file found at {INTERACTIVE_HIST_PATH}. "
                f"Moved to {corrupt_path} and created new blank file in its place."
            )

    readline.set_history_length(1000)

    if len(source) <= (7 + 5 + 19):
        prompt = f"{source}=> "
    else:
        prompt = f"{source[:7]}[...]{source[-19:]}=> "

    last_result = None

    query_buffer = ""

    while True:
        try:
            raw_query = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            break
        if not raw_query:
            continue

        readline.add_history(raw_query)
        readline.write_history_file(INTERACTIVE_HIST_PATH)

        if raw_query[0] in ("\\", ".", "/"):
            handle_administrative_command(raw_query, source, last_result)
            continue

        query_buffer += raw_query
        if multiline:
            semi_pos = query_buffer.find(";")
            if semi_pos != -1:
                query = query_buffer[:semi_pos].strip()
                query_buffer = " "  # Alternatively, support many queries entered at once? # query_buffer[semi_pos + 1:]
                if not query:
                    continue
            else:
                query_buffer += " "
                continue
        else:
            query = query_buffer
            query_buffer = ""
            if not query:
                continue

        if not query.strip(";"):
            continue

        try:
            # Load source
            last_result = None
            table = load_url(
                url=source,
                query=query,
                filter_sql=intermediate_filter_sql,
                schema_coercion=schema_coercion,
                restrict_schema=restrict_schema,
                autocache=autocache,
            )
            last_result = table
            # Dump to destination
            output = table.dump_to_url(url=dest)
            if output:
                print(f"(Wrote out {output})", file=sys.stderr)
            if output and open_dest:
                os_open(output)
        except EmptyDataError:
            print("(0 rows)", file=sys.stderr)
        except InvalidQueryError as exc:
            print(str(exc).strip(), file=sys.stderr)
