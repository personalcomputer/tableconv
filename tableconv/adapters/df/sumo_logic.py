import datetime
import json
import logging
import os
import sys
import time
from typing import Any

import pandas as pd
import yaml

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.exceptions import InvalidParamsError
from tableconv.parse_time import parse_input_time
from tableconv.uri import parse_uri

logger = logging.getLogger(__name__)

SUMO_API_MAX_RESULTS_PER_API_CALL = 10000
SUMO_API_TS_FORMAT = "%Y-%m-%dT%H:%M:%S"
SUMO_API_RESULTS_POLLING_INTERVAL = datetime.timedelta(seconds=5)
CREDENTIALS_FILE_PATH = os.path.expanduser("~/.sumologiccredentials.yaml")
SUMOLOGIC_API_RATE_LIMIT_INTERVAL_S = datetime.timedelta(milliseconds=1000 / 4).total_seconds()


class SumoLogicClient:
    """
    Derivative of https://github.com/SumoLogic/sumologic-python-sdk
    """

    def __init__(self, accessId, accessKey):
        import requests  # inlined for startup performance

        self.session = requests.Session()
        self.session.auth = (accessId, accessKey)
        self.session.headers = {"content-type": "application/json", "accept": "application/json"}
        self.endpoint = self._get_endpoint()
        self.last_query_time = None

    def _get_endpoint(self):
        self.endpoint = "https://api.sumologic.com/api"
        self.response = self.session.get("https://api.sumologic.com/api/v1/collectors")  # Dummy call to get endpoint
        endpoint = self.response.url.replace("/v1/collectors", "")  # Sanitize URI and retain domain
        return endpoint + "/v1"

    def request(self, method, sub_url, params=None, data=None):
        time_since_last_query = time.time() - (self.last_query_time or 0)
        if time_since_last_query < SUMOLOGIC_API_RATE_LIMIT_INTERVAL_S:
            time.sleep(SUMOLOGIC_API_RATE_LIMIT_INTERVAL_S - time_since_last_query)
        self.last_query_time = time.time()
        r = self.session.request(method, self.endpoint + sub_url, params=params, json=data)
        if 400 <= r.status_code < 600:
            r.reason = r.text
        r.raise_for_status()
        return r

    def search_job(self, query, from_time=None, to_time=None, time_zone="UTC", by_receipt_time=None):
        data = {
            "query": query,
            "from": from_time.astimezone(datetime.UTC).strftime(SUMO_API_TS_FORMAT),
            "to": to_time.astimezone(datetime.UTC).strftime(SUMO_API_TS_FORMAT),
            "timeZone": time_zone,
            "byReceiptTime": by_receipt_time,
        }
        r = self.request("POST", "/search/jobs", data=data)
        return json.loads(r.text)

    def search_job_status(self, search_job_id):
        r = self.request("GET", f"/search/jobs/{search_job_id}")
        return json.loads(r.text)

    def search_job_messages(self, search_job_id, limit=None, offset=0):
        params = {"limit": limit, "offset": offset}
        r = self.request("GET", f"/search/jobs/{search_job_id}/messages", params)
        return json.loads(r.text)

    def delete_search_job(self, search_job_id):
        return self.request("DELETE", f"/search/jobs/{search_job_id}")


