import io
import os

import tableconv_daemon.protocol as protocol


def _roundtrip(frame):
    buf = io.BytesIO()
    protocol.write_frame(buf, frame)
    buf.seek(0)
    return protocol.read_frame(buf)


def test_encode_decode_basic_dict():
    assert protocol.decode_frame(protocol.encode_frame({"t": "end", "code": 0})) == {"t": "end", "code": 0}


def test_frame_terminated_by_newline():
    data = protocol.encode_frame({"t": "end", "code": 1})
    assert data.endswith(b"\n")
    assert data.count(b"\n") == 1


def test_write_read_frame_roundtrip():
    assert _roundtrip({"t": "req", "argv": ["csv:-", "-o", "tsv:-"], "cwd": "/x"}) == {
        "t": "req",
        "argv": ["csv:-", "-o", "tsv:-"],
        "cwd": "/x",
    }


def test_read_frame_returns_none_on_eof():
    assert protocol.read_frame(io.BytesIO(b"")) is None


def test_multiple_frames_in_one_stream():
    buf = io.BytesIO()
    protocol.write_frame(buf, {"t": "out", "d": "a"})
    protocol.write_frame(buf, {"t": "out", "d": "b"})
    protocol.write_frame(buf, {"t": "end", "code": 0})
    buf.seek(0)
    assert protocol.read_frame(buf) == {"t": "out", "d": "a"}
    assert protocol.read_frame(buf) == {"t": "out", "d": "b"}
    assert protocol.read_frame(buf) == {"t": "end", "code": 0}
    assert protocol.read_frame(buf) is None


def test_payload_frame_utf8_uses_d():
    frame = protocol.make_payload_frame("out", b"hello\n")
    assert frame == {"t": "out", "d": "hello\n"}
    assert protocol.extract_payload(frame) == b"hello\n"


def test_payload_frame_esc_bytes_uses_d_and_roundtrips():
    # Rich colorized output: ESC (U+001B) is valid UTF-8, so it takes the readable 'd' path.
    payload = b"\x1b[31mhello\x1b[0m\n"
    frame = protocol.make_payload_frame("out", payload)
    assert "d" in frame and "b" not in frame
    assert protocol.extract_payload(frame) == payload


def test_payload_frame_box_drawing_uses_d():
    payload = "┌─┐\n│x│\n└─┘\n".encode()
    frame = protocol.make_payload_frame("out", payload)
    assert "d" in frame
    assert protocol.extract_payload(frame) == payload


def test_payload_frame_invalid_utf8_uses_b_and_roundtrips():
    # Parquet/msgpack-style binary: contains bytes that are not valid UTF-8.
    payload = b"\x80\x81\x82PAR1\x00\xff"
    frame = protocol.make_payload_frame("out", payload)
    assert frame["t"] == "out"
    assert "b" in frame and "d" not in frame
    assert protocol.extract_payload(frame) == payload


def test_payload_frame_nul_byte_uses_d():
    # NUL (U+0000) is valid UTF-8 and must NOT be mistaken for a sentinel.
    payload = b"a\x00b"
    frame = protocol.make_payload_frame("out", payload)
    assert "d" in frame
    assert protocol.extract_payload(frame) == payload


def test_embedded_newline_in_payload_does_not_break_framing():
    payload = b"line1\nline2\nline3"
    buf = io.BytesIO()
    protocol.write_payload_frame(buf, "out", payload)
    protocol.write_frame(buf, {"t": "end", "code": 0})
    buf.seek(0)
    frame = protocol.read_frame(buf)
    assert protocol.extract_payload(frame) == payload
    assert protocol.read_frame(buf) == {"t": "end", "code": 0}
    assert protocol.read_frame(buf) is None


def test_write_frame_fd_roundtrip(tmp_path):
    path = tmp_path / "ctrl"
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        protocol.write_frame_fd(fd, {"t": "end", "code": 42})
    finally:
        os.close(fd)
    with open(str(path), "rb") as f:
        assert protocol.read_frame(f) == {"t": "end", "code": 42}
