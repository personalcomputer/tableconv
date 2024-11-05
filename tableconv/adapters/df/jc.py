import logging
import shlex
import subprocess
import urllib

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter

logger = logging.getLogger(__name__)


@register_adapter(["jc", "cmd", "sh"], read_only=True)
class JC(Adapter):
    """
    Experimental adapter. Violates the unix philosophy but improves convenience by letting you directly run shell
    commands as a tableconv source, instead of needing to pipe them to jc and then pipe that json to tableconv. I think
    in the tableconv end game this is how things would work, tableconv would be your only interface to the operating
    system. Although right now this is arguably more of a bad adapter than a good one, because it fails to teach/support
    the intended beginner-level pipe-heavy usage pattern of tableconv.

    See https://github.com/kellyjonbrazil/jc
    """

    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}://ls -l"

    @staticmethod
    def _get_magic_parser(cmd):
        import jc

        magic_dict = {}
        for entry in jc.all_parser_info():
            magic_dict.update({mc: entry["argument"] for mc in entry.get("magic_commands", [])})
        one_word_command = cmd[0]
        two_word_command = " ".join(cmd[0:2])
        return magic_dict.get(two_word_command, magic_dict.get(one_word_command))

    @staticmethod
    def load(uri, query):
        import jc

        cmd_str = urllib.parse.unquote(uri.removeprefix("jc://").removeprefix("jc:"))
        cmd = shlex.split(cmd_str)

        parser_name = JC._get_magic_parser(cmd)
        if not parser_name:
            raise ValueError(
                "Not able to guess jc parser. Try using jc manually from the command line instead, and"
                " piping to tableconv."
            )

        cmd_output = subprocess.check_output(cmd, text=True)
        data = jc.parse(parser_name, cmd_output)

        return pd.DataFrame.from_records(data)
