from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    app_username: str
    app_password: str
    db_path: str = "/data/app.db"
    app_host: str = "0.0.0.0"
    app_port: int = 8088

    model: str = "all_coding"
    openai_base_url: str = "https://9router.arbeitermili.eu/v1"
    openai_api_key: str | None = None
    openai_timeout_seconds: int = 30

    mcp_server_url: str = "https://haimcp.arbeitermili.eu/mcp/cms1vfcpi00042bs248msptyv"
    mcp_api_key: str | None = None
    mcp_auth_header: str = "Authorization"
    mcp_auth_scheme: str = "Bearer"
    mcp_transport: str = "streamable_http"

    fhem_url: str | None = None
    fhem_username: str | None = None
    fhem_password: str | None = None
    fhem_verify_tls: bool = True

    approval_ttl_seconds: int = 120
    max_tool_iterations: int = 8
    max_request_bytes: int = 65536

    telegram_bot_token: str | None = None
    telegram_allowed_user_ids: tuple[int, ...] = ()


READ_ONLY_ALLOWLIST = {
    "fhem_get_reading",
    "fhem_list_devices",
    "fhem_search",
    "fhem_list_readings",
    "fhem_get_state",
    "fhem_get_device",
    "fhem_room_list",
    "fhem_list",
    "fhem_get",
}


MUTATION_KEYWORDS = (
    "set",
    "attr",
    "define",
    "delete",
    "raw",
    "set_multiple",
)


def load_settings() -> Settings:
    app_username = os.getenv("APP_USERNAME", "").strip()
    app_password = os.getenv("APP_PASSWORD", "").strip()
    if not app_username or not app_password:
        raise ValueError("APP_USERNAME und APP_PASSWORD müssen gesetzt sein.")

    allowed_ids_raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
    allowed_ids = tuple(
        int(part.strip())
        for part in allowed_ids_raw.split(",")
        if part.strip()
    )

    return Settings(
        app_username=app_username,
        app_password=app_password,
        db_path=os.getenv("DB_PATH", "/data/app.db"),
        app_host=os.getenv("APP_HOST", "0.0.0.0"),
        app_port=_env_int("PORT", 8088),
        model=os.getenv("MODEL", "all_coding"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://9router.arbeitermili.eu/v1"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_timeout_seconds=_env_int("OPENAI_TIMEOUT_SECONDS", 30),
        mcp_server_url=os.getenv("MCP_SERVER_URL", "https://haimcp.arbeitermili.eu/mcp/cms1vfcpi00042bs248msptyv"),
        mcp_api_key=os.getenv("MCP_API_KEY"),
        mcp_auth_header=os.getenv("MCP_AUTH_HEADER", "Authorization"),
        mcp_auth_scheme=os.getenv("MCP_AUTH_SCHEME", "Bearer"),
        mcp_transport=os.getenv("MCP_TRANSPORT", "streamable_http"),
        fhem_url=os.getenv("FHEM_URL"),
        fhem_username=os.getenv("FHEM_USERNAME"),
        fhem_password=os.getenv("FHEM_PASSWORD"),
        fhem_verify_tls=_env_bool("FHEM_VERIFY_TLS", True),
        approval_ttl_seconds=_env_int("APPROVAL_TTL_SECONDS", 120),
        max_tool_iterations=_env_int("MAX_TOOL_ITERATIONS", 8),
        max_request_bytes=_env_int("MAX_REQUEST_BYTES", 65536),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_allowed_user_ids=allowed_ids,
    )
