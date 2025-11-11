# CrateDB destination adapter for dlt

[![Status][badge-status]][project-pypi]
[![CI][badge-ci]][project-ci]
[![Coverage][badge-coverage]][project-coverage]
[![Downloads per month][badge-downloads-per-month]][project-downloads]

[![License][badge-license]][project-license]
[![Release Notes][badge-release-notes]][project-release-notes]
[![PyPI Version][badge-package-version]][project-pypi]
[![Python Versions][badge-python-versions]][project-pypi]

» [Documentation]
| [Releases]
| [Issues]
| [Source code]
| [License]
| [CrateDB]
| [Community Forum]

## About

The [dlt-cratedb] package is temporary for shipping the code until
[DLT-2733] is ready for upstreaming into main [dlt].

## Documentation

Please refer to the [overview] and the [usage guide].

## What's inside

- The `cratedb` adapter is heavily based on the `postgres` adapter.
- The `CrateDbSqlClient` deviates from the original `Psycopg2SqlClient` by
  accounting for [CRATEDB-15161] per `SystemColumnWorkaround`. This will be
  resolved with [DLT-CRATEDB-30] when CrateDB 6.2 will be released around
  January/February 2026.
- A few more other patches to account for specifics of CrateDB.

## Backlog

The project tracks corresponding [issues] and a few more [backlog] items
to be resolved in its incubation phase.


[backlog]: https://github.com/crate/dlt-cratedb/blob/main/docs/backlog.md
[CRATEDB-15161]: https://github.com/crate/crate/issues/15161
[dlt]: https://github.com/dlt-hub/dlt
[DLT-2733]: https://github.com/dlt-hub/dlt/pull/2733
[dlt-cratedb]: https://pypi.org/project/dlt-cratedb
[DLT-CRATEDB-30]: https://github.com/crate/dlt-cratedb/pull/30
[issues]: https://github.com/crate/dlt-cratedb/issues
[overview]: https://cratedb.com/docs/guide/integrate/dlt/
[usage guide]: https://cratedb.com/docs/guide/integrate/dlt/usage.html

[CrateDB]: https://cratedb.com/database
[Bluesky]: https://bsky.app/search?q=cratedb
[Community Forum]: https://community.cratedb.com/
[Documentation]: https://cratedb.com/docs/guide/integrate/dlt/
[Issues]: https://github.com/crate/dlt-cratedb/issues
[License]: https://github.com/crate/dlt-cratedb/blob/main/LICENSE.txt
[managed on GitHub]: https://github.com/crate/dlt-cratedb
[Source code]: https://github.com/crate/dlt-cratedb
[Releases]: https://github.com/surister/dlt-cratedb/releases

[badge-ci]: https://github.com/crate/dlt-cratedb/actions/workflows/tests.yml/badge.svg
[badge-bluesky]: https://img.shields.io/badge/Bluesky-0285FF?logo=bluesky&logoColor=fff&label=Follow%20%40CrateDB
[badge-coverage]: https://codecov.io/gh/crate/dlt-cratedb/branch/main/graph/badge.svg
[badge-downloads-per-month]: https://pepy.tech/badge/dlt-cratedb/month
[badge-license]: https://img.shields.io/github/license/crate/dlt-cratedb
[badge-package-version]: https://img.shields.io/pypi/v/dlt-cratedb.svg
[badge-python-versions]: https://img.shields.io/pypi/pyversions/dlt-cratedb.svg
[badge-release-notes]: https://img.shields.io/github/release/crate/dlt-cratedb?label=Release+Notes
[badge-status]: https://img.shields.io/pypi/status/dlt-cratedb.svg
[project-ci]: https://github.com/crate/dlt-cratedb/actions/workflows/tests.yml
[project-coverage]: https://app.codecov.io/gh/crate/dlt-cratedb
[project-downloads]: https://pepy.tech/project/dlt-cratedb/
[project-license]: https://github.com/crate/dlt-cratedb/blob/main/LICENSE.txt
[project-pypi]: https://pypi.org/project/dlt-cratedb
[project-release-notes]: https://github.com/crate/dlt-cratedb/releases
