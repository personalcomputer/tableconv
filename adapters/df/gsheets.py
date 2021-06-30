import datetime
import math
import os
import sys

import pandas as pd
import numpy as np

from ...uri import parse_uri
from .base import Adapter, register_adapter


@register_adapter(['gsheets'])
class GoogleSheetsAdapter(Adapter):

    @staticmethod
    def get_example_url(scheme):
        return f'gsheets://:new:'

    @staticmethod
    def _get_credentials():
        from oauth2client import client, tools
        from oauth2client.file import Storage

        store = Storage(os.path.expanduser('~/.tableconv-gsheets-credentials'))
        credentials = store.get()
        sys.argv = ['']
        if not credentials or credentials.invalid:
            CLIENT_SECRET_FILE = os.path.expanduser('~/.tableconv-gsheets-client-secrets')
            SCOPES = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive',
            ]
            flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
            flow.user_agent = 'tableconv'
            credentials = tools.run_flow(flow, store)
        return credentials

    @staticmethod
    def load(uri, query):
        import googleapiclient.discovery
        import httplib2

        uri = parse_uri(uri)
        spreadsheet_id = uri.authority
        sheet_name = uri.path.strip('/')

        googlesheets = googleapiclient.discovery.build(
            'sheets', 'v4', http=GoogleSheetsAdapter._get_credentials().authorize(httplib2.Http())
        )

        # Query data
        raw_data = googlesheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'",
        ).execute()

        header = raw_data['values'][0]
        return pd.DataFrame(raw_data['values'][1:], columns=header)

    @staticmethod
    def _create_spreadsheet(googlesheets, spreadsheet_name, first_sheet_name, columns, rows):
        sheet = {
            'properties': {
                'autoRecalc': 'ON_CHANGE',
                'title': spreadsheet_name,
                'locale': 'en_US',
                'timeZone': 'UTC/UTC',
            },
            'sheets': [
                {
                    'properties': {
                        'gridProperties': {'columnCount': columns, 'rowCount': rows},
                        'index': 0,
                        'sheetId': 0,
                        'sheetType': 'GRID',
                        'title': first_sheet_name,
                    }
                }
            ],
        }
        result = googlesheets.spreadsheets().create(body=sheet).execute()
        return result['spreadsheetId']

    @staticmethod
    def _add_sheet(googlesheets, spreadsheet_id, sheet_name, columns, rows):
        requests = [
            {
                'addSheet': {
                    'properties': {
                        'gridProperties': {'columnCount': columns, 'rowCount': rows},
                        'index': 0,
                        'sheetType': 'GRID',
                        'title': sheet_name,
                    }
                }
            },
        ]
        response = googlesheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': requests}
        ).execute()
        return response['replies'][0]['addSheet']['properties']['sheetId']

    @staticmethod
    def _serialize_df(df):
        serialized_records = [list(record) for record in df.values]

        df = df.replace({np.nan: None})
        for i, row in enumerate(serialized_records):
            for j, obj in enumerate(row):
                if isinstance(obj, datetime.datetime):
                    if obj.tzinfo is not None:
                        obj = obj.astimezone(datetime.timezone.utc)
                    # Warning: Interpret naive TS as being UTC.
                    serialized_records[i][j] = obj.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(obj, list) or isinstance(obj, dict):
                    serialized_records[i][j] = str(obj)
                elif hasattr(obj, 'dtype'):
                    serialized_records[i][j] = obj.item()
                if isinstance(serialized_records[i][j], float) and math.isnan(serialized_records[i][j]):
                    serialized_records[i][j] = None
        return [list(df.columns)] + serialized_records

    @staticmethod
    def dump(df, uri):
        import googleapiclient.discovery
        import httplib2

        uri = parse_uri(uri)
        if uri.authority is None:
            raise ValueError('Please specify spreadsheet id or :new: in gsheets uri')

        if uri.path.strip('/') is not None:
            sheet_name = uri.path.strip('/')
        else:
            sheet_name = 'Sheet1'

        serialized_records = GoogleSheetsAdapter._serialize_df(df)
        http_client = GoogleSheetsAdapter._get_credentials().authorize(httplib2.Http())
        googlesheets = googleapiclient.discovery.build(
            'sheets', 'v4', http=http_client
        )

        # Create new spreadsheet, if specified.
        columns = len(df.columns)
        rows = len(df.values)
        if uri.authority == ':new:':
            spreadsheet_name = uri.query.get('name', f'Untitled {datetime.datetime.utcnow().isoformat()[:-7]}')
            spreadsheet_id = GoogleSheetsAdapter._create_spreadsheet(
                googlesheets, spreadsheet_name, sheet_name, columns, rows)
            sheet_id = 0

            permission_domain = os.environ.get('TABLECONV_GSHEETS_DEFAULT_PERMISSION_GRANT_DOMAIN')
            if permission_domain:
                drive_service = googleapiclient.discovery.build(
                    'drive', 'v3', http=http_client
                )
                drive_service.permissions().create(
                    fileId=spreadsheet_id,
                    body={'type': 'domain', 'role': 'writer', 'domain': permission_domain},
                ).execute()
        else:
            spreadsheet_id = uri.authority
            sheet_id = GoogleSheetsAdapter._add_sheet(
                googlesheets, spreadsheet_id, sheet_name, columns, rows)

        # Insert data
        googlesheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f'{sheet_name}!A1',
            valueInputOption='RAW',
            body={'values': serialized_records},
        ).execute()

        # Format
        googlesheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': [
            {'updateSheetProperties': {
                'properties': {
                    'sheetId': sheet_id,
                    'gridProperties': {'frozenRowCount': 1}
                },
                'fields': 'gridProperties.frozenRowCount',
            }},
            {'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'endRowIndex': 1
                },
                'cell': {'userEnteredFormat': {'textFormat': {'bold': True}}},
                'fields': 'userEnteredFormat.textFormat.bold',
            }},
            {'autoResizeDimensions': {
                'dimensions': {
                    'sheetId': sheet_id,
                    'dimension': 'COLUMNS',
                }
            }},
        ]}).execute()
        return f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid=0'
