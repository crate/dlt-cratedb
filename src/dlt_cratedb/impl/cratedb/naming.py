from dlt.common.normalizers.naming.snake_case import NamingConvention as SnakeCaseNamingConvention

from dlt_cratedb.impl.cratedb.utils import RESERVED_SYSTEM_COLUMNS

# The escaped form of each reserved name, e.g. `_id` -> `__id`. Used to keep the
# rename idempotent under `normalize_path` (see `normalize_path` below).
ESCAPED_SYSTEM_COLUMNS = frozenset("_" + name for name in RESERVED_SYSTEM_COLUMNS)


class NamingConvention(SnakeCaseNamingConvention):
    """
    Snake-case naming, with a CrateDB twist: rename columns that collide with
    CrateDB's reserved system column names by prepending an underscore.

    MongoDB stamps every document with a top-level `_id`, and CrateDB reserves
    `_id` (and a handful of others in RESERVED_SYSTEM_COLUMNS), so a plain load fails with::

        InvalidColumnNameException["_id" conflicts with system column]

    Renaming `_id` -> `__id` sidesteps the conflict (this matches the convention
    CrateDB Toolkit's native MongoDB adapter already uses). dlt records the
    *normalized* name in its own schema, so the rewrite is consistent end-to-end
    (DDL + INSERT) and needs no reverse mapping on read.

    @see: https://github.com/crate/dlt-cratedb/issues/19
    """

    def normalize_identifier(self, identifier: str) -> str:
        norm = super().normalize_identifier(identifier)
        if norm in RESERVED_SYSTEM_COLUMNS:
            norm = "_" + norm
        return norm

    def normalize_path(self, path: str) -> str:
        # Short-circuit escaped top-level names to keep the rewrite idempotent.
        # `__` is dlt's nested-path separator, so `__id` fed through `break_path`
        # would split to `id`. dlt re-normalizes compound hints (e.g. `primary_key`)
        # this way. Only top-level columns matter; CrateDB enforces reservation there.
        if path in ESCAPED_SYSTEM_COLUMNS:
            return path
        return super().normalize_path(path)
