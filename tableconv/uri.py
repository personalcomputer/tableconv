import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from tableconv.exceptions import InvalidURLSyntaxError


@dataclass
class URI:
    scheme: str
    query: Dict[str, Any]
    authority: Optional[str] = None
    path: str = ''
    fragment: Optional[str] = None


def parse_uri(uri_str: str) -> URI:
    m = re.match(
        r'^(?:(?P<scheme>[^:/?#]+):)?'
        r'(?://(?P<authority>[^/?#]*))?'
        r'(?P<path>[^?#]*)'
        r'(?:\?(?P<query>[^#]*))?'
        r'(?:#(?P<fragment>.*))?',
        uri_str
    )
    if not m:
        raise InvalidURLSyntaxError(f'Unable to parse URI "{uri_str}"')
    scheme = m.group('scheme')
    authority = m.group('authority')
    if m.group('path') and not scheme and os.path.extsep in m.group('path'):
        scheme = os.path.splitext(m.group('path'))[1][1:]
        # logger.warning(f'Inferring input is a {scheme} from file extension. To specify explicitly, use syntax
        # {scheme}://{path}')
        authority = None
    if not scheme:
        raise InvalidURLSyntaxError(f'Unable to parse URI "{uri_str}" scheme.')
    scheme = scheme.lower()
    query_dict_items = (kv.split('=') for kv in m.group('query').split('&')) if m.group('query') else []
    query = {k.lower(): v for k, v in query_dict_items}
    return URI(
        scheme=scheme,
        query=query,
        authority=authority,
        path=m.group('path'),
        fragment=m.group('fragment'),
    )
