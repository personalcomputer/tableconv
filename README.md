# tableconv

tableconv is a prototype of software to convert tabular data from any format to any format.

## Install

```sh
uv tool install tableconv
```
(or: `pip install tableconv`)

## Examples

Convert JSON to CSV
```sh
tableconv test.json -o test.csv
```

Convert CSV to JSON
```sh
tableconv test.csv -o test.json
```

Dump a Postgres table as JSON
```sh
tableconv postgresql://192.168.0.10:5432/test_db/my_table -o my_table.json
```

Display a parquet file's data in a human-readable format
```sh
tableconv test.parquet -o ascii:-
```

Convert CSV to a Markdown Table
```sh
tableconv test.csv -o md:-
```

Dump the first 100 rows of a postgres table as JSON
```sh
tableconv postgresql://192.168.0.10:5432/test_db -q 'SELECT * FROM my_table ORDER BY id LIMIT 100' -o my_table.json
```

Copy a few columns from one CSV into a new CSV.
(in general, all functionality works on all of the supported data formats. So you can of course query with SQL on an Oracle database but it's also supported to query with SQL on JSON, SQL on Excel, and, here SQL on CSV)
```sh
tableconv test.csv -q 'SELECT time, name FROM data ORDER BY time DESC' -o output.csv
```

Append a few columns from a CSV into MySQL
```sh
tableconv test.csv -q 'SELECT time, name FROM data ORDER BY time DESC' -o mysql://localhost:3306/test_db/my_table?if_exists=append
```

Extract a report from a SQLite database into a new Google Spreadsheet
```sh
tableconv sqlite3://my_db.db -q 'SELECT name, COUNT(*) from occurrences ORDER BY 2 DESC LIMIT 10' -o "gsheets://:new:/?name=top_occurrences_$(date +'%Y_%m_%d')"
```

## Details

Tableconv is a user interface prototype, not a new data transformation engine. The heavy lifting is credit primarily to **pandas**'s io module and **DuckDB**'s SQL engine. All the other disparate formats are mostly each implemented by specialized third party libraries (refer to the pyproject.toml for a complete list). Tableconv has just glued them all together behind a single common CLI interface to enable high-productivity by allowing you to learn one conversion UI once and not need to research and learn a new data model, a new query language, and a new tool suite every time you encounter an unfamiliar format and need to process it quickly.

## TODO

- Comprehensive online & built-in documentation of all the parameters supported by each format adapter
- Further explore the experimental vision of computing where _all_ services are wrangled to be tables. RESTful tables as the metaphor for 100% of computer interactions. No app switching. All interactions represented as tabular data operations. You want to read your email? `tc email -Q 'where read=False order by date desc limit 10'`. You want to respond? `echo addr,body\nexample@exampl.org,Thanks for the email!' | tc csv:- -o email`
- Create a consistent configuration and service authentication story.
- Fix parameters to all be made consistent in behavior/naming/etc across adapters.


## Additional Feature Documentation

### Interactive Mode
Launch an interactive SQL shell to inspect data from a CSV file in the terminal
```sh
tableconv test.csv -i
```

### Arrays

Arrays can be thought of as one dimensional tables, so tableconv has strong support for array formats too. Here
is an example of converting a copy/pasted newline-deliminated list into a list in the Python list syntax.
```sh
pbpaste | tableconv list:- -o pylist:-
```

Or in YAML's sequence syntax:
```sh
pbpaste | tableconv list:- -o yamlsequence:-
```

Or as a full single-dimensional CSV table:
```sh
pbpaste | tableconv list:- -o csv:-
```

## Influences
- odo
- Singer
- ODBC/JDBC
- osquery
- pandas
- duckdb


## Usage

```
usage: tableconv SOURCE_URL [-q QUERY_SQL] [-o DEST_URL]

positional arguments:
  SOURCE_URL            Specify the data source URL.

options:
  -h, --help            show this help message and exit
  -q, -Q, --query SOURCE_QUERY
                        Query to run on the source. Even for non-SQL datasources (e.g. csv or
                        json), SQL querying is still supported, try `SELECT * FROM data`.
  -F, --filter INTERMEDIATE_FILTER_SQL
                        Filter (i.e. transform) the input data using a SQL query operating on the
                        dataset in memory using DuckDB SQL.
  -o, --dest, --out, --output DEST_URL
                        Specify the data destination URL. If this destination already exists, be
                        aware that the default behavior is to overwrite.
  -i, --interactive     Enter interactive REPL query mode.
  --open                Open resulting file/url in the operating system desktop environment. (not
                        supported for all destination types)
  --autocache, --cache  Cache network data, and reuse cached data.
  -v, --verbose, --debug
                        Show debug details, including API calls and error sources.
  --version             Show version number and exit
  --quiet               Only display errors.
  --print, --print-dest
                        Print resulting URL/path to stdout, for chaining with other commands.
  --schema, --coerce-schema SCHEMA_COERCION
                        Coerce source schema according to a schema definition. (WARNING:
                        experimental feature)
  --restrict-schema     Exclude all columns not included in the SCHEMA_COERCION definition.
                        (WARNING: experimental feature)
  --daemonize           Tableconv startup time (python startup time) is slow. To mitigate that,
                        you can first run tableconv as a daemon, and then all future invocations
                        will be fast. (while daemon is still alive) (WARNING: experimental
                        feature)
  --multitable, --multifile
                        Convert entire "database"s of tables from one format to another, such as
                        folders with many csvs, a multi-tab spreadsheet, or an actual RDBMS
                        (WARNING: This is an experimental mode, very rough, details undocumented)

supported url schemes:
  ascii:- (dest only)
  asciibox:- (dest only)
  asciifancygrid:- (dest only)
  asciigrid:- (dest only)
  asciilite:- (dest only)
  asciipipe:- (dest only)
  asciiplain:- (dest only)
  asciipresto:- (dest only)
  asciipretty:- (dest only)
  asciipsql:- (dest only)
  asciirich:- (dest only)
  asciisimple:- (dest only)
  awsathena://eu-central-1
  awsdynamodb://eu-central-1/example_table (source only)
  awslogs://eu-central-1//aws/lambda/example-function (source only)
  cmd://ls -l example (source only)
  csa:-
  example.avro
  example.binpb (source only)
  example.csv
  example.dta
  example.duckdb
  example.feather
  example.fixedwidth
  example.fwf
  example.h5
  example.hdf5
  example.html
  example.json
  example.jsonl
  example.jsonlines
  example.ldjson
  example.msgpack
  example.ndjson
  example.numbers (source only)
  example.odf
  example.ods
  example.odt
  example.orc (source only)
  example.parquet
  example.pcap (source only)
  example.pcapng (source only)
  example.pickledf
  example.protob (source only)
  example.protobuf (source only)
  example.py
  example.python
  example.toml
  example.tsv
  example.xls
  example.xlsb
  example.xlsm
  example.xlsx
  example.yaml
  example.yml
  file_per_row:///tmp/example (each file is considered a (filename,value) record)
  gsheets://:new:
  iceberg:///tmp/warehouse?catalog_uri=sqlite:////tmp/warehouse/pyiceberg_catalog.db
  jc://ls -l example (source only)
  jiraformat:- (dest only)
  jsonarray:-
  jsondict:- (source only)
  latex:- (dest only)
  leveldblog:output-0 (source only)
  list:-
  markdown:- (dest only)
  md:- (dest only)
  mediawikiformat:- (dest only)
  moinmoinformat:- (dest only)
  mssql://127.0.0.1:5432/example_db
  mysql://127.0.0.1:5432/example_db
  nestedlist:-
  oracle://127.0.0.1:5432/example_db
  osquery://processes (source only)
  postgis://127.0.0.1:5432/example_db
  postgres://127.0.0.1:5432/example_db
  postgresql://127.0.0.1:5432/example_db
  pylist:-
  pythonlist:-
  rich:- (dest only)
  rst:- (dest only)
  sh://ls -l example (source only)
  smartsheet://SHEET_ID (source only)
  sql_literal:- (dest only)
  sql_values:- (dest only)
  sqlite3:///tmp/example.db
  sqlite:///tmp/example.db
  sumologic://?from=2021-03-01T00:00:00Z&to=2021-05-03T00:00:00Z (source only)
  tex:- (dest only)
  tsa:-
  yamlsequence:-

help & support:
  https://github.com/personalcomputer/tableconv/issues/new
```

## Python API

### Quickstart Example: Basic API usage: Replicating a typical CLI command using the API

```python
In [1]: import tableconv

In [2]: # tableconv test.csv -q 'SELECT time, name FROM data ORDER BY time DESC' -o gsheets://:new:/?name=test

In [3]: tableconv.load_url('test.csv', query='SELECT time, name FROM data ORDER BY time DESC').dump_to_url('gsheets://:new:', params={'name': 'test'})
```

### Quickstart Example: More advanced API usage: Importing in data from an arbitrary URL to a python dictionary

```python
In [1]: import tableconv

In [2]: tableconv.load_url('postgresql://localhost:5432/test_db/cities').as_dict_records()
Out[2]:
[
 {'LatD': 41, 'LatM': 5, 'LatS': 59, 'NS': 'N', 'LonD': 80, 'LonM': 39, 'LonS': 0, 'EW': 'W', 'City': 'Youngstown', 'State': 'OH'},
 {'LatD': 42, 'LatM': 52, 'LatS': 48, 'NS': 'N', 'LonD': 97, 'LonM': 23, 'LonS': 23, 'EW': 'W', 'City': 'Yankton', 'State': 'SD'},
 [...]
]
```

### SDK API Reference Documentation

(Reference documentation pending)

