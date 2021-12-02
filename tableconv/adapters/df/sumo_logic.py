import datetime
import logging
import os
import re
import sys
import time
from typing import Optional, Union
from unittest import mock

import pandas as pd
import yaml
from dateutil.parser import parse as dateutil_parse

from ...uri import parse_uri
from .base import Adapter, register_adapter

logger = logging.getLogger(__name__)

SUMO_API_MAX_RESULTS_PER_API_CALL = 10000
SUMO_API_TS_FORMAT = '%Y-%m-%dT%H:%M:%S'
SUMO_API_RESULTS_POLLING_INTERVAL = datetime.timedelta(seconds=5)
CREDENTIALS_FILE_PATH = os.path.expanduser('~/.sumologiccredentials.yaml')


def utcnow():
    ts = datetime.datetime.utcnow()
    ts = ts.replace(tzinfo=datetime.timezone.utc)
    return ts


def get_sumo_data(search_query: str,
                  search_from: Union[datetime.datetime, datetime.timedelta],
                  search_to: Optional[datetime.datetime] = None,
                  by_receipt_time: bool = False):
    if isinstance(search_from, datetime.timedelta):
        search_from = utcnow() - search_from
    if search_to is None:
        search_to = utcnow() + datetime.timedelta(days=1)

    SUMO_CREDS = yaml.safe_load(open(CREDENTIALS_FILE_PATH))

    from sumologic import \
        SumoLogic  # TODO: This is a low quality library by an inexperienced developer. Replace with a home-spun version

    # As a hack to deal with the low quality code in SumoLogic SDK, we monkeypatch print() so it does not fill up user's
    # terminal with junk debug information.
    with mock.patch('builtins.print'):
        sumo = SumoLogic(SUMO_CREDS['access_id'], SUMO_CREDS['access_key'])

    search_job = sumo.search_job(
        query=search_query + ' | json auto',
        fromTime=search_from.astimezone(datetime.timezone.utc).strftime(SUMO_API_TS_FORMAT),
        toTime=search_to.astimezone(datetime.timezone.utc).strftime(SUMO_API_TS_FORMAT),
        timeZone='UTC',
        byReceiptTime=by_receipt_time,
    )

    logger.info(f'Waiting for query to complete (job id: {search_job["id"]})')
    time.sleep((SUMO_API_RESULTS_POLLING_INTERVAL / 2).total_seconds())
    while True:
        status = sumo.search_job_status(search_job)
        if status['state'] != 'GATHERING RESULTS':
            assert(status['state'] == 'DONE GATHERING RESULTS')
            break
        time.sleep(SUMO_API_RESULTS_POLLING_INTERVAL.total_seconds())

    message_count = status['messageCount']
    logger.info(f'Downloading sumo results (message count: {message_count})')

    raw_results = []
    if message_count > 0:
        offset = 0
        while offset < message_count:
            search_output = sumo.search_job_messages(search_job, limit=SUMO_API_MAX_RESULTS_PER_API_CALL, offset=offset)['messages']
            assert(search_output)
            raw_results.extend((r['map'] for r in search_output))
            offset += len(search_output)
            logger.debug(f'Sumo message download {round(100*offset/message_count)}% complete')
    assert(len(raw_results) == message_count)

    sumo.delete_search_job(search_job)

    return pd.DataFrame.from_records(raw_results)


def parse_input_time(val: str) -> Union[datetime.timedelta, datetime.datetime]:
    hms_match = re.match(r'^\-?(\d\d):(\d\d):(\d\d)$', val)
    if hms_match:
        return datetime.timedelta(seconds=int(hms_match.group(1))*60*60 + int(hms_match.group(2))*60 + int(hms_match.group(3)))  # noqa: E226
    elif re.match(r'-?\d+$', val):
        return datetime.timedelta(seconds=abs(int(val)))
    else:
        dt = dateutil_parse(val)
        if not dt.tzinfo:
            raise ValueError('Must include the timezone when specifying a datetime')
        return dt


@register_adapter(['sumologic'], read_only=True)
class SumoLogicAdapter(Adapter):

    @staticmethod
    def get_configuration_options_description():
        return {
            'access_id': 'SumoLogic Access Key ID (https://service.sumologic.com/ui/#/preferences)',
            'access_key': 'SumoLogic Access Key Key (https://service.sumologic.com/ui/#/preferences)',
        }

    @staticmethod
    def set_configuration_options(args):
        if set(args.keys()) != set(SumoLogicAdapter.get_configuration_options_description().keys()):
            print('Please specify all required options. See --help.')
            sys.exit(1)
        with open(CREDENTIALS_FILE_PATH, 'w') as f:
            f.write(yaml.dump(args))
        logger.info(f'Wrote configuration to "{CREDENTIALS_FILE_PATH}"')

    @staticmethod
    def get_example_url(scheme):
        return f'{scheme}://?from=2021-03-01T00:00:00Z&to=2021-05-03T00:00:00Z'

    @staticmethod
    def load(uri, query):
        parsed_uri = parse_uri(uri)
        params = parsed_uri.query

        # Params:
        # ?from
        #   Specify the lower time range bound for the query. Specify either a timezone-aware datetime in any format, or a relative time in seconds or HH:MM:SS format
        # ?to
        #   Specify the upper time range bound for the query. Specify either a timezone-aware datetime in any format, or a relative time in seconds or HH:MM:SS format. Default: Unlimited
        # ?receipt_time
        #   Use receipt time. Default: False

        if 'from' not in params:
            raise ValueError('?from must be specified. This is the lower time range bound for the query. Specify either a datetime in any format, or a relative time in seconds or HH:MM:SS format')

        from_time = parse_input_time(params['from'])
        if 'to' in params:
            to_time = parse_input_time(params['to'])
        else:
            to_time = None

        df = get_sumo_data(query, search_from=from_time, search_to=to_time, by_receipt_time=params.get('receipt_time', False))

        return df
