"""
Regression tests for crate/dlt-cratedb#14.

`merge` / `delete-insert` write dispositions and `refresh="drop_resources"` used to crash
on the CrateDB adapter with either:

- `DestinationSchemaTampered` (schema version-hash mismatch during the load step), or
- `DatabaseUndefinedRelation: Relation 'testdrive_staging._dlt_version' unknown`.
"""

import uuid
from typing import Any, Dict, List

import dlt

import dlt_cratedb  # noqa: F401  -- registers `dlt.destinations.cratedb`
from dlt_cratedb.impl.cratedb.configuration import CrateDbCredentials


def _dataset_name() -> str:
    # Stable within a test (dev_mode off) so its repeated loads share one dataset,
    # unique across tests for isolation.
    return "test_merge_" + uuid.uuid4().hex[:12]


def _pipeline(credentials: CrateDbCredentials, dataset_name: str) -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name="test_cratedb_merge_" + dataset_name,
        destination=dlt.destinations.cratedb(credentials=credentials),
        dataset_name=dataset_name,
        dev_mode=False,
    )


def _row_count(pipeline: dlt.Pipeline, table_name: str) -> int:
    with pipeline.sql_client() as client:
        qualified = client.make_qualified_table_name(table_name)
        client.execute_sql(f"REFRESH TABLE {qualified}")
        with client.execute_query(f"SELECT COUNT(*) FROM {qualified}") as cur:
            return int(cur.fetchone()[0])


def _names(pipeline: dlt.Pipeline, table_name: str) -> set:
    with pipeline.sql_client() as client:
        qualified = client.make_qualified_table_name(table_name)
        client.execute_sql(f"REFRESH TABLE {qualified}")
        with client.execute_query(f"SELECT name FROM {qualified}") as cur:
            return {row[0] for row in cur.fetchall()}


def test_merge_does_not_tamper_schema(credentials: CrateDbCredentials) -> None:
    """Two consecutive `merge` loads must not raise `DestinationSchemaTampered`."""
    dataset_name = _dataset_name()
    pipeline = _pipeline(credentials, dataset_name)

    first: List[Dict[str, Any]] = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    second: List[Dict[str, Any]] = [
        {"id": 2, "name": "Bob v2"},  # update
        {"id": 3, "name": "Carol"},  # insert
    ]

    info1 = pipeline.run(first, table_name="people", write_disposition="merge", primary_key="id")
    assert not info1.has_failed_jobs

    # The 2nd load triggers the staging pass that used to crash.
    info2 = pipeline.run(second, table_name="people", write_disposition="merge", primary_key="id")
    assert not info2.has_failed_jobs

    # `merge` is redirected to a full replace on CrateDB (GH-6): the 2nd load replaces the
    # 1st, so only `second`'s rows remain.
    assert _names(pipeline, "people") == {"Bob v2", "Carol"}


def test_delete_insert_without_primary_key(credentials: CrateDbCredentials) -> None:
    dataset_name = _dataset_name()
    pipeline = _pipeline(credentials, dataset_name)

    rows: List[Dict[str, Any]] = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    info1 = pipeline.run(
        rows,
        table_name="people",
        write_disposition={"disposition": "merge", "strategy": "delete-insert"},
    )
    assert not info1.has_failed_jobs

    info2 = pipeline.run(
        rows,
        table_name="people",
        write_disposition={"disposition": "merge", "strategy": "delete-insert"},
    )
    assert not info2.has_failed_jobs


def test_refresh_drop_resources(credentials: CrateDbCredentials) -> None:
    dataset_name = _dataset_name()
    pipeline = _pipeline(credentials, dataset_name)

    @dlt.resource(name="people", write_disposition="append")
    def people():
        yield {"id": 1, "name": "Alice"}
        yield {"id": 2, "name": "Bob"}

    info1 = pipeline.run(people(), refresh="drop_resources")
    assert not info1.has_failed_jobs

    # 2nd invocation drops resources first, then re-creates — the documented failure point.
    info2 = pipeline.run(people(), refresh="drop_resources")
    assert not info2.has_failed_jobs

    # 3rd invocation, where the issue reports the secondary staging `_dlt_version` error.
    info3 = pipeline.run(people(), refresh="drop_resources")
    assert not info3.has_failed_jobs

    assert _row_count(pipeline, "people") == 2


def test_refresh_with_missing_staging_version_table(credentials: CrateDbCredentials) -> None:
    """`refresh="drop_resources"` must not crash when the staging `_dlt_version` is gone.

    Secondary symptom of GH-14: a staging dataset can look initialized (our `_placeholder`
    table) while `_dlt_version` is gone — the partial state ingestr's ephemeral jobs leave.
    dlt then deletes from a missing `_dlt_version` and used to abort the load.
    """
    dataset_name = _dataset_name()
    pipeline = _pipeline(credentials, dataset_name)

    @dlt.resource(name="people", write_disposition="append")
    def people():
        yield {"id": 1, "name": "Alice"}

    pipeline.run(people(), refresh="drop_resources")
    pipeline.run(people(), refresh="drop_resources")  # creates the staging dataset

    # Simulate the partial staging state: keep the placeholder, drop `_dlt_version`.
    staging_dataset = dataset_name + "_staging"
    with pipeline.sql_client() as client:
        client.execute_sql(f'CREATE TABLE IF NOT EXISTS "{staging_dataset}"._placeholder (id INT)')
        client.execute_sql(f'DROP TABLE IF EXISTS "{staging_dataset}"."_dlt_version"')

    info = pipeline.run(people(), refresh="drop_resources")
    assert not info.has_failed_jobs
