# Check Manager

A desktop finance operations app for:
- cheque lifecycle tracking
- registration and income management
- expense tracking and categorization
- backup/restore of local data
- local (offline) analytics and report generation

The UI is built with `PySide6`, data is stored in local `SQLite`, and the app is designed to run safely both from source and as a Windows standalone executable.

## Key Features

- **Cheque management**: status workflow, due dates, filtering, and table operations.
- **Registrations and income**: customer records, payments, linked cheque entries.
- **Expense management**: categorized expenses with payment method tracking.
- **Exports**: Excel and PDF output for operational and analytics reports.
- **Offline analytics**: deterministic local analysis engine (no external API required).
- **Simple backup/restore**:
  - manual one-click backup to any folder
  - manual restore from any `.db` backup file
  - timestamped naming with collision-safe suffixing (`_01`, `_02`, ...)

## Technology Stack

- Python 3.10+
- PySide6 + qt-material
- SQLite
- openpyxl
- reportlab
- jdatetime
- requests (used by holiday utility layer)

## Project Layout

- `main.py` - app entry point and Qt application bootstrap
- `app_context.py` - dependency wiring and startup lifecycle
- `config.py` - path resolution and environment-based runtime config
- `core/logging_config.py` - global logging setup (rotation + hooks)
- `core/error_handler.py` - centralized user-friendly error handling
- `database/db.py` - schema, migrations, and low-level DB helpers
- `services/` - business logic (checks, expenses, registrations, backup, analytics, export)
- `ui/` - windows, pages, dialogs, and widgets
- `tests/` - unittest-based test suite

## Quick Start

### 1) Create a virtual environment

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Run

```bash
python main.py
```

## Testing

Run all tests:

```bash
python -m unittest discover -v
```

Run backup tests:

```bash
python -m unittest tests.test_backup_service -v
```

## Data Location

The app does **not** use a database inside the project folder.  
It always uses `%LOCALAPPDATA%\check_manager\app_data.db` on Windows (unless overridden by env var).

### Windows (real active paths)

- App data root: `%LOCALAPPDATA%\check_manager`
- Active database: `%LOCALAPPDATA%\check_manager\app_data.db`
- Logs directory: `%LOCALAPPDATA%\check_manager\logs`
- Exports directory: `%LOCALAPPDATA%\check_manager\exports`

### Linux

- App data root: `${XDG_DATA_HOME:-~/.local/share}/check_manager`

### Why deleting project `.db` does nothing

If you delete `app_data.db` from the repository/project directory, the app behavior will not change, because the running app reads/writes:

- `%LOCALAPPDATA%\check_manager\app_data.db` on Windows

So only the AppData DB is the active DB used at runtime.

Override root data directory (for testing/support):

- `CHECK_MANAGER_DATA_DIR`

## Logging and Error Handling

- Application logging is centralized and configured once at startup.
- Log files are written to the app user directory: `logs/application.log`.
- Rotation is enabled (`2 MB` per file, `12` backups).
- Unhandled exceptions (main thread and worker threads) are logged with full stack trace.
- UI-level exceptions are caught by a guarded Qt application wrapper, so unexpected dialog/form errors do not crash the whole app.
- User-facing errors are localized and friendly; internal stack traces remain available in logs for debugging.

## Configuration (Environment Variables)

### General

| Variable | Default | Description |
|---|---|---|
| `CHECK_MANAGER_DATA_DIR` | empty | Override the app data root directory |
| `CHECK_MANAGER_LOG_LEVEL` | `INFO` | Global log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, ...) |

### Analytics / AI service knobs

| Variable | Default |
|---|---|
| `AI_TIMEOUT_SEC` | `10` |
| `AI_HEALTHCHECK_TTL_SEC` | `45` |
| `AI_MAX_RETRIES` | `4` |
| `AI_RETRY_BACKOFF_SEC` | `1.0` |
| `AI_STARTUP_HEALTHCHECK` | `False` |
| `AI_AUTORECONNECT_ENABLED` | `True` |
| `AI_RECONNECT_INTERVAL_SEC` | `2.0` |
| `AI_RECONNECT_BACKOFF_MAX_SEC` | `60.0` |
| `AI_AUTO_MONTHLY_EXPORT_ENABLED` | `True` |
| `AI_AUTO_MONTHLY_EXPORT_FORMATS` | `excel,pdf` |
| `AI_AUTO_MONTHLY_EXPORT_MONTH_OFFSET` | `-1` |

## Backup/Restore

- Backup flow:
  1. User clicks **Create Backup**.
  2. User chooses destination folder.
  3. App copies active DB file with this naming:
     - `check_manager_backup_YYYY-MM-DD_HH-MM-SS.db`
  - if same timestamp exists: `check_manager_backup_YYYY-MM-DD_HH-MM-SS_01.db`, `..._02.db`, ...
- Restore flow:
  1. User clicks **Restore Backup**.
  2. User selects a `.db` file.
  3. App closes DB connections, replaces active DB file, and reloads DB context.
  4. App shows clear success or error message.

Notes:
- Restore operates on the active AppData DB path only.
- If another process is holding the DB lock, restore fails with a clear error message.

## License

No license file is currently included in this repository.  
If you intend to distribute this project, add a `LICENSE` file explicitly.
