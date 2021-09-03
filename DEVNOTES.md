
## Adapters that need to be added
- bson
- msgpack
- avro
- pickle or dill
- serpent (alternative implementation of python literal serialization)
- multifile/folder support, where each file is part of the same table.
  - Can still treat as multi-table via complicated queries, like `SELECT users.id, photos.name from data users JOIN data photos ON (photos.filename='photos' AND photos.author_id=users.id) WHERE users.filename='users'`. This is difficult thuough, so alternatively it could have support for treating multi-file as multi-table.



## Writeups on related projects

Most influential:
- odo
  - Really novel tool that takes native format conversion tools from many different libraries and provides a unified interface for them. Wherever possible it tries to use native code to convert directly from your src to dest, but if there is no direct converter it uses an intermediate format (actually can use any number of chained intermediate formats, that it dynamically calculates. It has no prefered internal intermediate format).   - http://odo.pydata.org/en/latest/
- Singer
  - OSS "open-core" spinoff from the Stich ETL platform (managed). This is not so much a tool itself as it is just a spec for a JSON-based intermediate format that has spawned some ~100 tools written in different languages that can import and export to the intermediate format. https://www.singer.io/
- ODBC/JDBC
  - 1980s/90s successful standard API for database drivers. Widely embraced by database developers. https://en.wikipedia.org/wiki/Open_Database_Connectivity.
- osquery https://github.com/osquery/osquery
  - Very popular tool that exposing os-level information such as process status in a SQL interface. Used in sysadmin automation. Exposed as a Thrift API, with sdks in many languages.

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
- Spark http://spark.apache.org/docs/latest/sql-data-sources.html
  - Has concept of "RDDs", providing an abstract dataframe-based query interface to an arbitrary distributed backend datastore. Wrapped by spark-SQL to make this a SQL interface. Excellent distributed performance on a cluster.
- https://github.com/johnkerl/miller
  - Data file query tool. Implements a custom query language.
- https://github.com/BurntSushi/xsv
  - Comprehensive CSV query tool. Implements a custom query language.
- https://github.com/tstack/lnav
  - Inspiration for adding misc log formats support and the regex adapter
