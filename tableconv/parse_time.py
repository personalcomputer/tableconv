import datetime
import re

from dateutil.parser import parse as dateutil_parse


def parse_input_time(val: str) -> datetime.timedelta | datetime.datetime:
    hms_match = re.match(r"^\-?(\d\d):(\d\d):(\d\d)$", val)
    if hms_match:
        seconds = (
            int(hms_match.group(1)) * 60 * 60 + int(hms_match.group(2)) * 60 + int(hms_match.group(3))
        )  # noqa: E226
        return datetime.timedelta(seconds=seconds)
    elif re.match(r"-?\d+$", val):
        return datetime.timedelta(seconds=abs(int(val)))
    else:
        dt = dateutil_parse(val)
        if not dt.tzinfo:
            raise ValueError("Must include the timezone when specifying a datetime")
        return dt
