import json
from datetime import date, datetime, time
from typing import Any

from dlt.common.data_writers.escape import _escape_extended, _make_sql_escape_re

# CrateDB does not accept the original `{"'": "''", "\\": "\\\\", "\n": "\\n", "\r": "\\r"}`?
SQL_ESCAPE_DICT = {"'": "''"}
SQL_ESCAPE_RE = _make_sql_escape_re(SQL_ESCAPE_DICT)

# CrateDB reserves a fixed set of system column names. Defining a top-level column with
# one of these names fails with `InvalidColumnNameException[... conflicts with system column]`.
# This is an *exact* match, not a pattern: since CrateDB 6.2 (crate/crate#15161) the generic
# `_`-prefix restriction was lifted, so only these specific names remain reserved. Object
# sub-keys are unaffected. Source of truth: crate/crate `SysColumns.NAMES`.
# https://github.com/crate/crate/issues/15161
RESERVED_SYSTEM_COLUMNS = frozenset(
    {
        "_id",
        "_version",
        "_score",
        "_uid",
        "_doc",
        "_raw",
        "_seq_no",
        "_primary_term",
        "_tombstone",
        "_fetchid",
        "_docid",
    }
)


def _escape_extended_cratedb(v: str) -> str:
    """
    The best-practice escaper for CrateDB, discovered by trial-and-error.
    """
    return _escape_extended(v, prefix="'", escape_dict=SQL_ESCAPE_DICT, escape_re=SQL_ESCAPE_RE)


def escape_cratedb_literal(v: Any) -> Any:
    """
    Based on `escape_postgres_literal`, with a mix of `escape_redshift_literal`.

    CrateDB needs a slightly adjusted escaping of literals.
    Examples: "L'Aupillon" and "Pizzas d'Anarosa" from `sys.summits`.

    It possibly also doesn't support the `E'` prefix as employed by the PostgreSQL escaper?
    Fortunately, the Redshift escaper came to the rescue, providing a reasonable baseline.

    CrateDB also needs support when serializing container types ARRAY vs. OBJECT.
    """
    if isinstance(v, str):
        return _escape_extended_cratedb(v)
    if isinstance(v, (datetime, date, time)):
        return f"'{v.isoformat()}'"
    # CrateDB, when serializing from an incoming `json` or `jsonb` type, the type mapper
    # can't know about what's actually inside, so arrays need a special treatment.
    if isinstance(v, list):
        v = {"array": v}
    if isinstance(v, dict):
        return _escape_extended_cratedb(json.dumps(v)) + "::OBJECT(DYNAMIC)"
    if isinstance(v, bytes):
        return f"'\\x{v.hex()}'"
    if v is None:
        return "NULL"

    return str(v)
