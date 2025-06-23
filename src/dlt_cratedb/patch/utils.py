def info_schema_null_to_bool(v: str) -> bool:
    """Converts INFORMATION SCHEMA truth values to Python bool"""
    if v in ("NO", "0", False):
        return False
    elif v in ("YES", "1", True):
        return True
    raise ValueError(v)
