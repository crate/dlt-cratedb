# ruff: noqa: S608
import logging
from typing import Any, Dict, List, Optional, Sequence

from dlt.common.destination import DestinationCapabilitiesContext
from dlt.common.destination.client import (
    FollowupJobRequest,
    LoadJob,
    PreparedTableSchema,
)
from dlt.common.schema import Schema, TColumnHint
from dlt.destinations.exceptions import DatabaseUndefinedRelation
from dlt.destinations.impl.postgres.postgres import PostgresClient
from dlt.destinations.insert_job_client import InsertValuesJobClient
from dlt.destinations.sql_client import SqlClientBase
from dlt.destinations.sql_jobs import SqlMergeFollowupJob, SqlStagingReplaceFollowupJob
from dlt.destinations.utils import get_deterministic_temp_table_name

from dlt_cratedb.impl.cratedb.configuration import CrateDbClientConfiguration
from dlt_cratedb.impl.cratedb.sql_client import CrateDbSqlClient

# FIXME: The `UNIQUE` constraint is dearly missing.
#        When loading data multiple times, duplicates will happen.
HINT_TO_CRATEDB_ATTR: Dict[TColumnHint, str] = {"unique": ""}


logger = logging.getLogger(__name__)


class CrateDbStagingReplaceJob(SqlStagingReplaceFollowupJob):
    @classmethod
    def generate_sql(
        cls,
        table_chain: Sequence[PreparedTableSchema],
        sql_client: SqlClientBase[Any],
    ) -> List[str]:
        """
        CrateDB uses `ALTER CLUSTER SWAP TABLE`.

        -- https://github.com/crate/crate/issues/14833
        """
        sql: List[str] = []
        for table in table_chain:
            with sql_client.with_staging_dataset():
                staging_table_name = sql_client.make_qualified_table_name(table["name"])
            table_name = sql_client.make_qualified_table_name(table["name"])
            sql.extend(
                (
                    # Drop destination table.
                    f"DROP TABLE IF EXISTS {table_name};",
                    # Recreate destination table, because `ALTER CLUSTER SWAP TABLE` needs it.
                    (
                        f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM"
                        f" {staging_table_name} WHERE 1 = 0;"
                    ),
                    # Move the staging table to the destination schema.
                    f"ALTER CLUSTER SWAP TABLE {staging_table_name} TO {table_name};",
                    # CrateDB needs to flush writes.
                    f"REFRESH TABLE {table_name};",
                    # Recreate staging table not needed with CrateDB, because
                    # `ALTER CLUSTER SWAP TABLE` does not remove the source table.
                    (
                        f"CREATE TABLE IF NOT EXISTS {staging_table_name} AS SELECT * FROM"
                        f" {table_name} WHERE 1 = 0;"
                    ),
                    f"REFRESH TABLE {staging_table_name};",
                )
            )
        return sql


