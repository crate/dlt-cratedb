"""
Integration tests for the `merge` write disposition.

- `delete-insert` and `scd2` run as merges, not as a replace.
  https://github.com/crate/dlt-cratedb/issues/6
- `upsert` and `insert-only` are refused before loading.
  https://github.com/crate/dlt-cratedb/issues/64
- `merge` / `delete-insert` write dispositions and `refresh="drop_resources"` used to crash
  with `DestinationSchemaTampered` or
  `DatabaseUndefinedRelation: Relation 'testdrive_staging._dlt_version' unknown`.
  https://github.com/crate/dlt-cratedb/issues/14
"""

import uuid
from typing import Any, Dict, Iterator, List, Sequence, Tuple

import dlt
import psycopg2
import pytest
from dlt.common.destination.exceptions import DestinationCapabilitiesException
from dlt.common.schema.typing import MERGE_STRATEGIES
from dlt.pipeline.exceptions import PipelineStepFailed
from verlib2 import Version

import dlt_cratedb  # noqa: F401  -- registers `dlt.destinations.cratedb`
from dlt_cratedb.impl.cratedb.configuration import CrateDbCredentials
from dlt_cratedb.impl.cratedb.cratedb import CrateDbMergeJob

SCD2 = {"disposition": "merge", "strategy": "scd2"}
DELETE_INSERT = {"disposition": "merge", "strategy": "delete-insert"}


@pytest.fixture
def dataset_name(credentials: CrateDbCredentials) -> Iterator[str]:
    """A dataset unique to the test, whose tables are dropped afterwards.

    Each table takes shards, and a long-lived CrateDB refuses new tables at 1000 open shards.
    """
    name = "test_merge_" + uuid.uuid4().hex[:12]
    yield name
    conn = psycopg2.connect(dsn=credentials.to_native_representation())
    conn.autocommit = True
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT table_schema, table_name FROM information_schema.tables"
                " WHERE table_schema IN (%s, %s) AND table_type = 'BASE TABLE'",
                (name, name + "_staging"),
            )
            for schema, table in cursor.fetchall():
                cursor.execute(f'DROP TABLE IF EXISTS "{schema}"."{table}"')
    finally:
        conn.close()


@pytest.fixture
def pipeline(credentials: CrateDbCredentials, dataset_name: str) -> dlt.Pipeline:
    # `dev_mode` off, so a test's repeated loads share one dataset.
    return dlt.pipeline(
        pipeline_name="test_cratedb_merge_" + dataset_name,
        destination=dlt.destinations.cratedb(credentials=credentials),
        dataset_name=dataset_name,
        dev_mode=False,
    )


def _run(pipeline: dlt.Pipeline, data: Any, **kwargs: Any) -> None:
    info = pipeline.run(data, **kwargs)
    assert not info.has_failed_jobs, info


def _query(pipeline: dlt.Pipeline, sql: str) -> List[Tuple[Any, ...]]:
    with pipeline.sql_client() as client:
        with client.execute_query(sql) as cursor:
            return [tuple(row) for row in cursor.fetchall()]


def _rows(pipeline: dlt.Pipeline, table_name: str, columns: str) -> List[Tuple[Any, ...]]:
    with pipeline.sql_client() as client:
        qualified = client.make_qualified_table_name(table_name)
        client.execute_sql(f"REFRESH TABLE {qualified}")
    return _query(pipeline, f"SELECT {columns} FROM {qualified} ORDER BY {columns}")


def _values(pipeline: dlt.Pipeline, table_name: str) -> List[Any]:
    return [row[0] for row in _rows(pipeline, table_name, "value")]


def _row_count(pipeline: dlt.Pipeline, table_name: str) -> int:
    return len(_rows(pipeline, table_name, "_dlt_id"))


def _names(pipeline: dlt.Pipeline, table_name: str) -> set:
    return {row[0] for row in _rows(pipeline, table_name, "name")}


