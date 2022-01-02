import datetime
import logging
import math
import os
import sys

import numpy as np
import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.exceptions import (AppendSchemeConflictError, InvalidLocationReferenceError, InvalidParamsError,
                                  TableAlreadyExistsError)
from tableconv.uri import parse_uri

logger = logging.getLogger(__name__)


def list_ljust(ls, n, fill_value=None):
    return ls + [fill_value] * (n - len(ls))


def get_sheet_properties(spreadsheet_data, sheet_name):
    for sheet in spreadsheet_data['sheets']:
        if sheet['properties']['title'] == sheet_name:
            return sheet['properties']
    raise KeyError(f'Sheet {sheet_name} not found')


GSHEETS_OAUTH_SECRETS_FILE_PATH = os.path.expanduser('~/.tableconv-gsheets-client-secrets')


@register_adapter(['gsheets'])
class GoogleSheetsAdapter(Adapter):

    @staticmethod
    def get_example_url(scheme):
        return 'gsheets://:new:'

    @staticmethod
    def get_configuration_options_description():
        return {
            'secrets_file': 'Path to JSON file containing Google Sheets OAuth secrets. Generate this file via '
                            'https://console.cloud.google.com/apis/credentials .',
        }

    @staticmethod
    def set_configuration_options(args):
        assert set(args.keys()) == set(GoogleSheetsAdapter.get_configuration_options_description().keys())
        with open(GSHEETS_OAUTH_SECRETS_FILE_PATH, 'w') as f:
            with open(args['secrets_file']) as in_file:
                f.write(in_file.read())
        logger.info(f'Wrote configuration to {GSHEETS_OAUTH_SECRETS_FILE_PATH}')
        GoogleSheetsAdapter._get_oauth_credentials()  # Trigger OAuth flow prompt

    @staticmethod
    def _get_oauth_credentials():
        from oauth2client import client, tools
        from oauth2client.file import Storage

        store = Storage(os.path.expanduser('~/.tableconv-gsheets-credentials'))
        credentials = store.get()
        sys.argv = ['']
        if not credentials or credentials.invalid:
            SCOPES = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive',
            ]
            flow = client.flow_from_clientsecrets(GSHEETS_OAUTH_SECRETS_FILE_PATH, SCOPES)
            flow.user_agent = 'tableconv'
            credentials = tools.run_flow(flow, store)
        return credentials

    @staticmethod
    def _get_googleapiclient_client(service, version):
        import googleapiclient.discovery
        import httplib2

        if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
            # login as a service account via env var
            http = None
        else:
            # login using OAuth
            http = GoogleSheetsAdapter._get_oauth_credentials().authorize(httplib2.Http())

        return googleapiclient.discovery.build(service, version, http=http)

    @staticmethod
    def load(uri, query):
        parsed_uri = parse_uri(uri)
        spreadsheet_id = parsed_uri.authority
        sheet_name = parsed_uri.path.strip('/')

        if not sheet_name:
            raise InvalidLocationReferenceError('Must specify sheet_name')

        googlesheets = GoogleSheetsAdapter._get_googleapiclient_client('sheets', 'v4')

        # Query data
        raw_data = googlesheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'",
        ).execute()

        header = raw_data['values'][0]
        num_columns = len(header)
        values = [list_ljust(row, num_columns) for row in raw_data['values'][1:]]
        return pd.DataFrame(values, columns=header)

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
        request = {
            'addSheet': {
                'properties': {
                    'gridProperties': {'columnCount': columns, 'rowCount': rows},
                    'index': 0,
                    'sheetType': 'GRID',
                    'title': sheet_name,
                }
            }
        }
        response = googlesheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': [request]}
        ).execute()
        return response['replies'][0]['addSheet']['properties']['sheetId']

    @staticmethod
    def _extend_sheet(googlesheets, spreadsheet_id, sheet_id, new_total_rows):
        request = {
            'updateSheetProperties': {
                'properties': {
                    'gridProperties': {'rowCount': new_total_rows},
                    'sheetId': sheet_id,
                },
                'fields': 'gridProperties.rowCount',
            }
        }
        googlesheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': [request]}
        ).execute()

    @staticmethod
    def _serialize_df(df):
        serialized_records = [list(record) for record in df.values]

        df = df.replace({np.nan: None})
        for i, row in enumerate(serialized_records):
            for j, obj in enumerate(row):
                if isinstance(obj, datetime.datetime):
                    if obj.tzinfo is not None:
                        obj = obj.astimezone(datetime.timezone.utc)
                    # WARNING: In effect, this line is causing naive datetimes to be reinterpreted as UTC.
                    serialized_records[i][j] = obj.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(obj, list) or isinstance(obj, dict):
                    serialized_records[i][j] = str(obj)
                elif hasattr(obj, 'dtype'):
                    serialized_records[i][j] = obj.item()
                if isinstance(serialized_records[i][j], float) and math.isnan(serialized_records[i][j]):
                    serialized_records[i][j] = None
        return serialized_records

    @staticmethod
    def dump(df, uri):
        import googleapiclient

        parsed_uri = parse_uri(uri)
        if parsed_uri.authority is None:
            raise InvalidLocationReferenceError('Please specify spreadsheet id or :new: in gsheets uri')
        params = parsed_uri.query

        if 'if_exists' in params:
            if_exists = params['if_exists']
        elif 'append' in params and params['append'].lower() != 'false':
            if_exists = 'append'
        elif 'overwrite' in params and params['overwrite'].lower() != 'false':
            if_exists = 'replace'
        else:
            if_exists = 'fail'

        if parsed_uri.path.strip('/') is not None:
            sheet_name = parsed_uri.path.strip('/')
        else:
            sheet_name = 'Sheet1'

        serialized_records = GoogleSheetsAdapter._serialize_df(df)
        serialized_header = [list(df.columns)]
        googlesheets = GoogleSheetsAdapter._get_googleapiclient_client('sheets', 'v4')

        # Create new spreadsheet, if specified.
        columns = len(df.columns)
        rows = len(df.values)
        new_sheet = None
        start_row = 1
        if parsed_uri.authority == ':new:':
            if if_exists != 'fail':
                raise InvalidParamsError('only if_exists=fail supported for new spreadsheets')
            spreadsheet_name = params.get('name', f'Untitled {datetime.datetime.utcnow().isoformat()[:-7]}')
            spreadsheet_id = GoogleSheetsAdapter._create_spreadsheet(
                googlesheets, spreadsheet_name, sheet_name, columns, rows)
            sheet_id = 0

            permission_domain = os.environ.get('TABLECONV_GSHEETS_DEFAULT_PERMISSION_GRANT_DOMAIN')
            if permission_domain:
                drive_service = GoogleSheetsAdapter._get_googleapiclient_client('drive', 'v3')
                drive_service.permissions().create(
                    fileId=spreadsheet_id,
                    body={'type': 'domain', 'role': 'writer', 'domain': permission_domain},
                ).execute()
            new_sheet = True
        else:
            spreadsheet_id = parsed_uri.authority
            try:
                sheet_id = GoogleSheetsAdapter._add_sheet(
                    googlesheets, spreadsheet_id, sheet_name, columns, rows)
                new_sheet = True
            except googleapiclient.errors.HttpError as exc:
                if f'A sheet with the name "{sheet_name}" already exists' not in str(exc):
                    raise
                if if_exists == 'fail':
                    raise TableAlreadyExistsError(exc.reason) from exc
                new_sheet = False
            if not new_sheet:
                if if_exists == 'replace':
                    # delete it..
                    raise NotImplementedError('Sheet if_exists=replace not implemented yet')
                elif if_exists == 'append':
                    spreadsheet_data = googlesheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                    sheet = get_sheet_properties(spreadsheet_data, sheet_name=sheet_name)
                    existing_rows = sheet['gridProperties']['rowCount']
                    existing_columns = sheet['gridProperties']['columnCount']
                    if existing_columns != columns:
                        raise AppendSchemeConflictError(f'Cannot append to {sheet_name} - columns don\'t match')
                    sheet_id = sheet['sheetId']
                    total_rows = existing_rows + columns
                    GoogleSheetsAdapter._extend_sheet(googlesheets, spreadsheet_id, sheet_id, new_total_rows=total_rows)
                    start_row = existing_rows + 1
                else:
                    raise AssertionError

        # Insert data
        serialized_cells = serialized_records
        if new_sheet:
            serialized_cells = serialized_header + serialized_records
        googlesheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f'{sheet_name}!A{start_row}',
            valueInputOption='RAW',
            body={'values': serialized_cells},
        ).execute()

        # Format
        if new_sheet:
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
        return f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet_id}'