class CrateDbMergeJob(SqlMergeFollowupJob):
    """
    Run dlt's `delete-insert` and `scd2` merge SQL on CrateDB.

    Overrides only the statements CrateDB cannot run as dlt emits them:

    - Queries see a table as of its last refresh, whichever connection wrote it,
      so staging, destination and temp tables are refreshed before they are read.
    - CrateDB cannot resolve the correlated `EXISTS` subquery dlt uses to select
      the rows to delete, and has no tuple `IN`.
      -- https://github.com/crate/crate/issues/18107
    - CrateDB has no temporary tables. Nested chains use regular tables in the
      staging dataset instead, dropped at the end of the job.
    - CrateDB 6.2 rejects the untyped `(SELECT NULL)` dlt orders by when
      deduplicating without a `dedup_sort` column.
      -- https://github.com/crate/dlt-cratedb/issues/7

    -- https://github.com/crate/dlt-cratedb/issues/6
    """

    @classmethod
    def generate_sql(
        cls,
        table_chain: Sequence[PreparedTableSchema],
        sql_client: SqlClientBase[Any],
    ) -> List[str]:
        """
        Refresh the destination tables, so the merged data is queryable when the load returns.
        """
        sql = super().generate_sql(table_chain, sql_client)
        for table in table_chain:
            sql.append(f"REFRESH TABLE {sql_client.make_qualified_table_name(table['name'])};")
        return sql

    @classmethod
    def _gen_table_setup_clauses(
        cls,
        table_chain: Sequence[PreparedTableSchema],
        sql_client: SqlClientBase[Any],
    ) -> List[str]:
        """
        Refresh staging and destination tables, so the merge sees the rows the load jobs
        just wrote to staging, and destination rows written moments ago.
        """
        table_names: List[str] = []
        for table in table_chain:
            table_names.extend(sql_client.get_qualified_table_names(table["name"]))
        return [f"REFRESH TABLE {', '.join(table_names)};"]

    @classmethod
    def _gen_key_table_clauses(
        cls, primary_keys: Sequence[str], merge_keys: Sequence[str]
    ) -> List[str]:
        """
        One non-correlated `IN` per key set, instead of dlt's correlated `EXISTS`.
        A compound key is compared as one expression, see `gen_concat_sql`.

        The returned templates carry `{d}` and `{s}` aliases and the `{staging}` table name.
        """
        return [
            f"{cls._gen_key_expr(keys, '{d}')} IN"
            f" (SELECT {cls._gen_key_expr(keys, '{s}')} FROM {{staging}} AS {{s}})"
            for keys in (primary_keys, merge_keys)
            if keys
        ]

    @classmethod
    def _gen_key_expr(cls, columns: Sequence[str], alias: str) -> str:
        qualified = [f"{alias}.{column}" for column in columns]
        if len(qualified) == 1:
            return qualified[0]
        return cls.gen_concat_sql(qualified)

    @classmethod
    def gen_key_table_clauses(  # type: ignore[override]
        cls,
        root_table_name: str,
        staging_root_table_name: str,
        *keys: Sequence[str],
        for_delete: bool,
    ) -> List[str]:
        """
        dlt >= 1.18 passes `primary_keys, merge_keys`. Older releases pass the clauses
        rendered by `_gen_key_table_clauses`.
        """
        key_clauses = cls._gen_key_table_clauses(*keys) if len(keys) == 2 else keys[0]
        condition = " OR ".join(
            clause.format(d="d", s="s", staging=staging_root_table_name) for clause in key_clauses
        )
        return [f"FROM {root_table_name} AS d WHERE {condition}"]

    @classmethod
    def gen_concat_sql(cls, columns: Sequence[str]) -> str:
        """
        Encode a compound key as one string, each part prefixed by its length.

        The length prefix keeps a value from forging a column boundary, so `('a:b', 'c')`
        and `('a', 'b:c')` stay distinct. `char_length(NULL)` and `|| NULL` are NULL, so a
        NULL key part never matches, the same result `=` gives on PostgreSQL. dlt's
        `CONCAT` reads NULL as an empty string.
        """
        return " || ".join(
            f"char_length({column}::TEXT)::TEXT || ':' || {column}::TEXT" for column in columns
        )

    @classmethod
    def default_order_by(cls) -> str:
        """
        CrateDB 6.2 cannot order by an untyped NULL.
        -- https://github.com/crate/dlt-cratedb/issues/7
        """
        return "(SELECT NULL::TEXT)"

    @classmethod
    def gen_merge_sql(
        cls,
        table_chain: Sequence[PreparedTableSchema],
        sql_client: SqlClientBase[Any],
    ) -> List[str]:
        """
        Drop the temp tables at the end. Only nested chains create them.
        """
        sql = super().gen_merge_sql(table_chain, sql_client)
        if len(table_chain) > 1:
            root_table_name = table_chain[0]["name"]
            for op in ("delete", "insert"):
                temp_table_name = cls._new_temp_table_name(root_table_name, op, sql_client)
                sql.append(f"DROP TABLE IF EXISTS {temp_table_name};")
        return sql

    @classmethod
    def _new_temp_table_name(cls, table_name: str, op: str, sql_client: SqlClientBase[Any]) -> str:
        """
        A regular table in the staging dataset, named deterministically, so a table left
        over by a failed load is dropped and recreated by the next one.
        """
        with sql_client.with_staging_dataset():
            return sql_client.make_qualified_table_name(
                cls._shorten_table_name(
                    get_deterministic_temp_table_name(table_name, op), sql_client
                )
            )

    @classmethod
    def _to_temp_table(  # type: ignore[override]
        cls,
        select_sql: str,
        temp_table_name: str,
        unique_column: str,
        sql_client: Optional[SqlClientBase[Any]] = None,
    ) -> str:
        """
        CrateDB has no temporary tables. Refresh the new table, so the statements
        consuming it see its rows.
        """
        return (
            f"DROP TABLE IF EXISTS {temp_table_name};\n"
            f"CREATE TABLE {temp_table_name} AS {select_sql};\n"
            f"REFRESH TABLE {temp_table_name};"
        )


