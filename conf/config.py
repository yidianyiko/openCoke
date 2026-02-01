import json
import os
import re
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Pattern to match ${VAR_NAME} placeholders
ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand ${VAR_NAME} placeholders with environment variables."""
    if isinstance(value, str):

        def replace_env_var(match):
            var_name = match.group(1)
            env_value = os.getenv(var_name)
            if env_value is None:
                # Keep the placeholder if env var is not set
                return match.group(0)
            return env_value

        return ENV_VAR_PATTERN.sub(replace_env_var, value)
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    else:
        return value


def init_conf():
    conf = {}
    with open("conf/config.json", mode="r") as f:
        conf = json.load(f)

    # Expand environment variables in config values
    conf = _expand_env_vars(conf)

    env = os.getenv("env", "dev")
    # 定制化配置覆盖原配置
    server_conf = conf.get(env) or {}
    conf.update(server_conf)
    return conf


def save_config():
    """保存配置到文件"""
    with open("conf/config.json", mode="w", encoding="utf-8") as f:
        json.dump(CONF, f, ensure_ascii=False, indent=4)


CONF = init_conf()


def get_config() -> dict:
    """Get the global configuration dictionary."""
    return CONF
