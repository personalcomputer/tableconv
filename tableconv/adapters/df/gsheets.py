import copy
import datetime
import logging
import math
import os
import sys

import numpy as np
import pandas as pd

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.exceptions import (
    AppendSchemeConflictError,
    InvalidLocationReferenceError,
    InvalidParamsError,
    TableAlreadyExistsError,
    URLInaccessibleError,
)
from tableconv.uri import encode_uri, parse_uri

logger = logging.getLogger(__name__)


def list_ljust(ls, n, fill_value=None):
    """Extend a list to length n by appending fill_value.
    >>> list_ljust([1, 2, 3], 5, 0)
    [1, 2, 3, 0, 0]
    """
    return ls + [fill_value] * (n - len(ls))


def integer_to_spreadsheet_column_str(i):
    """The spreadsheet column id (A, B, C, ..., Z, AA, AB, ...) for the given column index number.
    >>> integer_to_spreadsheet_column_str(0)
    'A'
    >>> integer_to_spreadsheet_column_str(25)
    'Z'
    >>> integer_to_spreadsheet_column_str(26)
    'AA'
    >>> integer_to_spreadsheet_column_str(50)
    'AY'
    """
    i += 1
    result = ""
    while i > 0:
        i -= 1
        result = chr(i % 26 + ord("A")) + result
        i //= 26
    return result


def coords_to_spreadsheet_cell_str(coord):
    return f"{integer_to_spreadsheet_column_str(coord[1])}{coord[2]}"


def get_sheet_properties(spreadsheet_data, sheet_name):
    for sheet in spreadsheet_data["sheets"]:
        if sheet["properties"]["title"] == sheet_name:
            return sheet["properties"]
    raise KeyError(f"Sheet {sheet_name} not found")


GSHEETS_OAUTH_SECRETS_FILE_PATH = os.path.expanduser("~/.tableconv-gsheets-client-secrets")


