import pandas as pd

import logging

from tableconv.uri import parse_uri
from tableconv.adapters.df.base import Adapter, register_adapter


logger = logging.getLogger(__name__)


@register_adapter(['awsdynamodb'], read_only=True)
class AWSDynamoDB(Adapter):
    @staticmethod
    def get_example_url(scheme):
        return f'{scheme}://eu-central-1/example_table'

    @staticmethod
    def load(uri, query):
        import boto3

        uri = parse_uri(uri)
        aws_region = uri.authority
        table_name = uri.path.strip('/')

        dynamodb = boto3.client('dynamodb', region_name=aws_region)

        scan_results = dynamodb.get_paginator('scan').paginate(TableName=table_name)
        raw_array = []

        logger.info('Sequentially querying DynamoDB scan results...')
        for response in scan_results:
            raw_array.extend(response['Items'])

        return pd.DataFrame.from_records(raw_array)
