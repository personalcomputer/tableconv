# tableconv

"tableconv" is a prototype of a core data plumbing tool that enables data portability across 50+ data formats (such as CSV, Postgres, XLS, Google Sheets, JSON, etc). It is conceptually similar to [pandoc](https://pandoc.org/), except it operates on data formats instead of text formats. 

As a prototype, it is usable as a quick and dirty CLI ETL tool for converting data between any of the formats, or usable for performing basic bulk data transformations and joins defined in a unified language (SQL) but operating across disparate data in wildly different formats. That is the immediate value proposition of tableconv, but it was created within the mental framework of a larger vision: The tableconv vision of computing is that all software fundamentally interfaces via data tables; that all UIs and APIs can be interpreted as data frames or data tables. Instead of requiring power users to learn interface after interface and build their own bespoke tooling to extract and manipulate the data at scale in each interface, the world needs a highly interoperable operating system level client for power users to directly interact with, join, and manipulate the data with SQL (or similar) using the universal "table" abstraction provided in a consistent UI across each service. Tableconv is that tool. It is meant to have adapters written to support any/all services and data formats.

However, right now this is just a prototype. The software is slow and memory intensive. It has no streaming support and loads all data into memory before converting it. It is not suitable for tables over 1 million rows. Schemas can migrate inconsistently depending upon the data available. It has experimental features that will not work reliably, such as schema management, the unorthodox URL scheme, and special array (1 dimensional table) support. All parts of the user interface are expected to be overhauled at some point. The code quality is mediocre and inconsistent. Most obscure adapter options are untested. It has an incomplete story on how to use it outside the CLI in other software, as a library. It has no story or documentation for service authentication, aside from SQL DBs. Lastly, the documentation is weak and _no_ documentation has been written to document the standard options available for each adapter, nor any adapter-specific options.

## Usage

```
usage: tableconv SOURCE_URL [-q QUERY_SQL] [-o DEST_URL]

positional arguments:
  SOURCE_URL            Specify the data source URL.

optional arguments:
  -h, --help            show this help message and exit
  -q SOURCE_QUERY, --query SOURCE_QUERY
                        Query to run on the source. Even for non-SQL datasources (e.g. csv or json), SQL querying is still supported, try `SELECT * FROM data`.
  -F INTERMEDIATE_FILTER_SQL, --filter INTERMEDIATE_FILTER_SQL
                        Filter (aka transform) the input data using a SQL query operating on the dataset in memory using DuckDB SQL.
  -o DEST_URL, --dest DEST_URL, --out DEST_URL
                        Specify the data destination URL. If this destination already exists, be aware that the default behavior is to overwrite.
  -i, --interactive     Enter interactive REPL query mode
  --open                Open resulting file/url (not supported for all destination types)
  -v, --verbose, --debug
                        Show debug details, including all API calls.
  --quiet               Only display errors.

supported url schemes:
- ascii:- (dest only)
- asciibox:- (dest only)
- asciifancygrid:- (dest only)
- asciigrid:- (dest only)
- asciilite:- (dest only)
- asciipipe:- (dest only)
- asciiplain:- (dest only)
- asciipresto:- (dest only)
- asciipretty:- (dest only)
- asciipsql:- (dest only)
- asciisimple:- (dest only)
- awsathena://eu-central-1 
- awsdynamodb://eu-central-1/example_table (source only)
- csa:- 
- example.csv 
- example.dta 
- example.feather 
- example.h5 
- example.hdf5 
- example.json 
- example.jsonl 
- example.orc (source only)
- example.parquet 
- example.py 
- example.python 
- example.tsv 
- example.xls 
- example.xlsx 
- example.yaml 
- gsheets://:new: 
- html:- (dest only)
- jiracloud://mycorpname (source only)
- jsonarray:- 
- latex:- (dest only)
- list:- 
- markdown:- (dest only)
- md:- (dest only)
- mediawikiformat:- (dest only)
- moinmoinformat:- (dest only)
- mssql://127.0.0.1:5432/example_db 
- mysql://127.0.0.1:5432/example_db 
- oracle://127.0.0.1:5432/example_db 
- postgis://127.0.0.1:5432/example_db 
- postgres://127.0.0.1:5432/example_db 
- postgresql://127.0.0.1:5432/example_db 
- pylist:- 
- rst:- (dest only)
- smartsheet://SHEET_ID (source only)
- sqlite3://127.0.0.1:5432/example_db 
- sqlite://127.0.0.1:5432/example_db 
- sumologic://?from=2021-03-01T00:00:00Z&to=2021-05-03T00:00:00Z (source only)
- tex:- (dest only)
- yamlsequence:-
```

## Prior Art

Most influential:
- odo
  - Really novel tool that takes native format conversion tools from many different libraries and provides a unified interface for them. Wherever possible it tries to use native code to convert directly from your src to dest, but if there is no direct converter it uses an intermediate format (actually can use any number of chained intermediate formats, that it dynamically calculates. It has no prefered internal intermediate format).   - http://odo.pydata.org/en/latest/
- Singer
  - OSS "open-core" spinoff from the Stich ETL platform (managed). This is not so much a tool itself as it is just a spec for a JSON-based intermediate format that has spawned some ~100 tools written in different languages that can import and export to the intermediate format. https://www.singer.io/
- ODBC/JDBC
  - 1980s/90s successful standard API for database drivers. Widely embraced by database developers. https://en.wikipedia.org/wiki/Open_Database_Connectivity.
- osquery https://github.com/osquery/osquery
  - Very popular tool that exposing os-level information such as process status in a SQL interface. Used in sysadmin automation. Exposed as a Thrift API, with sdks in many languages.
- Spark http://spark.apache.org/docs/latest/sql-data-sources.html
  - Created concept of "RDDs", providing an abstract dataframe-based query interface to an arbitrary distributed backend datastore. Wrapped by spark-SQL to make this a SQL interface. Excellent distributed performance on a cluster.

Less influential, but notable:
- pandas io
  - The sub-components of pandas that deal with exporting/importing data formats. This actually is the core of tableconv's current POC implementation.
- https://github.com/betodealmeida/shillelagh
  - Small project to provide a SQL interface to arbitrary "virtual databases" (read adapters).
- https://github.com/kellyjonbrazil/jc
  - CLI tool to convert text output of common unix commands into structured format (json)
- https://github.com/personalcomputer/sql_api_framework_poc
  - Weak POC exploring SQL's flexibility as a general-purpose network query language. Alternative to the current trend of using REST and GraphQL as general purpose network query languages (see e.g. PostgREST).
- https://github.com/personalcomputer/sql_api_framework_poc
  - Demonstration of SQL<->JSON interchangeability.
- https://github.com/johnkerl/miller
  - Data file query tool. Implements a custom query language.
- https://github.com/BurntSushi/xsv
  - Comprehensive CSV query tool. Implements a custom query language.
- https://github.com/tstack/lnav
  - Inspiration for adding misc log formats support and the regex adapter
