from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

APP_NAME = 'check_manager'


def _is_windows() -> bool:
    return platform.system().lower().startswith('windows')


def _resolve_app_data_dir() -> Path:
    # Allow override for tests/support scenarios.
    override = os.getenv('CHECK_MANAGER_DATA_DIR', '').strip()
    if override:
        return Path(override).expanduser().resolve()

    if _is_windows():
        # In PyInstaller one-file mode the bundle is extracted to a temp directory,
        # and in one-folder mode it can run from an install directory. Keep writable
        # data in LocalAppData so it persists across launches in both modes.
        local_app_data = os.getenv('LOCALAPPDATA', '').strip()
        if local_app_data:
            base = Path(local_app_data)
        elif getattr(sys, 'frozen', False):
            user_profile = os.getenv('USERPROFILE', '').strip()
            base = Path(user_profile) / 'AppData' / 'Local' if user_profile else Path.home() / 'AppData' / 'Local'
        else:
            base = Path.home() / 'AppData' / 'Local'
        return base / APP_NAME

    xdg_data_home = os.getenv('XDG_DATA_HOME', '').strip()
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / '.local' / 'share'
    return base / APP_NAME


APP_DATA_DIR = _resolve_app_data_dir()

DB_PATH = APP_DATA_DIR / 'app_data.db'
EXPORT_DIR = APP_DATA_DIR / 'exports'
LOG_DIR = APP_DATA_DIR / 'logs'

APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)



def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, '').strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, '').strip().lower()
    if not raw:
        return default
    return raw in {'1', 'true', 'yes', 'on'}


AI_TIMEOUT_SEC = _env_int('AI_TIMEOUT_SEC', 10)
AI_HEALTHCHECK_TTL_SEC = _env_int('AI_HEALTHCHECK_TTL_SEC', 45)
AI_MAX_RETRIES = _env_int('AI_MAX_RETRIES', 4)
AI_RETRY_BACKOFF_SEC = _env_float('AI_RETRY_BACKOFF_SEC', 1.0)
AI_STARTUP_HEALTHCHECK = _env_bool('AI_STARTUP_HEALTHCHECK', False)
AI_AUTORECONNECT_ENABLED = _env_bool('AI_AUTORECONNECT_ENABLED', True)
AI_RECONNECT_INTERVAL_SEC = _env_float('AI_RECONNECT_INTERVAL_SEC', 2.0)
AI_RECONNECT_BACKOFF_MAX_SEC = _env_float('AI_RECONNECT_BACKOFF_MAX_SEC', 60.0)

# Local/offline monthly export automation settings.
AI_AUTO_MONTHLY_EXPORT_ENABLED = _env_bool('AI_AUTO_MONTHLY_EXPORT_ENABLED', True)
AI_AUTO_MONTHLY_EXPORT_FORMATS = os.getenv('AI_AUTO_MONTHLY_EXPORT_FORMATS', 'excel,pdf').strip()
AI_AUTO_MONTHLY_EXPORT_MONTH_OFFSET = _env_int('AI_AUTO_MONTHLY_EXPORT_MONTH_OFFSET', -1)

# Logging settings.
LOG_LEVEL = os.getenv('CHECK_MANAGER_LOG_LEVEL', 'INFO').strip()