def _rerun_merge_sql(pipeline: dlt.Pipeline, table_names: Sequence[str]) -> None:
    """Execute the last load's merge SQL twice more, as a retry of the job would.

    Split the statements the way dlt does for a job file (one statement per line, then on
    `;`), because CrateDB 6.2 rejects empty statements.
    """
    with pipeline.destination_client() as client:
        table_chain = [client.prepare_load_table(name) for name in table_names]
        lines = [
            " ".join(statement.splitlines())
            for statement in CrateDbMergeJob.generate_sql(table_chain, client.sql_client)
        ]
        fragments = [part.strip() for line in lines for part in line.split(";") if part.strip()]
        client.sql_client.execute_many(fragments)
        client.sql_client.execute_many(fragments)


def test_merge_does_not_tamper_schema(pipeline: dlt.Pipeline) -> None:
    """Two consecutive `merge` loads must not raise `DestinationSchemaTampered`."""
    first: List[Dict[str, Any]] = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    second: List[Dict[str, Any]] = [
        {"id": 2, "name": "Bob v2"},  # update
        {"id": 3, "name": "Carol"},  # insert
    ]

    _run(pipeline, first, table_name="people", write_disposition="merge", primary_key="id")

    # The 2nd load triggers the staging pass that used to crash.
    _run(pipeline, second, table_name="people", write_disposition="merge", primary_key="id")

    assert _names(pipeline, "people") == {"Alice", "Bob v2", "Carol"}


def test_delete_insert_without_primary_key(pipeline: dlt.Pipeline) -> None:
    """Without a primary or merge key, `delete-insert` falls back to append."""
    rows: List[Dict[str, Any]] = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    _run(pipeline, rows, table_name="people", write_disposition=DELETE_INSERT)
    _run(pipeline, rows, table_name="people", write_disposition=DELETE_INSERT)

    assert _row_count(pipeline, "people") == 4


def test_merge_primary_key(pipeline: dlt.Pipeline) -> None:
    kwargs = {"table_name": "t", "write_disposition": "merge", "primary_key": "id"}
    _run(pipeline, [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}], **kwargs)
    _run(pipeline, [{"id": 2, "name": "b2"}, {"id": 3, "name": "c"}], **kwargs)

    assert _rows(pipeline, "t", "id, name") == [(1, "a"), (2, "b2"), (3, "c")]


def test_merge_is_visible_without_refresh(pipeline: dlt.Pipeline) -> None:
    """The merged rows are queryable as soon as the load returns."""
    kwargs = {"table_name": "t", "write_disposition": "merge", "primary_key": "id"}
    _run(pipeline, [{"id": 1}, {"id": 2}], **kwargs)
    _run(pipeline, [{"id": 2}, {"id": 3}], **kwargs)

    table = f'"{pipeline.dataset_name}"."t"'
    assert _query(pipeline, f"SELECT count(*) FROM {table}") == [(3,)]


def test_merge_deduplicates_without_dedup_sort(pipeline: dlt.Pipeline) -> None:
    """Deduplicating by primary key orders by a typed NULL, which CrateDB 6.2 needs.

    https://github.com/crate/dlt-cratedb/issues/7
    """
    kwargs = {"table_name": "t", "write_disposition": "merge", "primary_key": "id"}
    _run(pipeline, [{"id": 1, "v": 1}, {"id": 1, "v": 1}, {"id": 2, "v": 2}], **kwargs)

    assert _rows(pipeline, "t", "id, v") == [(1, 1), (2, 2)]


def test_merge_compound_primary_key(pipeline: dlt.Pipeline) -> None:
    kwargs = {"table_name": "t", "write_disposition": "merge", "primary_key": ["id", "name"]}
    _run(pipeline, [{"id": 1, "name": "a", "v": 1}, {"id": 1, "name": "b", "v": 1}], **kwargs)
    _run(pipeline, [{"id": 1, "name": "b", "v": 2}, {"id": 2, "name": "a", "v": 2}], **kwargs)

    assert _rows(pipeline, "t", "id, name, v") == [(1, "a", 1), (1, "b", 2), (2, "a", 2)]


