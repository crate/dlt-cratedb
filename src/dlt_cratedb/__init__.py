import dlt.destinations

from dlt_cratedb.impl.cratedb.factory import cratedb
from dlt_cratedb.patch import activate_patch

activate_patch()

setattr(dlt.destinations, "cratedb", cratedb)
