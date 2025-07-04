# ruff: noqa: S608
import logging
from typing import Any, Dict, List, Sequence

from dlt.common.destination import DestinationCapabilitiesContext
from dlt.common.destination.client import (
    FollowupJobRequest,
    LoadJob,
    PreparedTableSchema,
)
from dlt.common.schema import Schema, TColumnHint
from dlt.destinations.impl.postgres.postgres import PostgresClient
from dlt.destinations.insert_job_client import InsertValuesJobClient
from dlt.destinations.sql_client import SqlClientBase
from dlt.destinations.sql_jobs import SqlStagingReplaceFollowupJob

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
        CrateDB currently does not support "merge" followup jobs.
        -- https://github.com/crate/dlt-cratedb/issues/6

        Workaround: Redirect the "merge" job to use a "replace" job instead.
        """
        return [CrateDbStagingReplaceJob.from_table_chain(table_chain, self.sql_client)]

    def complete_load(self, load_id: str) -> None:
        """
        Intercept to invoke a `REFRESH TABLE ...` statement.
        """
        result = super().complete_load(load_id=load_id)
        table_name = self.sql_client.make_qualified_table_name(self.schema.loads_table_name)
        self.sql_client.execute_sql(f"REFRESH TABLE {table_name}")
        return result

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
        Intercept to invoke a `REFRESH TABLE ...` statement.
        """
        result = super()._delete_schema_in_storage(schema=schema)
        table_name = self.sql_client.make_qualified_table_name(self.schema.version_table_name)
        self.sql_client.execute_sql(f"REFRESH TABLE {table_name}")
        return result
