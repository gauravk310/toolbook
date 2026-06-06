import os
from pathlib import Path


def hello():
    return "Hello from Toolbook"


def add(a, b):
    return a + b


def get_token(token_name: str) -> str | None:
    """
    Get a secret token from os.environ or ~/.toolbook/.env.
    """
    # 1. Check os.environ first
    if token_name in os.environ:
        return os.environ[token_name]

    # 2. Fallback to reading ~/.toolbook/.env directly
    env_file = Path.home() / ".toolbook" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == token_name:
                    val = v.strip()
                    os.environ[k.strip()] = val  # Cache it
                    return val
    return None
