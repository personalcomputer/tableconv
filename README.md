# tableconv

"tableconv" is a prototype of a core data plumbing tool that enables complete data portability across 50+ tabular formats. It is conceptually similar to [pandoc](https://pandoc.org/), except for data tables instead of documents.

Its primary usecase is as a quick and dirty CLI ETL tool for converting tabular data from any of 50+ input formats into 50+ output formats (such as CSV, Postgres, XLS, Google Sheets, JSON, etc).

It also supports basic in-line data transformation using SQL and has an interactive mode enabling DB-shell-like interactions even if the underlying data format has no native DB shell client, such as, e.g., CSV files.

The tableconv vision of computing is that all software fundamentally interfaces with data tables, that all APIs can be interpretted as data tables, and that this world needs a generic operating system level client for users to interact with the tables. tableconv is that tool. It is meant to have adapters written to support any/all service and extract or upload data to them to/from generic and portable tabular format.

The tableconv prototype software is slow and memory intensive. It has no streaming support and processes all data locally. It is not suitable for tables over 1 million rows. It also has experimental features that will not work reliably, such as schema management, and special array (1 dimensional table) support. Lastly, as experimental prototype software, all parts of the user interface are expected to be overhauled at some point, and currently no documentation has been written to document the standard options available for each adapter, nor any adapter-specific options.

## Usage

```
usage: __main__.py SOURCE_URL [-q QUERY_SQL] [-o DEST_URL]

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

- odo http://odo.pydata.org/en/latest/
- Singer https://www.singer.io/
- Hive SerDes https://cwiki.apache.org/confluence/display/Hive/SerDe
- ODBC
