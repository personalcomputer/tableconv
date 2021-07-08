# tableconv

"tableconv" is a prototype of a core data plumbing tool that interprets everything as a table, enables SQL on all tables, and enables complete data portability across 50+ tabular formats. It is very similar in concept to the "pandoc" tool, except for data tables.

Its primary usecase is as a quick and dirty CLI ETL tool for converting tabular data from any of 50+ tabular input formats into 50+ tabular output formats (such as CSV, Postgres, XLS, Google Sheets, etc).

# Prior Art

- odo http://odo.pydata.org/en/latest/
- Singer https://www.singer.io/
- Hive SerDes https://cwiki.apache.org/confluence/display/Hive/SerDe
- ODBC
