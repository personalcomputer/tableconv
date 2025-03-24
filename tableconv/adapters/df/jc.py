import logging
import shlex
import subprocess
import urllib

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.in_memory_query import query_in_memory

logger = logging.getLogger(__name__)


@register_adapter(["jc", "cmd", "sh"], read_only=True)
class JC(Adapter):
    """
    Experimental adapter. Violates the unix philosophy but improves convenience by letting you directly run shell
    commands as a tableconv source, instead of needing to run them, pipe them to jc, and then pipe that json to tc.
    I think in the tableconv end game this Adapter is aligned with how things would work, tableconv would be your only
    interface to the operating system. Although right now this is arguably more of a bad adapter than a good one,
    because it fails to teach/support the intended beginner-level pipe-heavy usage pattern of tableconv.

    See https://github.com/kellyjonbrazil/jc
    """

    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}://ls -l"

    @staticmethod
    def _get_magic_parser(cmd):
        import jc  # inlined for startup performance

        magic_dict = {}
        for entry in jc.all_parser_info():
            magic_dict.update({mc: entry["argument"] for mc in entry.get("magic_commands", [])})
        one_word_command = cmd[0]
        two_word_command = " ".join(cmd[0:2])
        return magic_dict.get(two_word_command, magic_dict.get(one_word_command))

    @staticmethod
    def load(uri, query):
        import jc  # inlined for startup performance

        cmd_str = uri
        for prefix in ["jc://", "jc:", "cmd://", "cmd:", "sh://", "sh:"]:
            if cmd_str.startswith(prefix):
                cmd_str = cmd_str.removeprefix(prefix)
                break
        cmd_str = urllib.parse.unquote(cmd_str)
        cmd = shlex.split(cmd_str)
        parser_name = JC._get_magic_parser(cmd)
        if not parser_name:
            raise ValueError(
                "Not able to guess jc parser. Try using jc manually from the command line instead, and"
                " piping to tableconv. (e.g. `jc ls -l | tableconv json:-`)"
            )

        cmd_output = subprocess.check_output(cmd, text=True)
        data = jc.parse(parser_name, cmd_output)
        df = pd.DataFrame.from_records(data)

        if query:
            df = query_in_memory([("data", df)], query)

        return df
