from dataclasses import dataclass
import os
import re


@dataclass
class URI:
    scheme: str = None
    authority: str = None
    path: str = None
    query: str = None
    fragment: str = None


def parse_uri(uri_str):
    m = re.match(r'^(?:(?P<scheme>[^:/?#]+):)?(?://(?P<authority>[^/?#]*))?(?P<path>[^?#]*)(?:\?(?P<query>[^#]*))?(?:#(?P<fragment>.*))?', uri_str)
    if not m:
        raise ValueError(f'Unable to parse URI {uri_str}')
    uri = URI(**m.groupdict())
    if uri.path and not uri.scheme and os.path.extsep in uri.path:
        uri.scheme = os.path.splitext(uri.path)[1][1:]
        # logger.warning(f'Inferring input is a {uri.scheme} from file extension. To specify explicitly, use syntax {uri.scheme}://{uri.path}')
        uri.authority = None
    query_dict_items = (kv.split('=') for kv in uri.query.split('&')) if uri.query else []
    uri.query = {k.lower(): v for k, v in query_dict_items}
    if uri.scheme:
        uri.scheme = uri.scheme.lower()
    return uri
