from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.error_handler import report_exception
from config import APP_DATA_DIR
from services.backup_service import BackupService


logger = logging.getLogger(__name__)


class BackupImportPage(QWidget):
    backupImported = Signal()

    def __init__(
        self,
        backup_service: BackupService,
        before_backup_callback=None,
        before_restore_callback=None,
        after_restore_callback=None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.backup_service = backup_service
        self.before_backup_callback = before_backup_callback
        self.before_restore_callback = before_restore_callback
        self.after_restore_callback = after_restore_callback
        self.setLayoutDirection(Qt.RightToLeft)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(14)

        header_panel = QFrame(self)
        header_panel.setObjectName('pageHeaderPanel')
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(8)

        title = QLabel('Backup & Restore')
        title.setObjectName('pageTitle')
        subtitle = QLabel('Protect your data with one-click backup and safe restore.')
        subtitle.setObjectName('pageSubtitle')
        subtitle.setWordWrap(True)

        db_info_card = QFrame(self)
        db_info_card.setObjectName('backupInfoCard')
        db_info_layout = QVBoxLayout(db_info_card)
        db_info_layout.setContentsMargins(12, 12, 12, 12)
        db_info_layout.setSpacing(8)

        db_label = QLabel('Active database path')
        db_label.setObjectName('backupInfoTitle')
        self.db_path_view = QPlainTextEdit(str(self.backup_service.db_path))
        self.db_path_view.setObjectName('backupPathView')
        self.db_path_view.setReadOnly(True)
        self.db_path_view.setMaximumHeight(60)
        self.db_path_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.db_path_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.db_path_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        path_button_row = QHBoxLayout()
        path_button_row.setSpacing(8)
        self.btn_open_data_folder = QPushButton('Open Data Folder')
        self.btn_copy_db_path = QPushButton('Copy Path')
        self.btn_open_data_folder.setObjectName('backupSecondaryButton')
        self.btn_copy_db_path.setObjectName('backupSecondaryButton')
        self.btn_open_data_folder.clicked.connect(self._open_data_folder)
        self.btn_copy_db_path.clicked.connect(self._copy_active_db_path)
        path_button_row.addWidget(self.btn_open_data_folder)
        path_button_row.addWidget(self.btn_copy_db_path)
        path_button_row.addStretch()

        db_info_layout.addWidget(db_label)
        db_info_layout.addWidget(self.db_path_view)
        db_info_layout.addLayout(path_button_row)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        header_layout.addWidget(db_info_card)
        root_layout.addWidget(header_panel)

        actions_panel = QFrame(self)
        actions_panel.setObjectName('dashboardPanel')
        actions_layout = QHBoxLayout(actions_panel)
        actions_layout.setContentsMargins(18, 16, 18, 16)
        actions_layout.setSpacing(12)

        backup_card = self._build_action_card(
            title='Create Backup',
            description='Save a full copy of your current data to any folder you choose.',
            button_text='Create Backup Now',
            button_name='backupPrimaryButton',
            handler=self._create_backup,
        )
        restore_card = self._build_action_card(
            title='Restore Backup',
            description='Replace current data with a selected backup file (.db).',
            button_text='Restore Selected Backup',
            button_name='backupDangerButton',
            handler=self._restore_backup,
        )

        actions_layout.addWidget(backup_card)
        actions_layout.addWidget(restore_card)
        root_layout.addWidget(actions_panel)

        self.lbl_status = QLabel('Ready. Choose one of the actions above.')
        self.lbl_status.setObjectName('backupStatusLabel')
        self.lbl_status.setWordWrap(True)
        root_layout.addWidget(self.lbl_status)

        notice = QLabel(
            'Tip: Backup files can be kept on external storage. '
            'Restore replaces current data, so keep a fresh backup first.'
        )
        notice.setObjectName('backupSafetyNote')
        notice.setWordWrap(True)
        root_layout.addWidget(notice)

    def _build_action_card(
        self,
        title: str,
        description: str,
        button_text: str,
        button_name: str,
        handler,
    ) -> QFrame:
        card = QFrame(self)
        card.setObjectName('backupActionCard')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(8)

        card_title = QLabel(title)
        card_title.setObjectName('backupCardTitle')
        card_desc = QLabel(description)
        card_desc.setObjectName('backupCardDescription')
        card_desc.setWordWrap(True)
        action_btn = QPushButton(button_text)
        action_btn.setObjectName(button_name)
        action_btn.clicked.connect(handler)

        card_layout.addWidget(card_title)
        card_layout.addWidget(card_desc)
        card_layout.addStretch()
        card_layout.addWidget(action_btn)
        return card

    def _create_backup(self) -> None:
        destination_dir = QFileDialog.getExistingDirectory(self, 'Choose Backup Destination')
        if not destination_dir:
            return

        try:
            if self.before_backup_callback is not None:
                self.before_backup_callback()

            backup_path = self.backup_service.create_backup(Path(destination_dir))
            self.lbl_status.setText(f'Backup created successfully:\n{backup_path}')
            QMessageBox.information(self, 'Backup', f'Backup created successfully.\n{backup_path}')
        except Exception as exc:
            report_exception(
                self,
                exc,
                title='Backup Error',
                context='Create backup failed',
                logger_=logger,
            )

    def _open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(APP_DATA_DIR)))

    def _copy_active_db_path(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(str(self.backup_service.db_path))
        self.lbl_status.setText('Active database path copied to clipboard.')

    def _restore_backup(self) -> None:
        source_file, _ = QFileDialog.getOpenFileName(
            self,
            'Select Backup File',
            '',
            'Database Files (*.db)',
        )
        if not source_file:
            return

        answer = QMessageBox.warning(
            self,
            'Restore Backup',
            'Current database will be replaced with the selected backup. Continue?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        source_path = Path(source_file)
        try:
            if self.before_restore_callback is not None:
                self.before_restore_callback()

            self.backup_service.restore_backup(source_path)

            if self.after_restore_callback is not None:
                self.after_restore_callback()

            self.lbl_status.setText(f'Restore completed successfully:\n{source_path}')
            QMessageBox.information(self, 'Restore Backup', 'Database restored successfully.')
            self.backupImported.emit()
        except Exception as exc:
            report_exception(
                self,
                exc,
                title='Restore Error',
                context='Restore backup failed',
                logger_=logger,
            )
