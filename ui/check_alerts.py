from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from models.check_model import Check
from utils.date_utils import jalali_to_gregorian, normalize_jalali_date_text


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertCandidate:
    key: str
    check_id: int
    severity: str
    serial_7: str
    registrant_name: str
    due_date_text: str
    amount: int
    delta_days: int


class CheckAlertPopup(QDialog):
    viewRequested = Signal(int)

    def __init__(self, candidate: AlertCandidate, parent: QWidget):
        super().__init__(parent)
        self.candidate = candidate
        self.setObjectName('alertPopup')
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setModal(False)
        self.resize(420, 170)

        self._build_ui()

        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.setInterval(12000)
        self._close_timer.timeout.connect(self.close)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        title = QLabel(self._title_text())
        title.setObjectName('alertTitle')
        layout.addWidget(title)

        summary = QLabel(
            f"چک {self.candidate.serial_7} | {self.candidate.registrant_name} | {self.candidate.amount:,} ریال"
        )
        summary.setObjectName('alertSummary')
        summary.setWordWrap(True)
        layout.addWidget(summary)

        detail = QLabel(f'تاریخ سررسید: {self.candidate.due_date_text}')
        detail.setObjectName('alertDetail')
        layout.addWidget(detail)

        button_row = QHBoxLayout()
        button_row.addStretch()

        btn_open = QPushButton('مشاهده چک')
        btn_open.setObjectName('alertPrimaryButton')
        btn_close = QPushButton('بستن')
        btn_close.setObjectName('alertSecondaryButton')

        button_row.addWidget(btn_open)
        button_row.addWidget(btn_close)
        layout.addLayout(button_row)

        btn_open.clicked.connect(lambda: self.viewRequested.emit(self.candidate.check_id))
        btn_open.clicked.connect(self.close)
        btn_close.clicked.connect(self.close)

        self.setProperty('severity', self.candidate.severity)

    def _title_text(self) -> str:
        if self.candidate.severity == 'overdue':
            return f'هشدار سررسید گذشته ({abs(self.candidate.delta_days)} روز)'
        if self.candidate.severity == 'today':
            return 'یادآوری چک سررسید امروز'
        return f'یادآوری سررسید نزدیک (تا {self.candidate.delta_days} روز دیگر)'

    def show_for_parent(self):
        self._position_near_parent()
        self.show()
        self.raise_()
        self._close_timer.start()

    def _position_near_parent(self):
        parent = self.parentWidget()
        if parent is None:
            return

        top_right = parent.mapToGlobal(parent.rect().topRight())
        x = top_right.x() - self.width() - 24
        y = top_right.y() + 24
        self.move(QPoint(x, y))


class CheckAlertManager(QObject):
    navigateToCheck = Signal(int)

    OPEN_STATUSES = {'PENDING', 'DEPOSITED', 'ENDORSED'}
    MAX_ALERTS_PER_SCAN = 4

    def __init__(self, check_service, parent_window: QWidget):
        super().__init__(parent_window)
        self.check_service = check_service
        self.parent_window = parent_window
        self._queue: deque[AlertCandidate] = deque()
        self._shown_keys: set[str] = set()
        self._active_popup: CheckAlertPopup | None = None
        self._today_marker = date.today()

        self._timer = QTimer(self)
        self._timer.setInterval(120000)
        self._timer.timeout.connect(self.scan_now)

    def start(self):
        self._timer.start()
        QTimer.singleShot(2000, self.scan_now)

    def scan_now(self):
        try:
            self._reset_daily_cache_if_needed()
            candidates = self._collect_candidates()
            for candidate in candidates[: self.MAX_ALERTS_PER_SCAN]:
                if any(item.key == candidate.key for item in self._queue):
                    continue
                self._queue.append(candidate)

            if self._active_popup is None:
                self._show_next_popup()
        except Exception:
            logger.exception('Alert scanning failed.')

    def _reset_daily_cache_if_needed(self):
        today = date.today()
        if today != self._today_marker:
            self._today_marker = today
            self._shown_keys.clear()

    def _collect_candidates(self) -> list[AlertCandidate]:
        today = date.today()
        candidates: list[AlertCandidate] = []

        for check in self.check_service.list_checks():
            if int(check.id or 0) <= 0:
                continue
            if (check.status or '').upper() not in self.OPEN_STATUSES:
                continue

            due_date = self._safe_due_date(check)
            if due_date is None:
                continue

            delta = (due_date - today).days
            if delta < 0:
                severity = 'overdue'
            elif delta == 0:
                severity = 'today'
            elif delta <= 3:
                severity = 'near'
            else:
                continue

            key = f'{severity}:{check.id}:{check.due_date}'
            if key in self._shown_keys:
                continue

            candidates.append(
                AlertCandidate(
                    key=key,
                    check_id=int(check.id),
                    severity=severity,
                    serial_7=check.serial_7,
                    registrant_name=check.registrant_name,
                    due_date_text=check.due_date,
                    amount=int(check.amount or 0),
                    delta_days=delta,
                )
            )

        severity_order = {'overdue': 0, 'today': 1, 'near': 2}
        candidates.sort(key=lambda item: (severity_order[item.severity], item.delta_days, item.check_id))
        return candidates

    @staticmethod
    def _safe_due_date(check: Check):
        if not check.due_date:
            return None
        try:
            return jalali_to_gregorian(normalize_jalali_date_text(check.due_date))
        except ValueError:
            return None

    def _show_next_popup(self):
        if not self._queue:
            return

        candidate = self._queue.popleft()
        self._shown_keys.add(candidate.key)

        popup = CheckAlertPopup(candidate, self.parent_window)
        popup.viewRequested.connect(self.navigateToCheck.emit)
        popup.finished.connect(self._on_popup_finished)

        self._active_popup = popup
        popup.show_for_parent()

    def _on_popup_finished(self, _result: int):
        self._active_popup = None
        if self._queue:
            QTimer.singleShot(350, self._show_next_popup)
