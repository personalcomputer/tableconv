import os

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "tableconv")


def get_config_filepath(key: str) -> str:
    return os.path.join(CONFIG_DIR, key)


def get_config(key: str) -> str | None:
    config_file = get_config_filepath(key)
    if not os.path.exists(config_file):
        return None
    with open(config_file) as f:
        value = f.read().strip()
    return value or None


def set_config(key: str, value: str) -> int:
    config_file = get_config_filepath(key)
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    with open(config_file, "w") as f:
        return f.write(value)
