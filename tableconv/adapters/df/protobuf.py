import io
import json
import logging
import os
import shlex
import subprocess

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.exceptions import InvalidParamsError, SourceParseError
from tableconv.uri import parse_uri

logger = logging.getLogger(__name__)


@register_adapter(["protobuf", "protob", "binpb"], read_only=True)
class ProtobufAdapter(Adapter):
    """
    Very basic wrapper of the https://buf.build/ "buf" CLI utility's protobuf to json translation feature.

    An alternative implementation might be based on wrapping https://github.com/hq6/ProtobufJson/tree/master.
    A 3rd implementation is https://github.com/pawitp/protobuf-decoder, for when the .proto is unavailable.

    In practice to be more useful, this adapter should support decoding concatenated streams of a protobuf message
    (without any formal "repeated" envelope).
    """

    @staticmethod
    def get_example_url(scheme):
        return f"example.{scheme}"

    @classmethod
    def load(cls, uri, query):
        from tableconv.adapters.df import JSONAdapter  # circular import

        try:
            subprocess.run(["buf", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise RuntimeError("`buf` CLI tool not found in PATH. Please install buf from https://buf.build/") from exc

        parsed_uri = parse_uri(uri)
        if "type" not in parsed_uri.query:
            raise InvalidParamsError(
                "?type parameter is required. This needs to be the name of the top-level protobuf message contained in "
                "the file."
            )
        proto_msg_type = parsed_uri.query["type"]
        data_path = os.path.abspath(os.path.expanduser(parsed_uri.path))
        if "proto" in parsed_uri.query:
            proto_path = os.path.abspath(os.path.expanduser(parsed_uri.query["proto"]))
        else:
            proto_path = None

        cmd = ["buf", "convert"]
        if proto_path:
            cmd += [proto_path]
        cmd += [
            f"--from={data_path}",
            f"--type={proto_msg_type}",
            "--to=-#format=json",
        ]
        logger.debug(f"Running {shlex.join(cmd)}")
        try:
            proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            if e.stderr.strip() == "Failure: --from: proto: not found":
                raise InvalidParamsError(
                    f'Type "{proto_msg_type}" not recognized. Tip: You may need to qualify the type with the protobuf '
                    'package name, e.g. "example.Example"'
                ) from e
            raise e

        data = json.loads(proc.stdout)
        type_exception = SourceParseError(
            "Input must be a protobuf message containing only one field: a repeated field."
        )
        if len(data.keys()) == 1:
            array_data = list(data.items())[0][1]
            if not isinstance(array_data, list):
                raise type_exception
        else:
            raise type_exception

        return JSONAdapter.load_file("json", io.StringIO(json.dumps(array_data)), parsed_uri.query)
