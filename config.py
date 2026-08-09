import os
DEFAULTS = {
    "host": "0.0.0.0",
    "port": 8080,
    "logfile": None,
    "database_folder": "data",
    "secret_key": "auditon-secret-key-change-me-in-production",
    "session_timeout_days": 7,
}
CONFIG_PATHS = [
    os.path.join(os.path.dirname(__file__), "auditon.conf"),
    "/etc/auditon/auditon.conf",
    os.environ.get("AUDITON_CONFIG", ""),
]
def load_config():
    config = dict(DEFAULTS)
    for path in CONFIG_PATHS:
        if path and os.path.isfile(path):
            _load_from_file(config, path)
            break
    _load_from_env(config)
    config["port"] = int(config["port"])
    config["session_timeout_days"] = int(config["session_timeout_days"])
    return config
def _load_from_file(config, path):
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip().lower()
                value = value.strip().strip('"').strip("'")
                if key in DEFAULTS:
                    config[key] = value.strip() if value.strip() else DEFAULTS[key]
def _load_from_env(config):
    env_map = {
        "AUDITON_HOST": "host",
        "AUDITON_PORT": "port",
        "AUDITON_LOGFILE": "logfile",
        "AUDITON_DATABASE_FOLDER": "database_folder",
        "AUDITON_SECRET_KEY": "secret_key",
        "AUDITON_SESSION_TIMEOUT_DAYS": "session_timeout_days",
    }
    for env_var, config_key in env_map.items():
        value = os.environ.get(env_var)
        if value is not None:
            config[config_key] = value
def save_config(config_dict):
    path = os.path.join(os.path.dirname(__file__), "auditon.conf")
    with open(path, "w") as f:
        for key in list(DEFAULTS.keys()) + ["secret_key"]:
            val = config_dict.get(key, DEFAULTS.get(key, ""))
            if val is not None:
                f.write(f"{key} = {val}\n")
CONFIG = load_config()