def test_merge_compound_key_values_cannot_collide(pipeline: dlt.Pipeline) -> None:
    """A key part containing a would-be separator must not match an unrelated row."""
    kwargs = {"table_name": "t", "write_disposition": "merge", "primary_key": ["a", "b"]}
    _run(
        pipeline,
        [{"a": "a\x1fb", "b": "c", "v": "kept"}, {"a": "p", "b": "q", "v": "old"}],
        **kwargs,
    )
    _run(
        pipeline,
        [{"a": "a", "b": "b\x1fc", "v": "new"}, {"a": "p", "b": "q", "v": "new"}],
        **kwargs,
    )

    assert _rows(pipeline, "t", "v") == [("kept",), ("new",), ("new",)]


def test_merge_merge_key(pipeline: dlt.Pipeline) -> None:
    """A merge key replaces every destination row sharing a key with the batch."""
    resource = dlt.resource(
        [{"day": 1, "id": 1}, {"day": 1, "id": 2}, {"day": 2, "id": 3}],
        name="t",
        write_disposition="merge",
        merge_key="day",
    )
    _run(pipeline, resource)
    resource = dlt.resource(
        [{"day": 1, "id": 9}], name="t", write_disposition="merge", merge_key="day"
    )
    _run(pipeline, resource)

    assert _rows(pipeline, "t", "day, id") == [(1, 9), (2, 3)]


def test_merge_primary_key_and_merge_key(pipeline: dlt.Pipeline) -> None:
    """Rows matching either the primary key or the merge key are replaced."""

    def resource(data: List[Dict[str, Any]]) -> Any:
        return dlt.resource(
            data, name="t", write_disposition="merge", primary_key="id", merge_key="day"
        )

    _run(
        pipeline,
        resource(
            [{"day": 1, "id": 1}, {"day": 1, "id": 2}, {"day": 2, "id": 3}, {"day": 3, "id": 4}]
        ),
    )
    # Deletes the `day=1` rows by merge key and `id=4` by primary key.
    _run(pipeline, resource([{"day": 1, "id": 5}, {"day": 9, "id": 4}]))

    assert _rows(pipeline, "t", "day, id") == [(1, 5), (2, 3), (9, 4)]


def test_merge_hard_delete(pipeline: dlt.Pipeline) -> None:
    @dlt.resource(
        name="t",
        write_disposition="merge",
        primary_key="id",
        columns={"deleted": {"hard_delete": True, "data_type": "bool"}},
    )
    def resource(data: List[Dict[str, Any]]) -> Iterator[List[Dict[str, Any]]]:
        yield data

    _run(pipeline, resource([{"id": 1, "deleted": False}, {"id": 2, "deleted": False}]))
    _run(pipeline, resource([{"id": 1, "deleted": True}, {"id": 3, "deleted": False}]))

    assert _rows(pipeline, "t", "id") == [(2,), (3,)]


def test_merge_dedup_sort(pipeline: dlt.Pipeline) -> None:
    @dlt.resource(
        name="t", write_disposition="merge", primary_key="id", columns={"v": {"dedup_sort": "desc"}}
    )
    def resource(data: List[Dict[str, Any]]) -> Iterator[List[Dict[str, Any]]]:
        yield data

    _run(pipeline, resource([{"id": 1, "v": 1}, {"id": 1, "v": 5}, {"id": 1, "v": 3}]))

    assert _rows(pipeline, "t", "id, v") == [(1, 5)]


def test_merge_declared_deduplicated_skips_dedup(pipeline: dlt.Pipeline) -> None:
    """With `deduplicated: True`, staging rows are taken as they are."""
    write_disposition = {**DELETE_INSERT, "deduplicated": True}
    kwargs = {"table_name": "t", "write_disposition": write_disposition, "primary_key": "id"}
    _run(pipeline, [{"id": 1, "v": 1}], **kwargs)
    _run(pipeline, [{"id": 1, "v": 2}, {"id": 1, "v": 3}], **kwargs)

    assert _rows(pipeline, "t", "id, v") == [(1, 2), (1, 3)]


def test_merge_arrow_table(pipeline: dlt.Pipeline) -> None:
    """Arrow items carry no `_dlt_id`, which the single-table merge does not need."""
    pa = pytest.importorskip("pyarrow")
    kwargs = {"table_name": "t", "write_disposition": "merge", "primary_key": "id"}
    _run(pipeline, pa.table({"id": [1, 2], "name": ["a", "b"]}), **kwargs)
    _run(pipeline, pa.table({"id": [2, 3], "name": ["b2", "c"]}), **kwargs)

    assert _rows(pipeline, "t", "id, name") == [(1, "a"), (2, "b2"), (3, "c")]


