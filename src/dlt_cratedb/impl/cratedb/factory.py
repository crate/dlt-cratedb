from copy import deepcopy
from typing import TYPE_CHECKING, Any, Dict, List, Type

from dlt.common.destination import Destination, DestinationCapabilitiesContext
from dlt.common.destination.typing import PreparedTableSchema
from dlt.common.schema.typing import TColumnSchema
from dlt.destinations.impl.postgres.factory import PostgresTypeMapper, postgres

from dlt_cratedb.impl.cratedb.configuration import CrateDbClientConfiguration
from dlt_cratedb.impl.cratedb.utils import escape_cratedb_literal

if TYPE_CHECKING:
    from dlt_cratedb.impl.cratedb.cratedb import CrateDbClient


class CrateDbTypeMapper(PostgresTypeMapper):
    """
    Adjust type mappings for CrateDB.

    - CrateDB uses `object(dynamic)` instead of `json` or `jsonb`.
    - CrateDB does not support `timestamp(6) without time zone`.
    - CrateDB does not support `time` for storing.
    - CrateDB does not support `binary` or `bytea`.
    """

    def __new__(cls, *args: List[Any], **kwargs: Dict[str, Any]) -> "CrateDbTypeMapper":
        cls.sct_to_unbound_dbt = deepcopy(PostgresTypeMapper.sct_to_unbound_dbt)
        cls.sct_to_unbound_dbt["json"] = "object(dynamic)"
        cls.sct_to_unbound_dbt["binary"] = "text"

        cls.sct_to_dbt = deepcopy(PostgresTypeMapper.sct_to_dbt)
        cls.sct_to_dbt["timestamp"] = "timestamp with time zone"
        del cls.sct_to_dbt["time"]

        cls.dbt_to_sct = deepcopy(PostgresTypeMapper.dbt_to_sct)
        cls.dbt_to_sct["jsonb"] = "object(dynamic)"  # type: ignore[assignment]
        cls.dbt_to_sct["bytea"] = "text"

        return super().__new__(cls)

    def to_db_datetime_type(
        self,
        column: TColumnSchema,
        table: PreparedTableSchema = None,
    ) -> str:
        """
        CrateDB does not support `timestamp(6) without time zone`.
        To not render the SQL clause like this, nullify the `precision` attribute.
        """
        column["precision"] = None
        return super().to_db_datetime_type(column, table)


class cratedb(postgres, Destination[CrateDbClientConfiguration, "CrateDbClient"]):
    spec = CrateDbClientConfiguration  # type: ignore[assignment]

    def _raw_capabilities(self) -> DestinationCapabilitiesContext:
        """
        Tune down capabilities for CrateDB.
        """
        caps = super()._raw_capabilities()

        # CrateDB does not support transactions.
        caps.supports_transactions = False
        caps.supports_ddl_transactions = False

        # CrateDB does not support `TRUNCATE TABLE`, use `DELETE FROM` instead.
        caps.supports_truncate_command = False

        # CrateDB's type mapping needs adjustments compared to PostgreSQL.
        caps.type_mapper = CrateDbTypeMapper

        # TODO: Provide a dedicated dialect for SQLGlot.
        caps.sqlglot_dialect = "postgres"

        # CrateDB needs a slightly adjusted escaping of literals.
        # TODO: Escaping might need further adjustments, to be explored using integration tests.
        caps.escape_literal = escape_cratedb_literal

        # CrateDB does not support direct data loading using advanced formats.
        # TODO: Explore adding more formats for staged imports.
        caps.preferred_loader_file_format = "insert_values"
        caps.supported_loader_file_formats = ["insert_values"]
        caps.loader_file_format_selector = None

        # PostgreSQL uses 32 MB SQL buffer.
        # Problem: That makes CrateDB crash and dump its heap, also with 16 MB.
        #          java.lang.OutOfMemoryError: Java heap space

        # Data source: 5x this resource == 500.000 records.
        # https://cdn.crate.io/downloads/datasets/cratedb-datasets/cloud-tutorials/devices_readings.json.gz
        # Advise: Avoid gc thrashing.
        # [gc][93] overhead, spent [682ms] collecting in the last [1.2s]

        #  2 MB => 1m26s (no gc thrashing)
        #  4 MB => 1m18s (no gc thrashing)
        #  6 MB => 1m19s (gc thrashing)
        caps.max_query_length = 4 * 1024 * 1024
        caps.is_max_query_length_in_bytes = True

        return caps

    @property
    def client_class(self) -> Type["CrateDbClient"]:
        """
        Provide a different client for CrateDB.
        """
        from dlt_cratedb.impl.cratedb.cratedb import CrateDbClient

        return CrateDbClient


cratedb.register()
