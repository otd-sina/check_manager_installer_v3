"""Dialog for managing expense categories."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.expense_service import ExpenseService
from ui.form_validation import reset_invalid, set_invalid


class ManageExpenseCategoriesDialog(QDialog):
    def __init__(self, expense_service: ExpenseService, parent: QWidget | None = None):
        super().__init__(parent)
        self.expense_service = expense_service
        self._selected_category_id: int | None = None

        self.setObjectName('appFormDialog')
        self.setWindowTitle('مدیریت دسته بندی هزینه ها')
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(620, 500)

        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)

        header_panel = QFrame(self)
        header_panel.setObjectName('dialogHeaderPanel')
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(2)

        title = QLabel('مدیریت دسته بندی هزینه ها')
        title.setObjectName('formDialogTitle')
        subtitle = QLabel('ایجاد، ویرایش و حذف دسته بندی های مصرف روزانه.')
        subtitle.setObjectName('formDialogSubtitle')
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header_panel)

        form_row = QHBoxLayout()
        form_row.setSpacing(8)

        self.edt_name = QLineEdit(self)
        self.edt_name.setPlaceholderText('نام دسته بندی')
        self.edt_name.setMaxLength(80)

        self.edt_description = QLineEdit(self)
        self.edt_description.setPlaceholderText('توضیح کوتاه (اختیاری)')
        self.edt_description.setMaxLength(140)

        self.btn_save = QPushButton('ذخیره')
        self.btn_reset = QPushButton('حالت جدید')

        form_row.addWidget(self.edt_name, 2)
        form_row.addWidget(self.edt_description, 3)
        form_row.addWidget(self.btn_save)
        form_row.addWidget(self.btn_reset)
        layout.addLayout(form_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['ID', 'دسته بندی', 'توضیح', 'تعداد هزینه'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnHidden(0, True)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.btn_delete = QPushButton('حذف دسته بندی')
        self.btn_close = QPushButton('بستن')
        footer.addWidget(self.btn_delete)
        footer.addWidget(self.btn_close)
        layout.addLayout(footer)

        self.btn_save.clicked.connect(self._save_category)
        self.btn_reset.clicked.connect(self._reset_form)
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_close.clicked.connect(self.accept)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

    def refresh(self):
        categories = self.expense_service.list_categories()
        usage_map = self.expense_service.get_category_usage()

        self.table.clearContents()
        self.table.setRowCount(len(categories))

        for row_index, category in enumerate(categories):
            self.table.setItem(row_index, 0, QTableWidgetItem(str(category.id or '')))
            self.table.setItem(row_index, 1, QTableWidgetItem(category.name))
            self.table.setItem(row_index, 2, QTableWidgetItem(category.description or '-'))

            usage = usage_map.get(int(category.id or 0), 0)
            usage_item = QTableWidgetItem(str(usage))
            usage_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_index, 3, usage_item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _on_selection_changed(self):
        selected = self.table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        id_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        description_item = self.table.item(row, 2)
        if id_item is None or name_item is None:
            return

        self._selected_category_id = int(id_item.text())
        self.edt_name.setText(name_item.text())
        desc = description_item.text() if description_item is not None else ''
        self.edt_description.setText('' if desc == '-' else desc)
        self.btn_save.setText('ویرایش')

    def _save_category(self):
        reset_invalid([self.edt_name])
        name = self.edt_name.text().strip()
        description = self.edt_description.text().strip()
        if not name:
            set_invalid(self.edt_name, True)
            self.edt_name.setFocus(Qt.OtherFocusReason)
            QMessageBox.warning(self, 'خطا', 'نام دسته بندی نمی تواند خالی باشد.')
            return

        try:
            if self._selected_category_id is None:
                self.expense_service.add_category(name, description)
            else:
                self.expense_service.update_category(self._selected_category_id, name, description)
        except ValueError as exc:
            QMessageBox.warning(self, 'خطا', str(exc))
            return

        self.refresh()
        self._reset_form()

    def _delete_selected(self):
        if self._selected_category_id is None:
            QMessageBox.warning(self, 'خطا', 'لطفا یک دسته بندی را انتخاب کنید.')
            return

        reply = QMessageBox.question(
            self,
            'حذف دسته بندی',
            'آیا از حذف این دسته بندی مطمئن هستید؟',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.expense_service.delete_category(self._selected_category_id)
        except ValueError as exc:
            QMessageBox.warning(self, 'امکان حذف وجود ندارد', str(exc))
            return

        self.refresh()
        self._reset_form()

    def _reset_form(self):
        self._selected_category_id = None
        self.edt_name.clear()
        self.edt_description.clear()
        self.table.clearSelection()
        self.btn_save.setText('ذخیره')
        reset_invalid([self.edt_name])
