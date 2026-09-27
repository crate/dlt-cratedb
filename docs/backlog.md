# CrateDB destination adapter backlog

## Iteration +1

- `dlt init chess cratedb` fails, because the dlt CLI does not import
  `dlt_cratedb`, so it cannot resolve the `cratedb` destination.

- ERROR: mismatched input 'ABORT' expecting {....

- Documentation: How JSONB/ARRAYs are mapped to CrateDB

- Is it possible to use an `adapter` to better support CrateDB's special
  data types? For example, full round-tripping using `sys.summits` isn't
  possible just yet, due to the `coordinates` column, for example when
  selecting DuckDB.

- Is it possible to provide other direct loaders from the `sqlalchemy`
  adapter?

- Addressing per `cratedb://` will raise errors. dlt passes the URL
  scheme through to psycopg2, which rejects it:
  `invalid dsn: invalid connection option "cratedb://crate:@localhost:5432?connect_timeout"`.
  Without a password, e.g. `cratedb://crate@localhost:5432/`, resolving
  the configuration fails even earlier:
  `Missing 1 field(s) in configuration CrateDbClientConfiguration: credentials`.
  The same happens with `postgres://crate@localhost:5432/`, so CrateDB's
  password-less default user must be spelled `crate:@`.

- Add staging support
  > CrateDB supports Amazon S3, Google Cloud Storage, and Azure Blob
  > Storage as file staging destinations.

## Verify

- > Data is loaded into CrateDB using the most efficient method
  > depending on the data source.

## Iteration +2

- The `UNIQUE` constraint is dearly missing. Is it possible to emulate?
  Otherwise, when loading data multiple times, duplicates will happen.
  ```
  cr> select * from users;
  +----+-------+-------------------+----------------+
  | id | name  |     _dlt_load_id  | _dlt_id        |
  +----+-------+-------------------+----------------+
  |  2 | Bob   | 1749406972.57687  | NFPmX5Pw4gZ7fA |
  |  1 | Alice | 1749406985.809837 | 6/Xoe8jhlBUbAQ |
  |  2 | Bob   | 1749406985.809837 | VnP4S8AsQ/ujOg |
  |  1 | Alice | 1749406972.57687  | 4HCWs9jqfwTyTQ |
  +----+-------+-------------------+----------------+
  SELECT 4 rows in set (0.003 sec)
  ```

- Provide Ibis dataset access, see
  tests/load/test_read_interfaces.py

- Software tests about geospatial concerns have been removed.
  See `postgres` adapter for bringing them back.
