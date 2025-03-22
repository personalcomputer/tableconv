import os
import re
from dataclasses import dataclass
from typing import Any

from tableconv.exceptions import InvalidURLSyntaxError


@dataclass
class URI:
    scheme: str
    query: dict[str, Any]
    authority: str | None = None
    path: str = ""
    fragment: str | None = None


def parse_uri(uri_str: str) -> URI:
    m = re.match(
        r"^(?:(?P<scheme>[^:/?#]+):)?"
        r"(?://(?P<authority>[^~/?#]*))?"
        r"(?P<path>[^?#]*)"
        r"(?:\?(?P<query>[^#]*))?"
        r"(?:#(?P<fragment>.*))?",
        uri_str,
    )
    if not m:
        raise InvalidURLSyntaxError(f'Unable to parse URI "{uri_str}"')
    scheme = m.group("scheme")
    authority = m.group("authority")
    if m.group("path") and not scheme and os.path.extsep in m.group("path"):
        scheme = os.path.splitext(m.group("path"))[1][1:]
        # logger.warning(f'Inferring input is a {scheme} from file extension. To specify explicitly, use syntax
        # {scheme}://{path}')
        authority = None
    if not scheme:
        raise InvalidURLSyntaxError(f'Unable to parse URI "{uri_str}" scheme.')
    scheme = scheme.lower()
    query_dict_items = (kv.split("=") for kv in m.group("query").split("&")) if m.group("query") else []
    query = {k.lower(): v for k, v in query_dict_items}
    return URI(
        scheme=scheme,
        query=query,
        authority=authority,
        path=m.group("path"),
        fragment=m.group("fragment"),
    )


def encode_uri(uri: URI) -> str:
    """
    Convert a URI object back to a string representation.

    Roundtrip tests:
    >>> encode_uri(parse_uri("http://example.com/data.csv"))
    'http://example.com/data.csv'
    >>> encode_uri(parse_uri("postgresql://example111:5432/table_5?q=test&page=1&param="))
    'postgresql://example111:5432/table_5?q=test&page=1&param='
    >>> encode_uri(parse_uri("list:///home/user/document.txt"))
    'list:/home/user/document.txt'
    >>> encode_uri(parse_uri("list:~/document.txt"))
    'list:~/document.txt'
    >>> encode_uri(parse_uri("example.csv"))
    'csv:example.csv'
    >>> encode_uri(parse_uri("/example.csv"))
    'csv:/example.csv'
    >>> encode_uri(parse_uri("ascii:-"))
    'ascii:-'
    >>> encode_uri(parse_uri("ascii://-"))
    'ascii://-'
    """
    result = f"{uri.scheme}:" if uri.scheme else ""
    if uri.authority:
        result += "//" + uri.authority
    result += uri.path
    if uri.query:
        query_parts = [f"{k}={v}" for k, v in uri.query.items()]
        result += "?" + "&".join(query_parts)
    if uri.fragment:
        result += f"#{uri.fragment}"
    return result
