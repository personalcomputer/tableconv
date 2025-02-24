import contextlib
import datetime
import logging
import time

import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.exceptions import InvalidQueryError
from tableconv.parse_time import parse_input_time
from tableconv.uri import parse_uri

logger = logging.getLogger(__name__)


@register_adapter(["awslogs"], read_only=True)
class AWSLogs(Adapter):
    """AWS Cloudwatch Logs (Disclaimer: Only supports Logs Insights queries for now)"""

    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}://eu-central-1//aws/lambda/example-function"

    @staticmethod
    def load(uri, query):
        import boto3

        uri = parse_uri(uri)
        aws_region = uri.authority

        from_time = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(days=1)
        to_time = datetime.datetime.now(tz=datetime.UTC)
        if "from" in uri.query:
            from_time = parse_input_time(uri.query["from"])
        if "to" in uri.query:
            to_time = parse_input_time(uri.query["to"])
        client = boto3.client("logs", region_name=aws_region)

        path = uri.path
        if path[0] == "/":
            path = path[1:]

        query_id = client.start_query(
            logGroupName=path,
            startTime=int(from_time.timestamp()),
            endTime=int(to_time.timestamp()),
            queryString=query,
            limit=int(uri.query.get("limit", 1000)),
        )["queryId"]

        try:
            while True:
                results = client.get_query_results(queryId=query_id)
                if results["status"] in ("Failed", "Timeout", "Unknown"):
                    raise InvalidQueryError(f"AWS CloudWatch Logs Insights Query {results['status']}.")
                elif results["status"] == "Complete":
                    raw_array = [{item["field"]: item["value"] for item in row} for row in results["results"]]
                    break
                else:
                    assert results["status"] in ("Running", "Scheduled")
                    POLL_INTERVAL = datetime.timedelta(seconds=2)
                    time.sleep(POLL_INTERVAL.total_seconds())
        except Exception as exc:
            with contextlib.suppress(Exception):
                client.stop_query(query_id)
            raise exc

        return pd.DataFrame.from_records(raw_array)
