# Changelog

## Unreleased

- Fixed incremental loads reloading data when a run restores its pipeline state from
  CrateDB shortly after the previous load: `_dlt_pipeline_state` is now refreshed when a
  load completes, like `_dlt_loads`, so the next run sees the state that load wrote.
- Fixed every load that writes data failing on dlt 1.30 with "dlt cannot determine the data location
  of destination `cratedb`": the destination now reports its cluster address
  (`host:port`) as its data location, since CrateDB has no databases.
- Fixed `merge`, `delete-insert`, and `refresh="drop_resources"` crashing on CrateDB
  (GH-14): the datetime type mapper no longer mutates the live schema (which tripped
  `DestinationSchemaTampered`), and deleting a schema now tolerates an already-dropped
  `_dlt_version` table instead of aborting the load.
- Fixed importing from MongoDB: columns that collide with CrateDB's reserved
  system column names (most notably MongoDB's `_id`) are now renamed with a
  leading underscore (e.g. `_id` -> `__id`) via a dedicated naming convention,
  instead of failing with `"_id" conflicts with system column`.
- Fixed loading strings that contain newlines or carriage returns: string literals are
  now rendered on one line as escape strings (`E'...'`). dlt splits load files into
  statements line by line, so a larger load could fail with `SyntaxError: ... no viable
  alternative at input 'VALUES ...`, and carriage returns were stored as newlines.

## 2026/03/10 v0.1.1

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
