import dataclasses
from typing import Final

from dlt.common.configuration import configspec
from dlt.common.configuration.exceptions import ConfigurationValueError
from dlt.destinations.impl.postgres.configuration import (
    PostgresClientConfiguration,
    PostgresCredentials,
)


@configspec(init=False)
class CrateDbCredentials(PostgresCredentials):
    drivername: Final[str] = dataclasses.field(  # type: ignore[misc]
        default="postgres", init=False, repr=False, compare=False
    )


# CrateDB does not support databases, just schemas.
# In dlt, schemas are conveyed by `dataset_name`?
del CrateDbCredentials.__dataclass_fields__["database"]


@configspec
class CrateDbClientConfiguration(PostgresClientConfiguration):
    destination_type: Final[str] = dataclasses.field(  # type: ignore[misc]
        default="cratedb", init=False, repr=False, compare=False
    )
    credentials: CrateDbCredentials

    def data_location(self) -> str:
        """Returns host:port. CrateDB has no databases, so the address identifies the data.

        dlt calls this from 1.30 on. It raises and falls back to the default port by itself,
        because `_no_data_location()` and `DEFAULT_PORT` do not exist before 1.30.
        """
        if not self.credentials or not self.credentials.host:
            raise ConfigurationValueError(
                "dlt cannot determine the data location of destination"
                f" `{self.destination_type}`: the configuration has no host. A resolved"
                " configuration always identifies the data location it accesses."
            )
        port = self.credentials.port or 5432
        return f"{self.credentials.host}:{port}"
