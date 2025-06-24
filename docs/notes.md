# CrateDB destination adapter notes

```python
# Converge PostgreSQLClient to SqlalchemyClient.
creds = self.sql_client.credentials
sa_sql_client = SqlalchemyClient(
    dataset_name=self.sql_client.dataset_name,
    staging_dataset_name=self.sql_client.staging_dataset_name,
    credentials=SqlalchemyCredentials(
        connection_string=f"crate://{creds.username}:{creds.password}@{creds.host}:4200",
    ),
    capabilities=self.sql_client.capabilities,
)
```

```python
class CrateDbClient:

    def _row_to_schema_info2(self, query: str, *args: Any) -> StorageSchemaInfo:
        """
        If there's no dataset/schema, return `None`.
        """
        try:
            return super()._row_to_schema_info(query, *args)
        except Exception as ex:
            if self._is_error_schema_unknown(ex):
                return None
            raise

    def get_stored_state2(self, pipeline_name: str) -> StateInfo:
        try:
            return super().get_stored_state(pipeline_name=pipeline_name)
        except Exception as ex:
            if self._is_error_schema_unknown(ex):
                return None
            raise

    def update_stored_schema2(
        self,
        only_tables: Iterable[str] = None,
        expected_update: TSchemaTables = None,
    ) -> Optional[TSchemaTables]:
        """
        CrateDB knows schemas, but does not provide `CREATE SCHEMA ...`.
        Instead, schemas are created transparently.
        This goes south if frameworks a) expect to _use_ `CREATE SCHEMA ...`,
        and still fail if we make it a no-op, because `information_schema`
        tables still don't know anything about it.
        """
        try:
            result = super().update_stored_schema(only_tables, expected_update)
        except Exception as ex:
            return None
        dlt_table_names = [
            self.sql_client.make_qualified_table_name(self.schema.loads_table_name),
            self.sql_client.make_qualified_table_name(self.schema.state_table_name),
            self.sql_client.make_qualified_table_name(self.schema.version_table_name),
        ]
        for table_name in dlt_table_names:
            try:
                self.sql_client.execute_sql(f"REFRESH TABLE {table_name}")
            except Exception as ex:
                if self._is_error_relation_unknown(ex):
                    continue
                raise
        return result

    def _is_error_relation_unknown(self, exception: Exception) -> bool:
        """
        CrateDB raises `Schema 'testdrive' unknown` errors when accessing schemas not including any tables yet.

        dlt.destinations.exceptions.DatabaseUndefinedRelation: Relation 'testdrive_staging._dlt_loads' unknown
        """
        if not isinstance(exception, (psycopg2.errors.UndefinedTable, dlt.destinations.exceptions.DatabaseUndefinedRelation)):
            return False
        msg = str(exception)
        if "Relation" in msg and "unknown" in msg:
            return True
        return False

    def _is_error_schema_unknown(self, exception: Exception) -> bool:
        """
        CrateDB raises `Schema 'testdrive' unknown` errors when accessing schemas not including any tables yet.

        psycopg2.errors.InternalError_: Schema 'testdrive_staging' unknown
        dlt.destinations.exceptions.DatabaseTransientException: Schema 'testdrive_staging' unknown

        a) Try to ignore that.
        b) TODO: Refactor to synthesize an empty result, see `job_client_impl.get_stored_state`.
        c) Resolve in CrateDB.
        """
        if not isinstance(exception, (psycopg2.errors.InternalError_, dlt.destinations.exceptions.DatabaseTransientException)):
            return False
        error_message = str(exception)
        #print("error_message:", error_message)
        if "Schema" in error_message and "unknown" in error_message:
            return True
        return False
```
