# CrateDB destination adapter for dlt

[![Status][badge-status]][project-pypi]
[![CI][badge-ci]][project-ci]
[![Coverage][badge-coverage]][project-coverage]
[![Downloads per month][badge-downloads-per-month]][project-downloads]

[![License][badge-license]][project-license]
[![Release Notes][badge-release-notes]][project-release-notes]
[![PyPI Version][badge-package-version]][project-pypi]
[![Python Versions][badge-python-versions]][project-pypi]
[![Python Versions][badge-dlt-versions]][dlt]

» [Documentation]
| [Releases]
| [Issues]
| [Source code]
| [License]
| [CrateDB]
| [Community Forum]
| [Bluesky]

## About

The [dlt-cratedb] package is temporary for shipping the code until
[DLT-2733] is ready for upstreaming into main [dlt].

## Documentation

Please refer to the [handbook].

## What's inside

- The `cratedb` adapter is heavily based on the `postgres` adapter.
- The `CrateDbSqlClient` deviates from the original `Psycopg2SqlClient` by
  accounting for [CRATEDB-15161] per `SystemColumnWorkaround`.
- A few more other patches.

## Backlog

We are tracking corresponding [issues] and a few more [backlog] items
to be resolved as we go.


[backlog]: https://github.com/crate/dlt-cratedb/blob/main/docs/backlog.md
[CRATEDB-15161]: https://github.com/crate/crate/issues/15161
[dlt]: https://github.com/dlt-hub/dlt
[DLT-2733]: https://github.com/dlt-hub/dlt/pull/2733
[dlt-cratedb]: https://pypi.org/project/dlt-cratedb
[issues]: https://github.com/crate/dlt-cratedb/issues
[handbook]: https://github.com/crate/dlt-cratedb/blob/main/docs/cratedb.md

[CrateDB]: https://cratedb.com/database
[Bluesky]: https://bsky.app/search?q=cratedb
[Community Forum]: https://community.cratedb.com/
[Documentation]: https://github.com/crate/dlt-cratedb
[Issues]: https://github.com/crate/dlt-cratedb/issues
[License]: https://github.com/crate/dlt-cratedb/blob/main/LICENSE.txt
[managed on GitHub]: https://github.com/crate/dlt-cratedb
[Source code]: https://github.com/crate/dlt-cratedb
[Releases]: https://github.com/surister/dlt-cratedb/releases

[badge-ci]: https://github.com/crate/dlt-cratedb/actions/workflows/tests.yml/badge.svg
[badge-dlt-versions]: https://img.shields.io/badge/dlt-1.10%2C%201.11%2C%201.12-blue.svg
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
[project-license]: https://github.com/crate/dlt-cratedb/blob/main/LICENSE
[project-pypi]: https://pypi.org/project/dlt-cratedb
[project-release-notes]: https://github.com/crate/dlt-cratedb/releases
