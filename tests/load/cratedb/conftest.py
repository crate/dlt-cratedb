from typing import Iterator

import pytest
from dlt.common.configuration.container import Container
from dlt.common.destination import DestinationCapabilitiesContext

from dlt_cratedb.impl.cratedb.configuration import CrateDbCredentials


@pytest.fixture
def credentials() -> CrateDbCredentials:
    creds = CrateDbCredentials()
    creds.username = "crate"
    creds.password = ""
    creds.host = "localhost"
    return creds


@pytest.fixture(autouse=True)
def reset_capabilities_container() -> Iterator[None]:
    """Clear destination capabilities left injected in the global Container.

    Running a real pipeline injects CrateDB's `DestinationCapabilitiesContext` into the process-wide Container
    and never removes it. That leaks into later client builds: an explicit case-sensitive schema gets
    overridden by CrateDB's case-insensitive naming, making tests order-dependent (e.g.
    `test_create_table_case_sensitive` fails only after an integration test ran).
    We have to clear it around each test.
    """
    container = Container()
    if DestinationCapabilitiesContext in container:
        del container[DestinationCapabilitiesContext]
    yield
    if DestinationCapabilitiesContext in container:
        del container[DestinationCapabilitiesContext]
