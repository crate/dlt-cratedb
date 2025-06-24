# CrateDB destination adapter for dlt

## About

The [dlt-cratedb] package is temporary for shipping the code until
[DLT-2733] is ready for upstreaming.

## Documentation

Please refer to the [handbook].

## What's inside

- The `cratedb` adapter is heavily based on the `postgres` adapter.
- The `CrateDbSqlClient` deviates from the original `Psycopg2SqlClient` by
  accounting for [CRATEDB-15161] per `SystemColumnWorkaround`.
- A few more other patches.

## Backlog

We are tracking corresponding [issues] on the dlt fork project.
A few more [backlog] items also need to be resolved.


[backlog]: docs/backlog.md
[CRATEDB-15161]: https://github.com/crate/crate/issues/15161
[dlt]: https://github.com/dlt-hub/dlt
[DLT-2733]: https://github.com/dlt-hub/dlt/pull/2733
[dlt-cratedb]: https://pypi.org/project/dlt-cratedb
[issues]: https://github.com/crate-workbench/dlt/issues
[handbook]: docs/cratedb.md