class CrateDbClient(PostgresClient):
    def __init__(
        self,
        schema: Schema,
        config: CrateDbClientConfiguration,
        capabilities: DestinationCapabilitiesContext,
    ) -> None:
        sql_client = CrateDbSqlClient(
            config.normalize_dataset_name(schema),
            config.normalize_staging_dataset_name(schema),
            config.credentials,
            capabilities,
        )
        InsertValuesJobClient.__init__(self, schema, config, sql_client)
        self.config: CrateDbClientConfiguration = config
        self.sql_client: CrateDbSqlClient = sql_client
        self.active_hints = HINT_TO_CRATEDB_ATTR if self.config.create_indexes else {}
        self.type_mapper = self.capabilities.get_type_mapper()

    def create_load_job(
        self,
        table: PreparedTableSchema,
        file_path: str,
        load_id: str,
        restore: bool = False,
    ) -> LoadJob:
        """
        CrateDB only supports the "insert values" paradigm.
        """
        job = InsertValuesJobClient.create_load_job(self, table, file_path, load_id, restore)
        if job is not None:
            return job
        return None

    def _create_merge_followup_jobs(
        self, table_chain: Sequence[PreparedTableSchema]
    ) -> List[FollowupJobRequest]:
        """
        Merge with `CrateDbMergeJob`, which runs dlt's `delete-insert` and `scd2` SQL.
        -- https://github.com/crate/dlt-cratedb/issues/6
        """
        return [CrateDbMergeJob.from_table_chain(table_chain, self.sql_client)]

    def complete_load(self, load_id: str) -> None:
        """
        Intercept to invoke `REFRESH TABLE ...` statements.

        dlt restores pipeline state by joining `_dlt_pipeline_state` to `_dlt_loads`, so
        both have to show this load's rows before the next run reads them back. The state
        row is written before the load is marked complete, so its table is refreshed first:
        a reader that sees this load in `_dlt_loads` also sees its state.
        """
        self._refresh_state_table()
        result = super().complete_load(load_id=load_id)
        table_name = self.sql_client.make_qualified_table_name(self.schema.loads_table_name)
        self.sql_client.execute_sql(f"REFRESH TABLE {table_name}")
        return result

    def _refresh_state_table(self) -> None:
        """
        Refresh the pipeline state table, when this schema syncs state.

        The schema can list the table while the destination lacks it, for example after it
        was dropped by hand: dlt skips DDL for a schema version it already stored. A load
        that writes no new state row succeeded in that case before, so keep it succeeding.
        """
        if self.schema.state_table_name not in self.schema.tables:
            return
        table_name = self.sql_client.make_qualified_table_name(self.schema.state_table_name)
        try:
            self.sql_client.execute_sql(f"REFRESH TABLE {table_name}")
        except DatabaseUndefinedRelation:
            logger.debug("State table %s absent; nothing to refresh.", table_name)

    def _commit_schema_update(self, schema: Schema, schema_str: str) -> None:
        """
        Intercept to invoke a `REFRESH TABLE ...` statement.
        """
        result = super()._commit_schema_update(schema=schema, schema_str=schema_str)
        table_name = self.sql_client.make_qualified_table_name(self.schema.version_table_name)
        self.sql_client.execute_sql(f"REFRESH TABLE {table_name}")
        return result

    def _delete_schema_in_storage(self, schema: Schema) -> None:
        """
        Intercept to invoke a `REFRESH TABLE ...` statement, and tolerate a missing
        version table. (#14)
        """
        try:
            result = super()._delete_schema_in_storage(schema=schema)
        except DatabaseUndefinedRelation:
            logger.debug(
                "Version table %s absent while deleting schema %s; nothing to delete.",
                self.schema.version_table_name,
                schema.name,
            )
            return None
        table_name = self.sql_client.make_qualified_table_name(self.schema.version_table_name)
        self.sql_client.execute_sql(f"REFRESH TABLE {table_name}")
        return result
