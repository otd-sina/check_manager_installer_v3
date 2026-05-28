from __future__ import annotations

from dataclasses import dataclass


PAGE_DASHBOARD = 'dashboard'
PAGE_REGISTRATIONS = 'registrations'
PAGE_CHECKS = 'checks'
PAGE_EXPENSES = 'expenses'
PAGE_DEBTS = 'debts'
PAGE_BACKUP = 'backup'


@dataclass(frozen=True)
class NavigationItem:
    page_key: str
    button_attr: str
    shortcut: str


NAVIGATION_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem(PAGE_DASHBOARD, 'btn_nav_dashboard', 'Ctrl+1'),
    NavigationItem(PAGE_REGISTRATIONS, 'btn_nav_registrations', 'Ctrl+2'),
    NavigationItem(PAGE_CHECKS, 'btn_nav_checks', 'Ctrl+3'),
    NavigationItem(PAGE_EXPENSES, 'btn_nav_expenses', 'Ctrl+4'),
    NavigationItem(PAGE_DEBTS, 'btn_nav_debts', 'Ctrl+5'),
    NavigationItem(PAGE_BACKUP, 'btn_nav_backup', 'Ctrl+6'),
)

PAGE_INDEX_BY_KEY: dict[str, int] = {
    item.page_key: index for index, item in enumerate(NAVIGATION_ITEMS)
}

SHORTCUT_TO_PAGE_KEY: dict[str, str] = {
    item.shortcut: item.page_key for item in NAVIGATION_ITEMS
}