def get_sumo_data(sumo, search_job_id):
    logger.info(f"Waiting for query to complete (job id: {search_job_id})")
    time.sleep((SUMO_API_RESULTS_POLLING_INTERVAL / 2).total_seconds())
    while True:
        status = sumo.search_job_status(search_job_id)
        STATES_THAT_MEAN_QUERY_STILL_IN_PROGRESS = [
            "GATHERING RESULTS",
            "DONE GATHERING HISTOGRAM",
            "GATHERING RESULTS FROM SUBQUERIES",
        ]

        if status["state"] in STATES_THAT_MEAN_QUERY_STILL_IN_PROGRESS:
            time.sleep(SUMO_API_RESULTS_POLLING_INTERVAL.total_seconds())
            continue

        assert status["state"] == "DONE GATHERING RESULTS", status["state"]
        break

    message_count = status["messageCount"]
    logger.info(f"Downloading sumo results (message count: {message_count})")

    raw_results: list[dict[str, Any]] = []
    if message_count > 0:
        offset = 0
        while offset < message_count:
            # Note: Parallelizing this does nothing, it is rate limited serverside on a per-api-key basis. I've already
            # tried.
            search_output = sumo.search_job_messages(
                search_job_id, limit=SUMO_API_MAX_RESULTS_PER_API_CALL, offset=offset
            )["messages"]
            assert search_output
            raw_results.extend(r["map"] for r in search_output)
            offset += len(search_output)
            logger.debug(f"Sumo message download {round(100 * offset / message_count)}% complete")
    assert len(raw_results) == message_count

    sumo.delete_search_job(search_job_id)

    return pd.DataFrame.from_records(raw_results)


def query_sumo(
    sumo: SumoLogicClient,
    search_query: str,
    search_from: datetime.datetime | datetime.timedelta,
    search_to: datetime.datetime | datetime.timedelta | None = None,
    by_receipt_time: bool = False,
):
    if isinstance(search_from, datetime.timedelta):
        search_from = datetime.datetime.now(tz=datetime.UTC) - search_from
    if isinstance(search_to, datetime.timedelta):
        search_to = datetime.datetime.now(tz=datetime.UTC) - search_to
    if search_to is None:
        search_to = datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(days=1)

    search_job = sumo.search_job(
        query=search_query + " | json auto",
        from_time=search_from,
        to_time=search_to,
        time_zone="UTC",
        by_receipt_time=by_receipt_time,
    )
    return search_job["id"]


@register_adapter(["sumologic"], read_only=True)
class SumoLogicAdapter(Adapter):
    @staticmethod
    def get_configuration_options_description():
        return {
            "access_id": "SumoLogic Access Key ID (https://service.sumologic.com/ui/#/preferences)",
            "access_key": "SumoLogic Access Key Key (https://service.sumologic.com/ui/#/preferences)",
        }

    @staticmethod
    def set_configuration_options(args):
        if set(args.keys()) != set(SumoLogicAdapter.get_configuration_options_description().keys()):
            print("Please specify all required options. See --help.")
            sys.exit(1)
        with open(CREDENTIALS_FILE_PATH, "w") as f:
            f.write(yaml.dump(args))
        logger.info(f'Wrote configuration to "{CREDENTIALS_FILE_PATH}"')

    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}://?from=2021-03-01T00:00:00Z&to=2021-05-03T00:00:00Z"

    @staticmethod
    def load(uri, query):
        parsed_uri = parse_uri(uri)
        params = parsed_uri.query

        # Params:
        # ?from
        #   Specify the lower time range bound for the query. Specify either a timezone-aware datetime in any format, or
        #   a relative time in seconds or HH:MM:SS format
        # ?to
        #   Specify the upper time range bound for the query. Specify either a timezone-aware datetime in any format, or
        #   a relative time in seconds or HH:MM:SS format. Default: Unlimited
        # ?receipt_time
        #   Use receipt time. Default: False

        if "from" not in params:
            raise InvalidParamsError(
                "?from must be specified. This is the lower time range bound for the query. Specify either a datetime"
                " in any format, or a relative time in seconds or HH:MM:SS format"
            )

        from_time = parse_input_time(params["from"])
        if "to" in params:
            to_time = parse_input_time(params["to"])
        else:
            to_time = None

        receipt_time = params.get("receipt_time", False)

        SUMO_CREDS = yaml.safe_load(open(CREDENTIALS_FILE_PATH))
        sumo = SumoLogicClient(SUMO_CREDS["access_id"], SUMO_CREDS["access_key"])

        search_job_id = query_sumo(sumo, query, search_from=from_time, search_to=to_time, by_receipt_time=receipt_time)
        df = get_sumo_data(sumo, search_job_id)

        return df
