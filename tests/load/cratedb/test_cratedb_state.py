"""
Pipeline state written by a load must be visible once the load completes.

dlt writes pipeline state as a row in `_dlt_pipeline_state`, and restores it from the
destination with a query joining that table to `_dlt_loads`. CrateDB only shows inserted
rows to such queries after a refresh, so a run that restores state before the next
periodic refresh used to get no state, or an older one, and reloaded incremental data.
"""

import time
import uuid
from pathlib import Path
from typing import Any, Iterator, List, Tuple

import dlt
import pytest

import dlt_cratedb  # noqa: F401  -- registers `dlt.destinations.cratedb`
from dlt_cratedb.impl.cratedb.configuration import CrateDbCredentials


def _dataset_name() -> str:
    return "test_state_" + uuid.uuid4().hex[:12]


def _pipeline(
    credentials: CrateDbCredentials,
    dataset_name: str,
    pipelines_dir: Path,
) -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name="test_cratedb_state_" + dataset_name,
        pipelines_dir=str(pipelines_dir),
        destination=dlt.destinations.cratedb(credentials=credentials),
        dataset_name=dataset_name,
        dev_mode=False,
    )


def _drop_tables(pipeline: dlt.Pipeline) -> None:
    """`drop_dataset()` only drops CrateDB's placeholder table, so drop everything explicitly."""
    with pipeline.sql_client() as client:
        with client.execute_query(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
            pipeline.dataset_name,
        ) as cur:
            names = [row[0] for row in cur.fetchall()]
        for name in names:
            client.execute_sql(f"DROP TABLE IF EXISTS {client.make_qualified_table_name(name)}")


def _statements_issued_by_complete_load(pipeline: dlt.Pipeline) -> Tuple[str, List[str]]:
    """Call `complete_load` on a fresh client and record every statement it executes."""
    with pipeline.destination_client() as client:
        state_table = client.sql_client.make_qualified_table_name(client.schema.state_table_name)
        issued: List[str] = []
        execute_sql = client.sql_client.execute_sql

        def recorder(sql: Any, *args: Any, **kwargs: Any) -> Any:
            issued.append(str(sql))
            return execute_sql(sql, *args, **kwargs)

        client.sql_client.execute_sql = recorder  # type: ignore[method-assign]
        client.complete_load("0000000000.000001")
    return state_table, issued


@pytest.fixture
def dataset_name() -> str:
    return _dataset_name()


@pytest.fixture
def cleanup(credentials: CrateDbCredentials, dataset_name: str, tmp_path: Path) -> Iterator[None]:
    yield
    _drop_tables(_pipeline(credentials, dataset_name, tmp_path / "cleanup"))


@dlt.resource(name="items", write_disposition="append")
def items(
    data: List[int],
    cursor: dlt.sources.incremental[int] = dlt.sources.incremental("id"),  # noqa: B008  -- dlt idiom
) -> Iterator[Any]:
    yield [{"id": i} for i in data]


def test_complete_load_refreshes_state_table(
    credentials: CrateDbCredentials, dataset_name: str, tmp_path: Path, cleanup: None
) -> None:
    pipeline = _pipeline(credentials, dataset_name, tmp_path / "p1")
    pipeline.run(items([1, 2]))

    state_table, issued = _statements_issued_by_complete_load(pipeline)
    assert f"REFRESH TABLE {state_table}" in issued


def test_state_restored_by_a_fresh_pipeline(
    credentials: CrateDbCredentials, dataset_name: str, tmp_path: Path, cleanup: None
) -> None:
    pipeline = _pipeline(credentials, dataset_name, tmp_path / "p1")
    pipeline.run(items([1, 2]))

    # Disable periodic refresh on the state table, so the next load's state row stays
    # hidden unless something refreshes it. CrateDB can still refresh internally, so this
    # makes a pass without the fix unlikely rather than impossible. Changing the interval
    # queues a refresh of its own: let it land before the second load.
    with pipeline.sql_client() as client:
        state_table = client.make_qualified_table_name(pipeline.default_schema.state_table_name)
        client.execute_sql(f"ALTER TABLE {state_table} SET (refresh_interval = 0)")
        client.execute_sql(f"REFRESH TABLE {state_table}")
    time.sleep(1)

    info = pipeline.run(items([3, 4]))
    second_load_id = info.loads_ids[-1]

    # A fresh pipelines dir has no local state, so it has to restore from CrateDB.
    fresh = _pipeline(credentials, dataset_name, tmp_path / "p2")
    fresh.sync_destination()

    with fresh.destination_client() as client:
        stored = client.get_stored_state(fresh.pipeline_name)
    assert stored is not None
    assert stored._dlt_load_id == second_load_id
    cursor = fresh.state["sources"][fresh.default_schema_name]["resources"]["items"]["incremental"][
        "id"
    ]
    assert cursor["last_value"] == 4


def test_load_without_state_extraction(
    credentials: CrateDbCredentials,
    dataset_name: str,
    tmp_path: Path,
    cleanup: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # With state sync off, dlt extracts no state and the schema has no state table.
    monkeypatch.setenv("RESTORE_FROM_DESTINATION", "false")
    pipeline = _pipeline(credentials, dataset_name, tmp_path / "p1")
    info = pipeline.run([{"id": 1}], table_name="items")
    assert not info.has_failed_jobs
    assert pipeline.default_schema.state_table_name not in pipeline.default_schema.tables

    # No state table to refresh, so no statement that is bound to fail.
    state_table, issued = _statements_issued_by_complete_load(pipeline)
    assert f"REFRESH TABLE {state_table}" not in issued


def test_load_tolerates_dropped_state_table(
    credentials: CrateDbCredentials, dataset_name: str, tmp_path: Path, cleanup: None
) -> None:
    pipeline = _pipeline(credentials, dataset_name, tmp_path / "p1")
    pipeline.run([{"id": 1}], table_name="items")

    with pipeline.sql_client() as client:
        state_table = client.make_qualified_table_name(pipeline.default_schema.state_table_name)
        client.execute_sql(f"DROP TABLE {state_table}")

    # Same data shape and unchanged state: same schema hash, so dlt does not recreate the
    # table, and no state row is written.
    info = pipeline.run([{"id": 2}], table_name="items")
    assert not info.has_failed_jobs