def test_merge_nested(pipeline: dlt.Pipeline) -> None:
    """Nested rows of a replaced parent are replaced, and no temp table is left behind."""
    kwargs = {"table_name": "t", "write_disposition": "merge", "primary_key": "id"}
    _run(pipeline, [{"id": 1, "tags": ["x", "y"]}, {"id": 2, "tags": ["p"]}], **kwargs)
    _run(pipeline, [{"id": 2, "tags": ["q", "r"]}, {"id": 3, "tags": ["s"]}], **kwargs)

    assert _values(pipeline, "t__tags") == ["q", "r", "s", "x", "y"]
    staging_tables = _query(
        pipeline,
        "SELECT table_name FROM information_schema.tables"
        f" WHERE table_schema = '{pipeline.dataset_name}_staging'",
    )
    leftovers = [name for (name,) in staging_tables if "_delete_" in name or "_insert_" in name]
    assert leftovers == []


def test_merge_nested_hard_delete(pipeline: dlt.Pipeline) -> None:
    @dlt.resource(
        name="t",
        write_disposition="merge",
        primary_key="id",
        columns={"deleted": {"hard_delete": True, "data_type": "bool"}},
    )
    def resource(data: List[Dict[str, Any]]) -> Iterator[List[Dict[str, Any]]]:
        yield data

    _run(
        pipeline,
        resource(
            [{"id": 1, "deleted": False, "tags": ["a"]}, {"id": 2, "deleted": False, "tags": ["b"]}]
        ),
    )
    _run(
        pipeline,
        resource(
            [{"id": 1, "deleted": True, "tags": ["a"]}, {"id": 3, "deleted": False, "tags": ["c"]}]
        ),
    )

    assert _rows(pipeline, "t", "id") == [(2,), (3,)]
    assert _values(pipeline, "t__tags") == ["b", "c"]


def test_merge_nested_merge_key(pipeline: dlt.Pipeline) -> None:
    def resource(data: List[Dict[str, Any]]) -> Any:
        return dlt.resource(data, name="t", write_disposition="merge", merge_key="day")

    _run(
        pipeline, resource([{"day": 1, "id": 1, "tags": ["a"]}, {"day": 2, "id": 2, "tags": ["b"]}])
    )
    _run(pipeline, resource([{"day": 1, "id": 3, "tags": ["c"]}]))

    assert _rows(pipeline, "t", "day, id") == [(1, 3), (2, 2)]
    assert _values(pipeline, "t__tags") == ["b", "c"]


def test_merge_rerun_converges(pipeline: dlt.Pipeline) -> None:
    kwargs = {"table_name": "t", "write_disposition": "merge", "primary_key": "id"}
    _run(pipeline, [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}], **kwargs)
    _run(pipeline, [{"id": 2, "name": "b2"}, {"id": 3, "name": "c"}], **kwargs)

    _rerun_merge_sql(pipeline, ["t"])

    assert _rows(pipeline, "t", "id, name") == [(1, "a"), (2, "b2"), (3, "c")]


def test_merge_nested_rerun_converges(pipeline: dlt.Pipeline) -> None:
    kwargs = {"table_name": "t", "write_disposition": "merge", "primary_key": "id"}
    _run(pipeline, [{"id": 1, "tags": ["a"]}, {"id": 2, "tags": ["b"]}], **kwargs)
    _run(pipeline, [{"id": 2, "tags": ["b2", "b3"]}], **kwargs)

    _rerun_merge_sql(pipeline, ["t", "t__tags"])

    assert _rows(pipeline, "t", "id") == [(1,), (2,)]
    assert _values(pipeline, "t__tags") == ["a", "b2", "b3"]


