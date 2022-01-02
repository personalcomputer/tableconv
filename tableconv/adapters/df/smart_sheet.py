import json
import os

import pandas as pd
import requests

from tableconv.exceptions import InvalidQueryError
from tableconv.uri import parse_uri
from tableconv.adapters.df.base import Adapter, register_adapter


class SmartSheetClient:
    """https://smartsheet-platform.github.io/api-docs/"""
    _BASE_URL = 'https://api.smartsheet.com'

    def __init__(self, auth_token):
        self._auth_token = auth_token

    def _call(self, method, url_part):
        url = self._BASE_URL + url_part
        response = requests.request(method, url, headers={'Authorization': f'Bearer {self._auth_token}'})
        response.raise_for_status()
        return response.json()

    def get_sheet_api_id(self, permalink_id: str):
        sheets = self._call('GET', '/2.0/sheets/')['data']
        for sheet in sheets:
            if sheet['permalink'].endswith(permalink_id):
                return sheet['id']
        raise KeyError(f'Sheet with id {permalink_id} not found out of {len(sheets)} available sheets')

    def get_sheet(self, api_id: int):
        return self._call('GET', f'/2.0/sheets/{api_id}')


@register_adapter(['smartsheet'], read_only=True)
class SmartSheetAdapter(Adapter):

    @staticmethod
    def get_example_url(scheme):
        return f'{scheme}://SHEET_ID'

    @staticmethod
    def _smartsheet_api_data_to_df(data):
        column_names = [column['title'] for column in data['columns']]
        records = []
        for row in data['rows'][1:]:
            record = {}
            for column_name, cell in zip(column_names, row['cells']):
                if 'value' not in cell:
                    continue
                record[column_name] = cell['value']
            records.append(record)
        return pd.DataFrame.from_records(records)

    @staticmethod
    def load(uri, query):
        if query is not None:
            raise InvalidQueryError('Direct smartsheet query language not supported, please use -F instead for '
                                    'in-memory SQL')

        uri = parse_uri(uri)
        permalink_id = uri.authority
        if not permalink_id:
            raise InvalidQueryError('Unable to parse smartsheet id from URL')

        smartsheet_token = json.loads(open(os.path.expanduser('~/.smartsheetcredentials.json')).read())['token']
        smartsheet = SmartSheetClient(smartsheet_token)

        data = smartsheet.get_sheet(smartsheet.get_sheet_api_id(permalink_id))
        return SmartSheetAdapter._smartsheet_api_data_to_df(data)
