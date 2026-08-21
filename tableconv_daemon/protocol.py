"""JSON Lines framing protocol for the tableconv daemon IPC.

One JSON object per line; the trailing ``b'\\n'`` is the frame boundary. JSON string
escaping handles embedded newlines (and any other control bytes) in payload data, so
framing stays unambiguous without base64-for-everything or sentinel bytes. See
``ARCHITECTURE_DAEMON_REFACTOR.md`` §3.1.

Frame types::

    req   {"t":"req","argv":[...],"cwd":"...","env":{...},"tty":{...}}   client -> worker
    in    {"t":"in","d":"..."} | {"t":"in","b":"<base64>"}               client -> worker (stdin relay; optional)
    abort {"t":"abort"}                                                  client/supervisor -> worker
    out   {"t":"out","d":"..."} | {"t":"out","b":"<base64>"}             worker -> client, stdout chunk
    err   {"t":"err","d":"..."} | {"t":"err","b":"<base64>"}             worker -> client, stderr chunk
    end   {"t":"end","code":<int>}                                       worker -> client, terminates a response

``"d"`` carries a UTF-8 string payload (the common, human-readable case, including all
rich colorized output -- ESC is U+001B and round-trips through JSON as ``\\u001b``).
``"b"`` carries a base64-encoded payload for the rare case where the bytes are not valid
UTF-8 (e.g. binary output formats like parquet/msgpack/avro). Encoder and decoder live
together in this single module (TODO #2a).
"""

import base64
import json
import os
from typing import Any

# Terminal-related environment keys forwarded from client -> worker (see §3.8). Defined
# here so the client (which builds the req frame) and the worker (which applies it) agree.
TERMINAL_ENV_KEYS: tuple[str, ...] = ("COLUMNS", "TERM", "COLORTERM", "NO_COLOR", "FORCE_COLOR")


def encode_frame(frame: dict[str, Any]) -> bytes:
    """Serialize one frame to its on-wire bytes: compact JSON + b'\\n'."""
    return (json.dumps(frame, separators=(",", ":")) + "\n").encode("utf-8")


def decode_frame(line: bytes) -> dict[str, Any]:
    """Parse one frame line (the trailing b'\\n' is tolerated by json.loads)."""
    return json.loads(line.decode("utf-8"))


def write_frame(stream, frame: dict[str, Any]) -> None:
    """Write one frame to a binary file-like (with .write/.flush), e.g. io.BytesIO or a socket makefile."""
    stream.write(encode_frame(frame))
    stream.flush()


def write_frame_fd(fd: int, frame: dict[str, Any]) -> None:
    """Write one frame to a raw file descriptor, retrying short writes."""
    data = encode_frame(frame)
    while data:
        n = os.write(fd, data)
        data = data[n:]


def read_frame(reader) -> dict[str, Any] | None:
    """Read one frame from a binary file-like with .readline(); return None on EOF."""
    line = reader.readline()
    if not line:
        return None
    return decode_frame(line)


def make_payload_frame(type_: str, payload: bytes) -> dict[str, Any]:
    """Build an out/err/in payload frame, auto-selecting 'd' (utf-8) or 'b' (base64)."""
    try:
        return {"t": type_, "d": payload.decode("utf-8")}
    except UnicodeDecodeError:
        return {"t": type_, "b": base64.b64encode(payload).decode("ascii")}


def extract_payload(frame: dict[str, Any]) -> bytes:
    """Inverse of make_payload_frame: return the raw payload bytes."""
    if "d" in frame:
        return frame["d"].encode("utf-8", errors="surrogateescape")
    return base64.b64decode(frame["b"])


def write_payload_frame(stream, type_: str, payload: bytes) -> None:
    """Convenience: write a payload frame to a binary file-like."""
    write_frame(stream, make_payload_frame(type_, payload))


def read_payload_from_frame(frame: dict[str, Any]) -> bytes:
    """Convenience: alias for extract_payload."""
    return extract_payload(frame)
