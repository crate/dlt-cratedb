# Changelog

## Unreleased

- Fixed CrateDB crashes by configuring `caps.max_query_length` to 4MB

## 2026/03/04 v0.1.0

- Removed `SystemColumnWorkaround` for `_`-prefixed column names.
  The package now requires CrateDB 6.2 or higher.

  At the same time, the update will invalidate existing `dlt` bookkeeping
  columns starting with two underscores, like `__dlt_id` or `__dlt_load_id`.
  Going forward, original `dlt` bookkeeping columns will be used, like
  `_dlt_id` or `_dlt_load_id`.

  After installing v0.1.0, the next load cannot use prior incremental
  bookkeeping and will fall back to a full load once. Subsequent loads will
  use the new `_dlt_*` bookkeeping. If you want to avoid this transition
  behavior, we recommend to continue using the previous release v0.0.2.

  If you continue with the update and have validated successful loads on
  v0.1.0, you can drop deprecated bookkeeping columns starting with `__dlt_`
  from your target tables.

- Fixed truncating tables by adding `CrateDbSqlClient._truncate_table_sql`

## 2025/07/07 v0.0.2
- ingestr: Fixed importing from Kafka per `SystemColumnWorkaround`

## 2025/06/24 v0.0.1
- Fixed mypy error `missing library stubs or py.typed marker`
- Satisfied `mypy` type checker

## 2025/06/24 v0.0.0
- Started the project, derived from https://github.com/dlt-hub/dlt/pull/2733
