"""
Unit tests for the CrateDB naming convention that works around CrateDB's reserved
system column names (e.g. MongoDB's `_id`).

See: https://github.com/crate/dlt-cratedb/issues/19
"""

import pytest

from dlt_cratedb.impl.cratedb.naming import NamingConvention
from dlt_cratedb.impl.cratedb.utils import RESERVED_SYSTEM_COLUMNS


@pytest.fixture
def naming() -> NamingConvention:
    return NamingConvention()


def test_reserved_names_are_escaped(naming: NamingConvention) -> None:
    for name in RESERVED_SYSTEM_COLUMNS:
        assert naming.normalize_identifier(name) == "_" + name


def test_mongodb_id_is_escaped(naming: NamingConvention) -> None:
    assert naming.normalize_identifier("_id") == "__id"


@pytest.mark.parametrize(
    "name",
    [
        "_foo",  # single leading underscore but not reserved -> allowed since CrateDB 6.2
        "_dlt_id",  # dlt's own bookkeeping columns are not reserved
        "_dlt_load_id",
        "id",
        "name",
        "user_name",
    ],
)
def test_non_reserved_names_pass_through(naming: NamingConvention, name: str) -> None:
    assert naming.normalize_identifier(name) == name


def test_normalize_identifier_is_idempotent(naming: NamingConvention) -> None:
    once = naming.normalize_identifier("_id")
    assert naming.normalize_identifier(once) == once == "__id"


def test_normalize_path_is_idempotent(naming: NamingConvention) -> None:
    # `__` is dlt's nested-path separator; the escaped name must survive being fed
    # back through `normalize_path` (which dlt does for compound hints like
    # `primary_key`), otherwise `__id` would be split apart into `id`.
    once = naming.normalize_path("_id")
    assert once == "__id"
    assert naming.normalize_path(once) == "__id"
    assert naming.normalize_path(naming.normalize_path(once)) == "__id"