@register_adapter(["gsheets"])
class GoogleSheetsAdapter(Adapter):
    @staticmethod
    def get_example_url(scheme):
        return "gsheets://:new:"

    @staticmethod
    def get_configuration_options_description():
        return {
            "secrets_file": "Path to JSON file containing Google Sheets OAuth secrets. Generate this file via "
            "https://console.cloud.google.com/apis/credentials .",
        }

    @staticmethod
    def set_configuration_options(args):
        assert set(args.keys()) == set(GoogleSheetsAdapter.get_configuration_options_description().keys())
        with open(GSHEETS_OAUTH_SECRETS_FILE_PATH, "w") as f:
            with open(args["secrets_file"]) as in_file:
                f.write(in_file.read())
        logger.info(f"Wrote configuration to {GSHEETS_OAUTH_SECRETS_FILE_PATH}")
        GoogleSheetsAdapter._get_oauth_credentials()  # Trigger OAuth flow prompt

    @staticmethod
    def _get_oauth_credentials():
        from oauth2client import client, tools
        from oauth2client.file import Storage

        creds_path = os.path.expanduser("~/.tableconv-gsheets-credentials")
        if not os.path.exists(creds_path) and not os.path.exists(GSHEETS_OAUTH_SECRETS_FILE_PATH):
            raise URLInaccessibleError(
                "gsheets integration requires configuring Google Sheets API authentication credentials. "
                "Please run `tableconv configure gsheets --help` for help."
            )
        store = Storage(creds_path)
        credentials = store.get()
        sys.argv = [""]
        if not credentials or credentials.invalid:
            SCOPES = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            flow = client.flow_from_clientsecrets(GSHEETS_OAUTH_SECRETS_FILE_PATH, SCOPES)
            flow.user_agent = os.environ.get("TABLECONV_GSHEETS_OAUTH_USER_AGENT", "tableconv")
            credentials = tools.run_flow(flow, store)
        return credentials

    @staticmethod
    def _get_googleapiclient_client(service, version):
        import googleapiclient.discovery
        import httplib2

        if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
            # login as a service account via env var
            http = None
        else:
            # login using OAuth
            http = GoogleSheetsAdapter._get_oauth_credentials().authorize(httplib2.Http())

        return googleapiclient.discovery.build(service, version, http=http)

    @staticmethod
    def _get_sheet_names(googlesheets, spreadsheet_id):
        return [
            sheet["properties"]["title"]
            for sheet in googlesheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()["sheets"]
        ]

    @classmethod
    def load(cls, uri, query):
        parsed_uri = parse_uri(uri)
        spreadsheet_id = parsed_uri.authority
        sheet_name = parsed_uri.path.strip("/")

        googlesheets = GoogleSheetsAdapter._get_googleapiclient_client("sheets", "v4")

        if not sheet_name:
            names = GoogleSheetsAdapter._get_sheet_names(googlesheets, spreadsheet_id)
            if len(names) == 1:
                sheet_name = names[0]
            else:
                raise InvalidLocationReferenceError(f"Must specify sheet_name. Available sheets: {', '.join(names)}")

        # Query data
        raw_data = (
            googlesheets.spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range=f"'{sheet_name}'",
            )
            .execute()
        )

        num_columns = max(*[len(r) for r in raw_data["values"]])
        header = list_ljust(raw_data["values"][0], num_columns)
        values = [list_ljust(row, num_columns) for row in raw_data["values"][1:]]
        df = pd.DataFrame(values, columns=header)
        return cls._query_in_memory(df, query)

    @classmethod
    def load_multitable(cls, uri):
        """Experimental feature. Undocumented. Low Quality."""
        parsed_uri = parse_uri(uri)
        spreadsheet_id = parsed_uri.authority
        assert parsed_uri.path.strip("/") == ""
        googlesheets = cls._get_googleapiclient_client("sheets", "v4")
        table_names = cls._get_sheet_names(googlesheets, spreadsheet_id)
        for table_name in table_names:
            table_uri_parsed = copy.copy(parsed_uri)
            table_uri_parsed.path = f"/{table_name}"
            logger.info(f"Loading table {encode_uri(table_uri_parsed)}")
            df = cls.load(encode_uri(table_uri_parsed), query=None)
            yield table_name, df

    @classmethod
    def dump_multitable(cls, df_multitable, uri):
        """Experimental feature. Undocumented. Low Quality."""
        parsed_uri = parse_uri(uri)
        if parsed_uri.authority is None:
            raise InvalidLocationReferenceError("Please specify spreadsheet id or :new: in gsheets uri")
        assert parsed_uri.path.strip("/") == ""
        for table_name, df in df_multitable:
            table_uri_parsed = copy.copy(parsed_uri)
            table_uri_parsed.path = os.path.join("/", table_name)
            logger.info(f"Dumping table {encode_uri(table_uri_parsed)}")
            output = cls.dump(df, encode_uri(table_uri_parsed))
            if parsed_uri.authority == ":new:":
                # Parse new sheet id out of http gui uri (output is not a tableconv uri)  # hacky
                parsed_uri.authority = os.path.split(parse_uri(output).path)[-1]
        return output

    @staticmethod
    def _create_spreadsheet(googlesheets, spreadsheet_name, first_sheet_name, columns, rows):
        sheet = {
            "properties": {
                "autoRecalc": "ON_CHANGE",
                "title": spreadsheet_name,
                "locale": "en_US",
                "timeZone": "UTC/UTC",
            },
            "sheets": [
                {
                    "properties": {
                        "gridProperties": {"columnCount": columns, "rowCount": rows},
                        "index": 0,
                        "sheetId": 0,
                        "sheetType": "GRID",
                        "title": first_sheet_name,
                    }
                }
            ],
        }
        result = googlesheets.spreadsheets().create(body=sheet).execute()
        return result["spreadsheetId"]

    @staticmethod
    def _add_sheet(googlesheets, spreadsheet_id, sheet_name, columns, rows):
        request = {
            "addSheet": {
                "properties": {
                    "gridProperties": {"columnCount": columns, "rowCount": rows + 1},
                    "index": 0,
                    "sheetType": "GRID",
                    "title": sheet_name,
                }
            }
        }
        response = (
            googlesheets.spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": [request]})
            .execute()
        )
        return response["replies"][0]["addSheet"]["properties"]["sheetId"]

    @staticmethod
    def _reshape_sheet(googlesheets, spreadsheet_id, sheet_id, columns, rows):
        request = {
            "updateSheetProperties": {
                "properties": {
                    "gridProperties": {"columnCount": columns, "rowCount": rows + 1},
                    "sheetId": sheet_id,
                },
                "fields": "gridProperties.columnCount,gridProperties.rowCount",
            }
        }
        googlesheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": [request]}).execute()

    @staticmethod
    def _serialize_df_to_array(df):
        serialized_array = [list(value) for value in df.values]

        MAX_CELL_SIZE = 50000
        oversize_cells = []

        df = df.replace({np.nan: None})
        # TODO: This is highly inefficient code. There should be a vectorized way to do these type conversions. It's
        # also an embarrassing parallelizable problem.
        for i, row in enumerate(serialized_array):
            for j, obj in enumerate(row):
                if isinstance(obj, datetime.datetime):
                    if type(obj) == type(pd.NaT):  # noqa: E721
                        # Not A Time. i.e. NULL.
                        serialized_array[i][j] = ""
                    else:
                        if obj.tzinfo is not None:
                            obj = obj.astimezone(datetime.UTC)
                        # Extremely contentious formatting choices here.
                        # We can use a time format that Google Sheets recognizes/parses, but in the process dropping
                        # timezone information, obj.strftime("%Y-%m-%d %H:%M:%S")
                        # Or we can use a format that ghseets cannot recognize, but close to one, better than iso8601:
                        serialized_array[i][j] = obj.strftime("%Y-%m-%d %H:%M:%S %Z")
                elif isinstance(obj, datetime.timedelta):  # noqa: SIM114
                    serialized_array[i][j] = str(obj)
                    # The above is a human readable way of encoding time delta. Extremely contentious though.
                    # For reference, the ways offered by Pandas IO in its JSON module are:
                    #   epoch: Format as a number, units of seconds. equivalent to .total_seconds()
                    #   iso: The fairly obscure ISO8601 "duration" (aka *P*eriod) formatting standard.
                    #        example: "P11DT14H50M12S"
                elif isinstance(obj, list) or isinstance(obj, dict):  # noqa: SIM101
                    serialized_array[i][j] = str(obj)
                elif isinstance(obj, np.ndarray):
                    serialized_array[i][j] = str(obj.tolist())
                elif hasattr(obj, "dtype"):
                    serialized_array[i][j] = obj.item()
                if isinstance(serialized_array[i][j], float) and math.isnan(serialized_array[i][j]):
                    serialized_array[i][j] = None
                if serialized_array[i][j] is pd.NA:
                    serialized_array[i][j] = None
                if isinstance(serialized_array[i][j], str) and len(serialized_array[i][j]) > MAX_CELL_SIZE:
                    serialized_array[i][j] = serialized_array[i][j][:MAX_CELL_SIZE]
                    oversize_cells.append((i, j))
        if oversize_cells:
            if len(oversize_cells) == 1:
                plural = ""
            else:
                plural = "s"
            if len(oversize_cells) <= 5:
                coord_strs = (f"{integer_to_spreadsheet_column_str(coord[0])}{coord[1]}" for coord in oversize_cells)
                example_cells_str = " (" + (", ".join(coord_strs)) + ")"
            elif all(coord[1] == oversize_cells[0][1] for coord in oversize_cells):
                # All oversize cells are from a single column
                example_cells_str = f" (all in column {integer_to_spreadsheet_column_str(oversize_cells[0][1])})"
            else:
                coord_strs = (
                    f"{integer_to_spreadsheet_column_str(coord[0])}{coord[1]}" for coord in oversize_cells[:3]
                )
                example_cells_str = " (Ex: " + (", ".join(coord_strs)) + ", and more)"

            logger.warning(
                f"Truncated {len(oversize_cells)} cell{plural}{example_cells_str} to their first {MAX_CELL_SIZE} "
                + " characters to fit within Google Sheets max cell size limit."
            )
        return serialized_array

    @staticmethod
    def dump(df, uri):
        import googleapiclient

        parsed_uri = parse_uri(uri)
        if parsed_uri.authority is None:
            raise InvalidLocationReferenceError("Please specify spreadsheet id or :new: in gsheets uri")
        params = parsed_uri.query

        if "if_exists" in params:
            if_exists = params["if_exists"]
        elif "append" in params and params["append"].lower() != "false":
            if_exists = "append"
        elif "overwrite" in params and params["overwrite"].lower() != "false":
            if_exists = "replace"
        else:
            if_exists = "fail"

        if parsed_uri.path.strip("/") is not None:
            sheet_name = parsed_uri.path.strip("/")
        else:
            sheet_name = "Sheet1"

        googlesheets = GoogleSheetsAdapter._get_googleapiclient_client("sheets", "v4")

        # Create new spreadsheet, if specified.
        columns = len(df.columns)
        rows = len(df.values)
        new_sheet = None
        reformat = True
        start_row = 1
        if parsed_uri.authority.lower().strip() == ":new:":
            if if_exists != "fail":
                raise InvalidParamsError("only if_exists=fail supported for :new: spreadsheets")
            datetime_formatted = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            spreadsheet_name = params.get("name", f"Untitled {datetime_formatted}")
            spreadsheet_id = GoogleSheetsAdapter._create_spreadsheet(
                googlesheets, spreadsheet_name, sheet_name, columns, rows
            )
            sheet_id = 0

            permission_domain = os.environ.get("TABLECONV_GSHEETS_DEFAULT_PERMISSION_GRANT_DOMAIN")
            if permission_domain:
                drive_service = GoogleSheetsAdapter._get_googleapiclient_client("drive", "v3")
                drive_service.permissions().create(
                    fileId=spreadsheet_id,
                    body={"type": "domain", "role": "writer", "domain": permission_domain},
                ).execute()
            new_sheet = True
        else:
            spreadsheet_id = parsed_uri.authority
            try:
                sheet_id = GoogleSheetsAdapter._add_sheet(googlesheets, spreadsheet_id, sheet_name, columns, rows)
                new_sheet = True
            except googleapiclient.errors.HttpError as exc:
                if f'A sheet with the name "{sheet_name}" already exists' not in str(exc):
                    raise
                if if_exists == "fail":
                    raise TableAlreadyExistsError(exc.reason) from exc
                new_sheet = False
            if not new_sheet:
                spreadsheet_data = googlesheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                sheet = get_sheet_properties(spreadsheet_data, sheet_name=sheet_name)
                sheet_id = sheet["sheetId"]
                if if_exists == "replace":
                    GoogleSheetsAdapter._reshape_sheet(
                        googlesheets, spreadsheet_id, sheet_id, columns=columns, rows=rows
                    )
                    # delete it..
                    # raise NotImplementedError("Sheet if_exists=replace not implemented yet")
                elif if_exists == "append":
                    reformat = False
                    existing_rows_count = sheet["gridProperties"]["rowCount"] - 1
                    existing_columns = (
                        googlesheets.spreadsheets()
                        .values()
                        .get(spreadsheetId=spreadsheet_id, range="1:1")
                        .execute()["values"][0]
                    )
                    duplicate_column_names = len(set(existing_columns)) != len(existing_columns) or len(
                        set(df.columns)
                    ) != len(df.columns)
                    if duplicate_column_names:
                        AppendSchemeConflictError(
                            f"Cannot append to {sheet_name} - cannot calculate append operation when some column "
                            "names are duplicated."
                        )
                    if set(existing_columns) != set(df.columns):
                        missing_remote = list(set(df.columns) - set(existing_columns))
                        missing_local = list(set(existing_columns) - set(df.columns))
                        log_statements = [f"Columns don't match in {sheet_name}. Appending matching columns anyways."]
                        if missing_remote:
                            logger.debug(f"{existing_columns=}")
                            logger.debug(f"{df.columns=}")
                            logger.debug(f"{missing_remote=}")
                            missing_remote_str = "\n".join(
                                f"- {col.encode('unicode_escape').decode()}" for col in missing_remote
                            )
                            log_statements.append(f"New columns to be added to spreadsheet: \n{missing_remote_str}.")
                        if missing_local:
                            missing_local_str = "\n".join(
                                f"- {col.encode('unicode_escape').decode()}" for col in missing_local
                            )
                            log_statements.append(
                                f"Columns to be filled in as blank for new rows: \n{missing_local_str}"
                            )
                        logger.warning("\n".join(log_statements))
                        # reconfigure sheet
                        if missing_remote:
                            columns = len(existing_columns) + len(missing_remote)
                            GoogleSheetsAdapter._reshape_sheet(
                                googlesheets,
                                spreadsheet_id,
                                sheet_id,
                                columns=columns,
                                rows=existing_rows_count,
                            )
                            # inject new headers
                            googlesheets.spreadsheets().values().update(
                                spreadsheetId=spreadsheet_id,
                                range=f"'{sheet_name}'!{integer_to_spreadsheet_column_str(len(existing_columns))}1",
                                valueInputOption="RAW",
                                body={"values": [missing_remote]},
                            ).execute()
                        # add in blank columns
                        for col in missing_local:
                            df[col] = None
                        # re-order columns in local data copy
                        df = df[existing_columns + missing_remote]

                    GoogleSheetsAdapter._reshape_sheet(
                        googlesheets,
                        spreadsheet_id,
                        sheet_id,
                        columns=columns,
                        rows=existing_rows_count + rows,
                    )
                    start_row = existing_rows_count + 1
                else:
                    raise AssertionError

        # Insert data
        logger.debug(f"Serializing {df.shape[0]*df.shape[1]} cells...")
        serialized_cells = GoogleSheetsAdapter._serialize_df_to_array(df)
        if reformat:
            serialized_cells = [list(df.columns)] + serialized_cells
        logger.debug("Uploading data to gsheets...")
        googlesheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A{start_row}",
            valueInputOption="RAW",
            body={"values": serialized_cells},
        ).execute()

        # Format
        logger.debug("Reformatting sheet...")
        if reformat:
            googlesheets.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "requests": [
                        {
                            "updateSheetProperties": {
                                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                                "fields": "gridProperties.frozenRowCount",
                            }
                        },
                        {
                            "repeatCell": {
                                "range": {"sheetId": sheet_id, "endRowIndex": 1},
                                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                                "fields": "userEnteredFormat.textFormat.bold",
                            }
                        },
                        {
                            "autoResizeDimensions": {
                                "dimensions": {
                                    "sheetId": sheet_id,
                                    "dimension": "COLUMNS",
                                }
                            }
                        },
                    ]
                },
            ).execute()
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet_id}"
