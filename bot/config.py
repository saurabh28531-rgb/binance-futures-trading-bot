import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env file into os.environ at import time
load_dotenv()


@dataclass(frozen=True)
class Config:
    """
    Immutable application configuration loaded from environment variables.

    frozen=True means no attribute can be changed after creation.
    This prevents any part of the code from accidentally modifying config.

    Attributes:
        api_key: Binance Demo Trading API key
        secret_key: Binance Demo Trading secret key
        base_url: Binance Futures Demo base URL
        request_timeout_connect: Seconds to wait for connection to establish
        request_timeout_read: Seconds to wait for API response
        max_retries: Maximum number of retry attempts on transient failures
        log_level: Logging level for console output
    """
    api_key: str
    secret_key: str
    base_url: str
    request_timeout_connect: float
    request_timeout_read: float
    max_retries: int
    log_level: str


def _get_required_env(key: str) -> str:
    """
    Read a required environment variable.

    Args:
        key: Environment variable name

    Returns:
        Value of the environment variable

    Raises:
        SystemExit: If the variable is missing or empty
    """
    value = os.environ.get(key, "").strip()
    if not value:
        print(
            f"\n❌ Missing required environment variable: {key}\n"
            f"   Please check your .env file against .env.example\n"
        )
        raise SystemExit(1)
    return value


def _load_config() -> Config:
    """
    Load and validate all configuration from environment variables.

    Returns:
        Fully validated immutable Config instance

    Raises:
        SystemExit: If any required variable is missing
    """
    return Config(
        api_key=_get_required_env("BINANCE_API_KEY"),
        secret_key=_get_required_env("BINANCE_SECRET_KEY"),
        base_url=_get_required_env("BINANCE_BASE_URL"),

        # Optional with sensible production defaults
        request_timeout_connect=float(os.environ.get("REQUEST_TIMEOUT_CONNECT", "5.0")),
        request_timeout_read=float(os.environ.get("REQUEST_TIMEOUT_READ", "10.0")),
        max_retries=max(1, int(os.environ.get("MAX_RETRIES", "3"))),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )


# Single config instance imported by all other modules
# This runs once when the module is first imported
config = _load_config()