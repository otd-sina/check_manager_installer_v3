from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)
BACKUP_NAME_PREFIX = 'check_manager_backup'
BACKUP_SUFFIX = '.db'


class BackupService:
    """Small backup helper with plain file copy semantics."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def create_backup(
        self,
        destination_dir: Path,
        before_copy_callback: Callable[[], None] | None = None,
        after_copy_callback: Callable[[], None] | None = None,
    ) -> Path:
        if not self.db_path.exists():
            raise FileNotFoundError(f'Database file does not exist: {self.db_path}')

        target_dir = Path(destination_dir).expanduser()
        target_dir.mkdir(parents=True, exist_ok=True)
        backup_path = self._next_backup_path(target_dir)

        if before_copy_callback is not None:
            before_copy_callback()

        try:
            self._checkpoint_wal()
            shutil.copy2(self.db_path, backup_path)
        finally:
            if after_copy_callback is not None:
                after_copy_callback()

        logger.info('Database backup created at %s', backup_path)
        return backup_path

    def restore_backup(self, backup_path: Path) -> Path:
        source_path = Path(backup_path).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(f'Backup file does not exist: {source_path}')
        if not source_path.is_file():
            raise ValueError('Selected backup path is not a file.')
        if source_path.suffix.lower() != BACKUP_SUFFIX:
            raise ValueError('Selected backup must be a .db file.')

        self._validate_sqlite_backup(source_path)

        restore_tmp_path = self.db_path.with_suffix(f'{self.db_path.suffix}.restore_tmp')
        if restore_tmp_path.exists():
            restore_tmp_path.unlink(missing_ok=True)

        try:
            shutil.copy2(source_path, restore_tmp_path)
            os.replace(restore_tmp_path, self.db_path)
        finally:
            if restore_tmp_path.exists():
                restore_tmp_path.unlink(missing_ok=True)

        logger.info('Database restored from backup: %s', source_path)
        return self.db_path

    def _next_backup_path(self, directory: Path) -> Path:
        stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_path = directory / f'{BACKUP_NAME_PREFIX}_{stamp}{BACKUP_SUFFIX}'
        return self._resolve_collision(backup_path)

    def _checkpoint_wal(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('PRAGMA wal_checkpoint(FULL);')

    @staticmethod
    def _validate_sqlite_backup(path: Path) -> None:
        try:
            with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as conn:
                row = conn.execute('PRAGMA integrity_check;').fetchone()
        except sqlite3.DatabaseError as exc:
            raise ValueError('Selected backup is not a valid SQLite database.') from exc

        result = str(row[0]).lower() if row and row[0] is not None else ''
        if result != 'ok':
            raise ValueError('Selected backup failed SQLite integrity check.')

    @staticmethod
    def _resolve_collision(path: Path) -> Path:
        if not path.exists():
            return path

        stem = path.stem
        suffix = path.suffix
        sequence = 1
        candidate = path
        while candidate.exists():
            candidate = path.with_name(f'{stem}_{sequence:02d}{suffix}')
            sequence += 1
        return candidate
