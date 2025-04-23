def strtobool(val: str) -> bool:
    TRUE_VALUES = {"t", "T", "y", "Y", "yes", "Yes", "YES", "true", "True", "TRUE", "on", "On", "ON", "1", 1}
    FALSE_VALUES = {"f", "F", "n", "N", "no", "No", "NO", "false", "False", "FALSE", "off", "Off", "OFF", "0", 0}
    if val in TRUE_VALUES:
        return True
    elif val in FALSE_VALUES:
        return False
    else:
        raise ValueError(f"Invalid boolean value: {val}")
