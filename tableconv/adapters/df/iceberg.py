import logging
import os

from tableconv.adapters.df.base import Adapter, register_adapter
from tableconv.exceptions import InvalidParamsError
from tableconv.uri import parse_uri

logger = logging.getLogger(__name__)


@register_adapter(["iceberg"])
class IcebergAdapter(Adapter):
    @staticmethod
    def get_example_url(scheme):
        return f"{scheme}:///tmp/warehouse?catalog_uri=sqlite:////tmp/warehouse/pyiceberg_catalog.db"

    @staticmethod
    def load_catalog(parsed_uri):
        from pyiceberg.catalog import load_catalog

        if "catalog_uri" not in parsed_uri.query:
            raise InvalidParamsError("?catalog_uri parameter is required")
        catalog_uri = parsed_uri.query["catalog_uri"]
        namespace = parsed_uri.query.get("namespace", "default")
        warehouse_path = parsed_uri.authority or parsed_uri.path
        return load_catalog(
            namespace,
            type="sql",
            uri=catalog_uri,
            warehouse=f"file://{warehouse_path}",
        )

    @staticmethod
    def load(uri, query):
        if query:
            raise InvalidParamsError(
                "Querying is not currently supported for iceberg, no iceberg query engine is available in tableconv. "
                "Use -F instead to load into memory and query with duckdb."
            )
        parsed_uri = parse_uri(uri)

        if "catalog_uri" in parsed_uri.query:
            catalog = IcebergAdapter.load_catalog(parsed_uri)
            table = catalog.load_table(parsed_uri.authority)
        else:
            from pyiceberg.table import StaticTable

            path = os.path.join(parsed_uri.authority, parsed_uri.path.lstrip("/"))
            if path.endswith(".metadata.json"):
                table = StaticTable.from_metadata(path)
            elif os.path.isdir(os.path.join(path, "metadata")):
                metadata_folder = os.path.join(path, "metadata")
                metadata_path = os.path.join(
                    metadata_folder, max(i for i in os.listdir(metadata_folder) if i.endswith(".metadata.json"))
                )
                logger.info(f"Loading table metainfo from {metadata_path}")
                table = StaticTable.from_metadata(metadata_path)
            else:
                raise InvalidParamsError(
                    f"{path} is invalid. Either use a catalog_uri, or pass a direct table .metadata.json file"
                )

        return table.scan().to_pandas()

    @staticmethod
    def dump(df, uri):
        parsed_uri = parse_uri(uri)
        table_name = parsed_uri.query.get("table_name", parsed_uri.query.get("table", None))
        if not table_name:
            raise InvalidParamsError("?table_name parameter is required")
        if_exists = parsed_uri.query.get("if_exists", "error")
        if if_exists not in ("append", "replace", "error"):
            raise InvalidParamsError("?if_exists parameter must be one of: append, replace, error")
        namespace = parsed_uri.query.get("namespace", "default")
        catalog = IcebergAdapter.load_catalog(parsed_uri)
        if namespace not in (i[0] for i in catalog.list_namespaces()):
            catalog.create_namespace(namespace)

        import pyarrow

        df = pyarrow.Table.from_pandas(df)

        exists = table_name in (i[0] for i in catalog.list_tables(namespace))
        if exists:
            table = catalog.load_table(f"{namespace}.{table_name}")
            if if_exists == "error":
                raise InvalidParamsError(f"table {table_name} already exists")
            elif if_exists == "append":
                table.append(df)
            elif if_exists == "replace":
                table.overwrite(df)
        else:

            table = catalog.create_table(
                f"{namespace}.{table_name}",
                schema=df.schema,
            )
            table.append(df)
