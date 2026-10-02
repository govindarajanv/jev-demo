"""Configuration: environment variables, with an optional .env file.

Keys you export in the shell win over .env, so CI and one-off runs can
override a checked-in default without editing the file.
"""

import os

ENV_KEYS = (
    "TYPESAFE_BASE_URL",
    "TYPESAFE_API_KEY",
    "JEV_API_KEY",
    "JEV_MODEL",
    "JEV_TIMEOUT",
    "JEV_DECISION_LOG",
)


def parse_env(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def env_path() -> str:
    if os.environ.get("JEV_ENV_FILE"):
        return os.environ["JEV_ENV_FILE"]
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, ".env")


def load_env() -> str | None:
    """Fill missing keys from .env. Returns the path used, if any."""

    path = env_path()
    if not os.path.isfile(path):
        return None
    for key, value in parse_env(open(path, encoding="utf-8").read()).items():
        os.environ.setdefault(key, value)
    return path


DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-1.13.0"
DEFAULT_TIMEOUT = 30.0


def settings() -> tuple[str, str, str, float]:
    load_env()
    base_url = os.environ.get("TYPESAFE_BASE_URL") or DEFAULT_BASE_URL
    api_key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY", "")
    model = os.environ.get("JEV_MODEL") or DEFAULT_MODEL
    try:
        timeout = float(os.environ.get("JEV_TIMEOUT") or DEFAULT_TIMEOUT)
    except ValueError:
        raise SystemExit(f"JEV_TIMEOUT is not a number: {os.environ['JEV_TIMEOUT']!r}")
    return base_url, api_key, model, timeout