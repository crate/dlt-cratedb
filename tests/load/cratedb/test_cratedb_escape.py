"""
Literal escaping for CrateDB's `insert_values` loads.

dlt splits a load file into statements line by line, so every rendered row has to stay on
one line: strings containing newlines are rendered as escape string literals (`E'...'`).
"""

import uuid
from typing import Any, Dict, List

import dlt
import pytest

import dlt_cratedb  # noqa: F401  -- registers `dlt.destinations.cratedb`
from dlt_cratedb.impl.cratedb.configuration import CrateDbCredentials
from dlt_cratedb.impl.cratedb.utils import escape_cratedb_literal

# Values CrateDB's escape string parser gets wrong when escaped the PostgreSQL way,
# next to the ones that need escaping at all.
TRICKY_STRINGS = [
    "plain",
    "L'Aupillon",
    "a'b",
    "'",
    "''",
    "back\\slash",
    "trailing backslash\\",
    "\\",
    "\\'",
    "\\x27",
    "\\12",
    "line\nbreak",
    "windows\r\nline",
    "carriage\rreturn",
    "tab\there",
    "ünïcödé ✓",
]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("plain", "E'plain'"),
        ("L'Aupillon", "E'L\\'Aupillon'"),
        ("line\nbreak", "E'line\\nbreak'"),
        ("windows\r\nline", "E'windows\\r\\nline'"),
        ("back\\slash", "E'back\\x5cslash'"),
        ("trailing\\", "E'trailing\\x5c'"),
    ],
)
def test_escape_string(value: str, expected: str) -> None:
    assert escape_cratedb_literal(value) == expected


def test_escape_object() -> None:
    # `json.dumps` already escapes newlines and backslashes, and the literal escapes its output.
    rendered = escape_cratedb_literal({"text": "it's", "path": "C:\\", "lines": ["a\nb"]})
    assert rendered == (
        """E'{"text": "it\\'s", "path": "C:\\x5c\\x5c", "lines": ["a\\x5cnb"]}'::OBJECT(DYNAMIC)"""
    )


def _pipeline(credentials: CrateDbCredentials, **destination_kwargs: Any) -> dlt.Pipeline:
    dataset_name = "test_escape_" + uuid.uuid4().hex[:12]
    return dlt.pipeline(
        pipeline_name="test_cratedb_escape_" + dataset_name,
        destination=dlt.destinations.cratedb(credentials=credentials, **destination_kwargs),
        dataset_name=dataset_name,
        dev_mode=False,
    )


def _texts(pipeline: dlt.Pipeline, table_name: str) -> Dict[int, str]:
    with pipeline.sql_client() as client:
        qualified = client.make_qualified_table_name(table_name)
        client.execute_sql(f"REFRESH TABLE {qualified}")
        with client.execute_query(f"SELECT id, text FROM {qualified}") as cur:
            return {row[0]: row[1] for row in cur.fetchall()}


def test_round_trip_strings_and_objects(credentials: CrateDbCredentials) -> None:
    pipeline = _pipeline(credentials)
    rows: List[Dict[str, Any]] = [
        {"id": i, "text": value, "data": {"value": value, "list": [value]}}
        for i, value in enumerate(TRICKY_STRINGS)
    ]

    info = pipeline.run(rows, table_name="tricky", columns={"data": {"data_type": "json"}})
    assert not info.has_failed_jobs

    assert _texts(pipeline, "tricky") == dict(enumerate(TRICKY_STRINGS))
    # Read the array element as a scalar.
    with pipeline.sql_client() as client:
        qualified = client.make_qualified_table_name("tricky")
        with client.execute_query(
            f"SELECT id, data['value'], data['list'][1] FROM {qualified}"
        ) as cur:
            objects = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
    assert objects == {i: (value, value) for i, value in enumerate(TRICKY_STRINGS)}


def test_multiline_strings_span_several_statements(credentials: CrateDbCredentials) -> None:
    """
    dlt reads `max_query_length // 2` characters per statement and completes the
    statement up to the next newline. With newlines left raw inside string values,
    that cut used to land inside a string, and the load failed with a `SyntaxError`.
    """
    pipeline = _pipeline(credentials, max_query_length=16 * 1024)
    text = "a line of text\n" * 60
    rows = [{"id": i, "text": text} for i in range(100)]

    info = pipeline.run(rows, table_name="multiline")
    assert not info.has_failed_jobs

    assert _texts(pipeline, "multiline") == dict.fromkeys(range(100), text)
