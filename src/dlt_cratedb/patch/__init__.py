from dlt_cratedb.patch.utils import info_schema_null_to_bool


def activate_patch() -> None:
    import dlt.destinations.job_client_impl
    import dlt.destinations.utils

    dlt.destinations.job_client_impl.info_schema_null_to_bool = info_schema_null_to_bool
    dlt.destinations.utils.info_schema_null_to_bool = info_schema_null_to_bool
