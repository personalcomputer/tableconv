# tableconv

"tableconv" is a prototype of a core data plumbing tool that enables complete data portability across 50+ tabular formats. It is similar in concept to the "pandoc" tool, except for data tables.

Its primary usecase is as a quick and dirty CLI ETL tool for converting tabular data from any of 50+ input formats into 50+ output formats (such as CSV, Postgres, XLS, Google Sheets, JSON, etc).

It also supports basic in-line data transformation using SQL and has an interactive mode enabling DB-shell-like interactions with e.g. CSV files.

The tableconv vision of computing is that all software fundamentally interfaces with data tables, that all APIs can be interpretted as data tables, and that this world needs a generic operating system level client for users to interact with the tables. tableconv is that tool. It is meant to have adapters written to support any/all service and extract or upload data to them to/from generic and portable tabular format.

The tableconv prototype software is slow, it is not suitable for tables over 1 million rows. It also has experimental features that will not work reliably, such as schema management, and special array (1 dimensional table) support.

# Prior Art

- odo http://odo.pydata.org/en/latest/
- Singer https://www.singer.io/
- Hive SerDes https://cwiki.apache.org/confluence/display/Hive/SerDe
- ODBC