def test_scd2(pipeline: dlt.Pipeline) -> None:
    _run(
        pipeline,
        [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],
        table_name="t",
        write_disposition=SCD2,
    )
    _run(
        pipeline,
        [{"id": 1, "name": "a"}, {"id": 2, "name": "b2"}],
        table_name="t",
        write_disposition=SCD2,
    )

    assert _rows(pipeline, "t", "id, name, _dlt_valid_to IS NULL") == [
        (1, "a", True),
        (2, "b", False),
        (2, "b2", True),
    ]


def test_scd2_compound_merge_key(pipeline: dlt.Pipeline) -> None:
    def resource(data: List[Dict[str, Any]]) -> Any:
        return dlt.resource(data, name="t", write_disposition=SCD2, merge_key=["k1", "k2"])

    _run(pipeline, resource([{"k1": 1, "k2": "x", "v": 1}, {"k1": 2, "k2": "y", "v": 1}]))
    _run(pipeline, resource([{"k1": 1, "k2": "x", "v": 2}]))

    assert _rows(pipeline, "t", "k1, v, _dlt_valid_to IS NULL") == [
        (1, 1, False),
        (1, 2, True),
        (2, 1, True),
    ]


def test_scd2_nested(pipeline: dlt.Pipeline) -> None:
    _run(
        pipeline,
        [{"id": 1, "tags": ["a"]}, {"id": 2, "tags": ["b"]}],
        table_name="t",
        write_disposition=SCD2,
    )
    _run(
        pipeline,
        [{"id": 1, "tags": ["a"]}, {"id": 2, "tags": ["b2"]}],
        table_name="t",
        write_disposition=SCD2,
    )

    assert _rows(pipeline, "t", "id, _dlt_valid_to IS NULL") == [(1, True), (2, False), (2, True)]
    assert _values(pipeline, "t__tags") == ["a", "b", "b2"]


@pytest.mark.skipif(
    Version(dlt.__version__) < Version("1.18"),
    reason="dlt < 1.18 cannot generate scd2 SQL outside a running load",
)
def test_scd2_rerun_converges(pipeline: dlt.Pipeline) -> None:
    first = {**SCD2, "boundary_timestamp": "2026-09-01T00:00:00+00:00"}
    second = {**SCD2, "boundary_timestamp": "2026-09-02T00:00:00+00:00"}
    _run(
        pipeline,
        [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],
        table_name="t",
        write_disposition=first,
    )
    _run(
        pipeline,
        [{"id": 1, "name": "a"}, {"id": 2, "name": "b2"}],
        table_name="t",
        write_disposition=second,
    )

    _rerun_merge_sql(pipeline, ["t"])

    assert _rows(pipeline, "t", "id, name, _dlt_valid_to IS NULL") == [
        (1, "a", True),
        (2, "b", False),
        (2, "b2", True),
    ]


@pytest.mark.parametrize("strategy", ["upsert", "insert-only"])
def test_merge_strategy_refused(pipeline: dlt.Pipeline, strategy: str) -> None:
    """Strategies CrateDB cannot run fail before anything is loaded."""
    if strategy not in MERGE_STRATEGIES:
        pytest.skip(f"dlt {dlt.__version__} has no `{strategy}` merge strategy")
    with pytest.raises(PipelineStepFailed) as excinfo:
        pipeline.run(
            [{"id": 1}],
            table_name="t",
            write_disposition={"disposition": "merge", "strategy": strategy},
            primary_key="id",
        )

    assert excinfo.value.step == "extract"
    cause: Any = excinfo.value
    while cause is not None and not isinstance(cause, DestinationCapabilitiesException):
        cause = cause.__cause__ or cause.__context__
    assert cause is not None
    assert f"`{strategy}` merge strategy not supported" in str(cause)


def test_refresh_drop_resources(pipeline: dlt.Pipeline) -> None:
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


def test_refresh_with_missing_staging_version_table(
    pipeline: dlt.Pipeline, dataset_name: str
) -> None:
    """`refresh="drop_resources"` must not crash when the staging `_dlt_version` is gone.

    Secondary symptom of GH-14: a staging dataset can look initialized (our `_placeholder`
    table) while `_dlt_version` is gone — the partial state ingestr's ephemeral jobs leave.
    dlt then deletes from a missing `_dlt_version` and used to abort the load.
    """

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
