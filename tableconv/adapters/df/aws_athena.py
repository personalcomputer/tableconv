import datetime
import logging
import os
import tempfile
import textwrap
import time
import uuid

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.adapters.df.pandas_io import CSVAdapter, ParquetAdapter
from tableconv.exceptions import (AppendSchemeConflictError, InvalidParamsError, InvalidQueryError,
                                  TableAlreadyExistsError)
from tableconv.uri import parse_uri

logger = logging.getLogger(__name__)


FORMAT_SQL_MAPPING = {
    'parquet': textwrap.dedent(
        '''
        ROW FORMAT SERDE
          'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe'
        STORED AS INPUTFORMAT
          'org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat'
        OUTPUTFORMAT
          'org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat'
        '''),
    'csv': textwrap.dedent(
        '''
        ROW FORMAT DELIMITED
          FIELDS TERMINATED BY ','
        STORED AS INPUTFORMAT
          'org.apache.hadoop.mapred.TextInputFormat'
        OUTPUTFORMAT
          'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
        ''')
}


@register_adapter(['awsathena'])
class AWSAthenaAdapter(Adapter):
    @staticmethod
    def get_example_url(scheme):
        return f'{scheme}://eu-central-1'

    @staticmethod
    def load(uri, query):
        uri = parse_uri(uri)
        aws_region = uri.authority

        return AWSAthenaAdapter._run_athena_query(
            query=query,
            aws_region=aws_region,
            catalog='AwsDataCatalog',
            database=None,
            return_results_df=True
        )

    @staticmethod
    def _run_athena_query(
            query, aws_region, catalog, database, return_results_raw=False, return_results_df=False,
            athena_client=None):
        import boto3
        if not athena_client:
            athena_client = boto3.client('athena', region_name=aws_region)
        sts = boto3.client('sts', region_name=aws_region)
        s3 = boto3.client('s3', region_name=aws_region)

        aws_account_id = sts.get_caller_identity()['Account']
        output_s3_bucket = f'aws-athena-query-results-{aws_account_id}-{aws_region}'

        logger.debug(f'Querying.. aws_region={aws_region}, catalog={catalog}, output_s3_bucket={output_s3_bucket}')
        query_execution_context = {'Catalog': catalog}
        if database:
            query_execution_context['Database'] = database
        query_req_resp = athena_client.start_query_execution(
            QueryString=query,
            QueryExecutionContext=query_execution_context,
            WorkGroup='primary',
            ResultConfiguration={
                'OutputLocation': f's3://{output_s3_bucket}/'
            },
        )
        query_execution_id = query_req_resp['QueryExecutionId']
        logger.info(f'Waiting for AWS Athena query {query_execution_id}...')

        while True:
            details = athena_client.get_query_execution(QueryExecutionId=query_execution_id)
            status = details['QueryExecution']['Status']['State']
            if status in ('FAILED', 'CANCELLED'):
                error_message = details['QueryExecution']['Status'].get('StateChangeReason')
                raise InvalidQueryError(f'AWS Athena Query {status.lower()}: {error_message}')
            elif status == 'SUCCEEDED':
                break
            else:
                POLL_INTERVAL = datetime.timedelta(seconds=2)
                time.sleep(POLL_INTERVAL.total_seconds())

        if return_results_raw:
            response = athena_client.get_query_results(
                QueryExecutionId=query_execution_id
            )
            return response['ResultSet']
        if return_results_df:
            output_s3_key = f'{query_execution_id}.csv'
            local_filename = f'/tmp/awsathena-{query_execution_id}.csv'
            try:
                s3.download_file(output_s3_bucket, output_s3_key, local_filename)
                df = CSVAdapter.load(f'csv://{local_filename}', None)
            finally:
                try:
                    os.remove(local_filename)
                except FileNotFoundError:
                    pass
            return df

    @staticmethod
    def _get_json_schema(df):
        """
        TODO: Update aws_athena to not be a df-level adapter, and instead use IntermediateExchangeTable, so we don't
        have to duplicate this logic.
        """
        from genson import SchemaBuilder
        builder = SchemaBuilder()
        builder.add_schema({'type': 'object', 'properties': {}})
        for row in df.to_dict(orient='records'):
            builder.add_object(row)
        return builder.to_schema()

    @staticmethod
    def resolve_presto_type(json_schema, column_name=None, top_level=False):
        presto_types = set()
        if 'type' in json_schema:
            if isinstance(json_schema['type'], str):
                json_types = {json_schema['type']}
            else:
                assert(isinstance(json_schema['type'], list))
                json_types = json_schema['type']
            for json_type in json_types:
                if json_type == 'array':
                    if 'items' in json_schema:
                        array_type = AWSAthenaAdapter.resolve_presto_type(json_schema['items'])
                    else:
                        array_type = 'string'
                    presto_types.add(f'array<{array_type}>')
                elif json_type == 'null':
                    pass
                else:
                    presto_types.add({
                        'integer': 'bigint',
                        'string': 'string',
                        'boolean': 'boolean',
                        'number': 'double',
                        'object': 'string',
                    }[json_type])
        else:
            assert('anyOf' in json_schema)
            for sub_definition in json_schema['anyOf']:
                presto_types.add(AWSAthenaAdapter.resolve_presto_type(sub_definition))
        if 'null' in presto_types and presto_types != {'null'}:
            presto_types.remove('null')
        if 'double' in presto_types and presto_types != {'double'}:
            # hide NaN corruption added by pandas
            presto_types.remove('double')
        if len(presto_types) > 1:
            if top_level:
                logger.warning(f'Identified multiple conflicting types for {column_name}: {presto_types}. Picking one '
                               'arbitrarily.')
            presto_types = {presto_types.pop()}
        if len(presto_types) == 0:
            if top_level:
                logger.warning(f'Unable to identify type of column {column_name}. Picking string.')
            presto_types = {'string'}
        return presto_types.pop()

    @staticmethod
    def _gen_schema(df, data_format, table_name, s3_base_url):
        schema = f'CREATE EXTERNAL TABLE `{table_name}` (\n'
        field_schema_lines = []
        columns = []
        for column, json_schema in AWSAthenaAdapter._get_json_schema(df)['properties'].items():
            presto_type = AWSAthenaAdapter.resolve_presto_type(json_schema, column_name=column, top_level=True)
            field_schema_lines.append(f'  `{column}` {presto_type}')
            columns.append(column)
        schema += ',\n'.join(field_schema_lines)
        schema += '\n)'
        schema += FORMAT_SQL_MAPPING[data_format]
        schema += f'LOCATION\n  \'{s3_base_url}\''
        return schema, columns

    @staticmethod
    def dump(df, uri):
        import boto3
        uri = parse_uri(uri)
        if 'if_exists' in uri.query:
            if_exists = uri.query['if_exists']
        elif 'append' in uri.query and uri.query['append'].lower() != 'false':
            if_exists = 'append'
        elif 'overwrite' in uri.query and uri.query['overwrite'].lower() != 'false':
            if_exists = 'replace'
        else:
            if_exists = 'fail'

        if if_exists not in ('replace', 'append', 'fail'):
            raise InvalidParamsError('valid values for if_exists are replace, append, or fail (default)')

        aws_region = uri.authority

        athena_client = boto3.client('athena', region_name=aws_region)
        catalog = 'AwsDataCatalog'
        database = uri.path.strip('/')
        table_name = uri.query['table']

        s3_bucket_path = uri.query['s3_bucket_path']
        s3_bucket_path_split = os.path.split(s3_bucket_path)
        if s3_bucket_path_split[0]:
            s3_bucket = s3_bucket_path_split[0]
            s3_bucket_prefix = os.path.join(s3_bucket_path_split[1], table_name)
        else:
            s3_bucket = s3_bucket_path_split[1]
            s3_bucket_prefix = table_name
        data_format = uri.query['data_format']
        if data_format not in FORMAT_SQL_MAPPING:
            raise InvalidParamsError(f'Only formats {FORMAT_SQL_MAPPING.keys()} supported')
        s3_base_url = f's3://{os.path.join(s3_bucket, s3_bucket_prefix)}'

        with tempfile.TemporaryDirectory() as temp_dir:
            # Dump to temp file on  disk
            filename = f'{uuid.uuid4()}.{data_format}'
            temp_file_path = os.path.join(temp_dir, filename)
            if data_format == 'csv':
                CSVAdapter.dump(df, uri=temp_file_path)
            elif data_format == 'parquet':
                ParquetAdapter.dump(df, uri=temp_file_path)
            else:
                raise AssertionError

            # Manage Table DDL
            schema_ddl, columns = AWSAthenaAdapter._gen_schema(df, data_format, table_name, s3_base_url)

            try:
                table_metadata = athena_client.get_table_metadata(
                    CatalogName=catalog, DatabaseName=database, TableName=table_name)
                table_exists = True
            except athena_client.exceptions.MetadataException as exc:
                if 'EntityNotFoundException' in exc.response['Error']['Message']:
                    table_exists = False
                else:
                    raise
            if table_exists:
                if if_exists == 'fail':
                    raise TableAlreadyExistsError(f'{database}{table_name} already exists')
                elif if_exists == 'append':
                    pre_existing_columns = [col['Name'] for col in table_metadata['TableMetadata']['Columns']]
                    if not pre_existing_columns == columns:
                        raise AppendSchemeConflictError('Cannot append to existing table - schema mismatch')
                    pre_existing_s3_base_url = table_metadata['TableMetadata']['Parameters']['location'].strip('/')
                    if pre_existing_s3_base_url != s3_base_url.strip('/'):
                        existing_uri = parse_uri(pre_existing_s3_base_url)
                        existing_bucket = existing_uri.authority
                        existing_prefix = existing_uri.path.strip('/')
                        if existing_bucket != s3_bucket:
                            raise AppendSchemeConflictError('Cannot append to existing table - s3 bucket mismatch '
                                                            f'(pre-existing location is {pre_existing_s3_base_url})')
                        if existing_prefix.startswith(s3_bucket_prefix):
                            # Discovered prefix is more restrictive than our requested prefix - this is safe, we can
                            # just adopt it.
                            logger.warning(f'Appending to found pre-existing prefix at {existing_prefix}')
                            s3_bucket_prefix = existing_prefix
                            s3_base_url = f's3://{os.path.join(s3_bucket, s3_bucket_prefix)}'
                            schema_ddl = None  # Invalidate the now-outdated schema
                elif if_exists == 'replace':
                    s3_bucket_prefix = os.path.join(s3_bucket_prefix, str(uuid.uuid4()))
                    s3_base_url = f's3://{os.path.join(s3_bucket, s3_bucket_prefix)}'
                    schema_ddl, _ = AWSAthenaAdapter._gen_schema(df, data_format, table_name, s3_base_url)
                    logger.warning(
                        f'Deleting table definition for {database}.{table_name}. Leaving old data behind and changing '
                        'prefix to {s3_bucket_prefix}/.')
                    assert s3_base_url and schema_ddl and s3_bucket_prefix  # safety check
                    # time.sleep(5)  # give user time to abort if running from CLI
                    old_table_schema_query_result = AWSAthenaAdapter._run_athena_query(
                        query=f'SHOW CREATE TABLE `{table_name}`', return_results_raw=True,
                        aws_region=aws_region, catalog='AwsDataCatalog', database=database, athena_client=athena_client
                    )
                    old_table_schema = '\n'.join([x['Data'][0]['VarCharValue']
                                                 for x in old_table_schema_query_result['Rows']])
                    logger.debug('Backup of old table schema before deleting:\n'
                                 + textwrap.indent(old_table_schema, '  '))
                    AWSAthenaAdapter._run_athena_query(
                        query=f'DROP TABLE `{table_name}`',
                        aws_region=aws_region, catalog='AwsDataCatalog', database=database, athena_client=athena_client
                    )
                    # It's just too dangerous to actually delete any data; commented out.
                    # s3 = boto3.resource('s3')
                    # bucket = s3.Bucket(s3_bucket)
                    # bucket.objects.filter(Prefix=f'{s3_bucket_prefix}/').delete()
                    table_exists = False
                else:
                    raise AssertionError
            if not table_exists:
                logger.info(f'Creating new table {database}.{table_name} in {aws_region}')
                logger.debug('\n' + textwrap.indent(schema_ddl, '  '))
                AWSAthenaAdapter._run_athena_query(
                    query=schema_ddl, return_results_raw=True,
                    aws_region=aws_region, catalog='AwsDataCatalog', database=database, athena_client=athena_client
                )

            # Upload temp file to s3
            s3_client = boto3.client('s3')
            s3_object_key = os.path.join(s3_bucket_prefix, filename)
            logger.info(f'Uploading data to s3://{os.path.join(s3_bucket, s3_object_key)}')
            s3_client.upload_file(temp_file_path, s3_bucket, s3_object_key)
