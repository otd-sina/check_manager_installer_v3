from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping, Sequence

from utils.date_utils import normalize_jalali_date_text

import logging


logger = logging.getLogger(__name__)
SCHEMA_USER_VERSION = 4

CHECK_STATUSES = (
    'PENDING',
    'DEPOSITED',
    'PAID',
    'CLEARED',
    'BOUNCED',
    'RETURNED',
    'ENDORSED',
    'CANCELED',
)

DEBT_STATUSES = (
    'PAID',
    'UNPAID',
    'PARTIAL',
)

EXPENSE_METHODS = {'CASH', 'CARD', 'TRANSFER', 'CHEQUE', 'ONLINE', 'OTHER'}
REGISTRATION_PAYMENT_METHODS = {'CHECK', 'CASH', 'CARD', 'TRANSFER'}
PAYMENT_METHODS = {'CHECK', 'CASH_INCOME'}

DATE_CHECK_TEMPLATE = """
{column} = ''
OR (
    length({column}) = 10
    AND substr({column}, 5, 1) = '/'
    AND substr({column}, 8, 1) = '/'
    AND replace({column}, '/', '') NOT GLOB '*[^0-9]*'
)
""".strip()

CHECK_STATUS_SQL = ', '.join(f"'{status}'" for status in CHECK_STATUSES)

CHECKS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serial_18 TEXT NOT NULL CHECK(length(serial_18) = 16 AND serial_18 NOT GLOB '*[^0-9]*'),
    serial_7 TEXT NOT NULL CHECK(trim(serial_7) <> ''),
    registrant_name TEXT NOT NULL CHECK(trim(registrant_name) <> ''),
    bank_name TEXT NOT NULL DEFAULT '',
    account_owner TEXT NOT NULL CHECK(trim(account_owner) <> ''),
    amount INTEGER NOT NULL DEFAULT 0 CHECK(amount >= 0),
    issue_date TEXT NOT NULL DEFAULT '' CHECK({DATE_CHECK_TEMPLATE.format(column='issue_date')}),
    due_date TEXT NOT NULL DEFAULT '' CHECK({DATE_CHECK_TEMPLATE.format(column='due_date')}),
    payee_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ({CHECK_STATUS_SQL})),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(issue_date = '' OR due_date = '' OR due_date >= issue_date)
);
"""

CHECK_INDEXES_SQL = (
    'CREATE INDEX IF NOT EXISTS idx_checks_due_date ON checks(due_date)',
    'CREATE INDEX IF NOT EXISTS idx_checks_status ON checks(status)',
    # Cheque number is stored in serial_7.
    'CREATE INDEX IF NOT EXISTS idx_checks_cheque_number ON checks(serial_7)',
)

DEBT_STATUS_SQL = ', '.join(f"'{status}'" for status in DEBT_STATUSES)

DEBTS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debtor_name TEXT NOT NULL CHECK(trim(debtor_name) <> ''),
    phone TEXT NOT NULL DEFAULT '' CHECK(phone = '' OR (phone NOT GLOB '*[^0-9]*' AND length(phone) >= 10)),
    purchase_date TEXT NOT NULL DEFAULT '' CHECK({DATE_CHECK_TEMPLATE.format(column='purchase_date')}),
    description TEXT NOT NULL DEFAULT '',
    total_amount INTEGER NOT NULL DEFAULT 0 CHECK(total_amount >= 0),
    paid_amount INTEGER NOT NULL DEFAULT 0 CHECK(paid_amount >= 0),
    remaining_balance INTEGER NOT NULL DEFAULT 0 CHECK(remaining_balance >= 0),
    due_date TEXT NOT NULL DEFAULT '' CHECK({DATE_CHECK_TEMPLATE.format(column='due_date')}),
    status TEXT NOT NULL DEFAULT 'UNPAID' CHECK(status IN ({DEBT_STATUS_SQL})),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(paid_amount <= total_amount),
    CHECK(remaining_balance = total_amount - paid_amount)
);
"""

DEBT_INDEXES_SQL = (
    'CREATE INDEX IF NOT EXISTS idx_debts_due_date ON debts(due_date)',
    'CREATE INDEX IF NOT EXISTS idx_debts_status ON debts(status)',
    'CREATE INDEX IF NOT EXISTS idx_debts_debtor_name ON debts(debtor_name COLLATE NOCASE)',
)

EXPENSE_CATEGORIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS expense_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK(trim(name) <> ''),
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

EXPENSES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK(trim(title) <> ''),
    amount INTEGER NOT NULL CHECK(amount >= 0),
    expense_date TEXT NOT NULL CHECK(
        length(expense_date) = 10
        AND substr(expense_date, 5, 1) = '/'
        AND substr(expense_date, 8, 1) = '/'
        AND replace(expense_date, '/', '') NOT GLOB '*[^0-9]*'
    ),
    category_id INTEGER NOT NULL,
    payment_method TEXT NOT NULL DEFAULT 'CASH' CHECK(payment_method IN ('CASH', 'CARD', 'TRANSFER', 'CHEQUE', 'ONLINE', 'OTHER')),
    reference_check_id INTEGER,
    vendor TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(category_id) REFERENCES expense_categories(id) ON DELETE RESTRICT,
    FOREIGN KEY(reference_check_id) REFERENCES checks(id) ON DELETE SET NULL
);
"""

EXPENSE_INDEXES_SQL = (
    'CREATE INDEX IF NOT EXISTS idx_expenses_expense_date ON expenses(expense_date DESC)',
    'CREATE INDEX IF NOT EXISTS idx_expenses_category_id ON expenses(category_id)',
    'CREATE INDEX IF NOT EXISTS idx_expenses_reference_check_id ON expenses(reference_check_id)',
)

DEFAULT_EXPENSE_CATEGORIES = [
    ('هزینه های اداری', 'لوازم اداری، ملزومات و سرویس های دفتری'),
    ('حمل و نقل', 'هزینه رفت و آمد، پیک، تاکسی و سوخت'),
    ('خدمات و قبوض', 'برق، آب، گاز، اینترنت و شارژ'),
    ('پشتیبانی و نگهداری', 'تعمیرات تجهیزات و سرویس های فنی'),
    ('پذیرایی', 'مواد غذایی، چای، قهوه و اقلام مصرفی روزانه'),
]

CANONICAL_CHECK_COLUMNS = [
    'id',
    'serial_18',
    'serial_7',
    'registrant_name',
    'bank_name',
    'account_owner',
    'amount',
    'issue_date',
    'due_date',
    'payee_name',
    'status',
    'notes',
    'created_at',
    'updated_at',
]

CANONICAL_EXPENSE_COLUMNS = [
    'id',
    'title',
    'amount',
    'expense_date',
    'category_id',
    'payment_method',
    'reference_check_id',
    'vendor',
    'notes',
    'created_at',
    'updated_at',
]

CANONICAL_PAYMENT_COLUMNS = [
    'id',
    'registration_id',
    'amount',
    'payment_method',
    'check_id',
    'payment_date',
    'notes',
    'created_at',
]


CUSTOMERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK(trim(name) <> ''),
    national_code TEXT NOT NULL CHECK(length(national_code) = 10 AND national_code NOT GLOB '*[^0-9]*'),
    phone TEXT NOT NULL CHECK(length(phone) >= 10 AND phone NOT GLOB '*[^0-9]*'),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CUSTOMER_INDEXES_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name COLLATE NOCASE)",
)

REGISTRATIONS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    course_name TEXT NOT NULL CHECK(trim(course_name) <> ''),
    registration_date TEXT NOT NULL DEFAULT '' CHECK({DATE_CHECK_TEMPLATE.format(column='registration_date')}),
    total_fee INTEGER NOT NULL DEFAULT 0 CHECK(total_fee > 0),
    initial_payment INTEGER NOT NULL DEFAULT 0 CHECK(initial_payment >= 0),
    payment_method TEXT NOT NULL DEFAULT 'CASH' CHECK(payment_method IN ('CHECK', 'CASH', 'CARD', 'TRANSFER')),
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
);
"""

REGISTRATION_INDEXES_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_registrations_customer_id ON registrations(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_registrations_registration_date ON registrations(registration_date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_registrations_payment_method ON registrations(payment_method)",
)

PAYMENTS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registration_id INTEGER NOT NULL,
    amount INTEGER NOT NULL CHECK(amount > 0),
    payment_method TEXT NOT NULL DEFAULT 'CASH_INCOME' CHECK(payment_method IN ('CHECK','CASH_INCOME')),
    check_id INTEGER,
    payment_date TEXT NOT NULL DEFAULT '' CHECK({DATE_CHECK_TEMPLATE.format(column='payment_date')}),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(registration_id) REFERENCES registrations(id) ON DELETE CASCADE,
    FOREIGN KEY(check_id) REFERENCES checks(id) ON DELETE SET NULL,
    CHECK(
        (payment_method = 'CHECK' AND check_id IS NOT NULL)
        OR (payment_method = 'CASH_INCOME' AND check_id IS NULL)
    )
);
"""

PAYMENT_INDEXES_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_payments_registration_id ON payments(registration_id)",
    "CREATE INDEX IF NOT EXISTS idx_payments_payment_date ON payments(payment_date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_payments_check_id ON payments(check_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_unique_check_link ON payments(check_id) WHERE check_id IS NOT NULL",
)



class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._open_connections: set[sqlite3.Connection] = set()
        self._init_db()
        logger.info('Database initialized at %s', self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        self._open_connections.add(conn)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA busy_timeout = 5000')
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
            self._open_connections.discard(conn)

    def close_open_connections(self) -> None:
        for conn in list(self._open_connections):
            try:
                conn.close()
            except sqlite3.Error:
                logger.exception('Failed to close an open SQLite connection before file replacement.')
            finally:
                self._open_connections.discard(conn)

    def _init_db(self):
        with self.transaction() as conn:
            cur = conn.cursor()
            self._ensure_checks_table(cur)
            self._ensure_debts_table(cur)
            self._ensure_expense_tables(cur)
            self._ensure_customer_tables(cur)
            self._ensure_registration_payment_tables(cur)
            self._repair_legacy_check_foreign_keys(cur)
            self._apply_schema_hardening(cur)
            self._normalize_existing_data(cur)
            cur.execute(f'PRAGMA user_version = {SCHEMA_USER_VERSION}')



    def _ensure_registration_payment_tables(self, cur: sqlite3.Cursor):
        cur.execute(REGISTRATIONS_TABLE_SQL)
        if self._needs_registrations_table_migration(cur):
            self._migrate_registrations_table(cur)
        self._ensure_registrations_columns(cur)
        for statement in REGISTRATION_INDEXES_SQL:
            cur.execute(statement)

        cur.execute(PAYMENTS_TABLE_SQL)
        self._ensure_payments_integrity(cur)
        for statement in PAYMENT_INDEXES_SQL:
            cur.execute(statement)

    def _ensure_checks_table(self, cur: sqlite3.Cursor):
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'checks'"
        )
        exists = cur.fetchone() is not None

        if not exists:
            cur.execute(CHECKS_TABLE_SQL)
            self._ensure_checks_indexes(cur)
            return

        if self._needs_checks_table_migration(cur):
            logger.info('Applying checks table migration.')
            self._migrate_checks_table(cur)

        self._ensure_checks_indexes(cur)

    def _ensure_checks_indexes(self, cur: sqlite3.Cursor):
        for statement in CHECK_INDEXES_SQL:
            cur.execute(statement)

    def _ensure_debts_table(self, cur: sqlite3.Cursor):
        cur.execute(DEBTS_TABLE_SQL)
        for statement in DEBT_INDEXES_SQL:
            cur.execute(statement)

    def _ensure_expense_tables(self, cur: sqlite3.Cursor):
        cur.execute(EXPENSE_CATEGORIES_TABLE_SQL)
        cur.execute(EXPENSES_TABLE_SQL)

        for statement in EXPENSE_INDEXES_SQL:
            cur.execute(statement)

        cur.execute('SELECT COUNT(*) FROM expense_categories')
        category_count = int(cur.fetchone()[0] or 0)
        if category_count == 0:
            cur.executemany(
                'INSERT INTO expense_categories(name, description) VALUES(?, ?)',
                DEFAULT_EXPENSE_CATEGORIES,
            )

    def _needs_checks_table_migration(self, cur: sqlite3.Cursor) -> bool:
        cur.execute('PRAGMA table_info(checks)')
        columns = [row[1] for row in cur.fetchall()]
        if columns != CANONICAL_CHECK_COLUMNS:
            return True

        cur.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'checks'")
        row = cur.fetchone()
        definition = (row[0] if row else '') or ''
        normalized = definition.upper()
        if 'CHECK(STATUS IN' not in normalized:
            return True
        if 'UPDATED_AT' not in normalized:
            return True
        if 'DUE_DATE >= ISSUE_DATE' not in normalized:
            return True
        if "SERIAL_18 TEXT NOT NULL CHECK(LENGTH(SERIAL_18) = 16 AND SERIAL_18 NOT GLOB '*[^0-9]*')" not in normalized:
            return True
        if "SERIAL_7 TEXT NOT NULL CHECK(TRIM(SERIAL_7) <> '')" not in normalized:
            return True
        return False

    def _migrate_checks_table(self, cur: sqlite3.Cursor):
        logger.info('Migrating checks table to canonical schema.')
        cur.execute("DROP TABLE IF EXISTS checks_legacy")
        # Keep dependent FKs pointing to `checks` while we rebuild the table.
        cur.execute('PRAGMA legacy_alter_table = ON')
        try:
            cur.execute('ALTER TABLE checks RENAME TO checks_legacy')
        finally:
            cur.execute('PRAGMA legacy_alter_table = OFF')
        cur.execute(CHECKS_TABLE_SQL)

        cur.execute('PRAGMA table_info(checks_legacy)')
        legacy_columns = {row[1] for row in cur.fetchall()}

        def has(column: str) -> bool:
            return column in legacy_columns

        def trimmed(column: str) -> str:
            return f"trim(COALESCE({column}, ''))"

        def normalized_digits(column: str, length: int, fallback_sql: str) -> str:
            content = trimmed(column)
            return (
                f"CASE WHEN length({content}) = {length} AND {content} NOT GLOB '*[^0-9]*' "
                f"THEN {content} ELSE {fallback_sql} END"
            )

        def normalized_date(column: str) -> str:
            value = f"replace({trimmed(column)}, '-', '/')"
            return (
                'CASE '
                f"WHEN {trimmed(column)} = '' THEN '' "
                f"WHEN length({value}) = 10 "
                f"AND substr({value}, 5, 1) = '/' "
                f"AND substr({value}, 8, 1) = '/' "
                f"AND replace({value}, '/', '') NOT GLOB '*[^0-9]*' "
                f"THEN {value} ELSE '' END"
            )

        serial_18_expr = (
            normalized_digits('serial_18', 16, "printf('%016d', abs(id) % 10000000000000000)")
            if has('serial_18')
            else "printf('%016d', abs(id) % 10000000000000000)"
        )

        serial_7_candidates = []
        if has('serial_7'):
            serial_7_candidates.append('serial_7')
        if has('check_number'):
            serial_7_candidates.append('check_number')

        if serial_7_candidates:
            serial_7_checks = ' '.join(
                f"WHEN {trimmed(column)} <> '' THEN {trimmed(column)}"
                for column in serial_7_candidates
            )
            serial_7_expr = f"CASE {serial_7_checks} ELSE 'SERIAL-' || id END"
        else:
            serial_7_expr = "'SERIAL-' || id"

        registrant_expr = (
            f"CASE WHEN {trimmed('registrant_name')} <> '' THEN {trimmed('registrant_name')} "
            f"WHEN {trimmed('account_owner')} <> '' THEN {trimmed('account_owner')} "
            "ELSE 'نامشخص' END"
            if has('registrant_name') and has('account_owner')
            else (
                f"CASE WHEN {trimmed('registrant_name')} <> '' THEN {trimmed('registrant_name')} ELSE 'نامشخص' END"
                if has('registrant_name')
                else (
                    f"CASE WHEN {trimmed('account_owner')} <> '' THEN {trimmed('account_owner')} ELSE 'نامشخص' END"
                    if has('account_owner')
                    else "'نامشخص'"
                )
            )
        )

        account_owner_expr = (
            f"CASE WHEN {trimmed('account_owner')} <> '' THEN {trimmed('account_owner')} "
            f"WHEN {trimmed('registrant_name')} <> '' THEN {trimmed('registrant_name')} "
            "ELSE 'نامشخص' END"
            if has('account_owner') and has('registrant_name')
            else (
                f"CASE WHEN {trimmed('account_owner')} <> '' THEN {trimmed('account_owner')} ELSE 'نامشخص' END"
                if has('account_owner')
                else (
                    f"CASE WHEN {trimmed('registrant_name')} <> '' THEN {trimmed('registrant_name')} ELSE 'نامشخص' END"
                    if has('registrant_name')
                    else "'نامشخص'"
                )
            )
        )

        amount_expr = (
            "CASE "
            "WHEN trim(COALESCE(amount, '')) = '' THEN 0 "
            "ELSE CAST(REPLACE(trim(amount), ',', '') AS INTEGER) END"
            if has('amount')
            else '0'
        )

        if has('status'):
            status_checks = ' '.join(
                f"WHEN upper(trim(COALESCE(status, ''))) = '{status}' THEN '{status}'"
                for status in CHECK_STATUSES
            )
            status_expr = f"CASE {status_checks} ELSE 'PENDING' END"
        else:
            status_expr = "'PENDING'"

        issue_date_expr = normalized_date('issue_date') if has('issue_date') else "''"
        due_date_expr = normalized_date('due_date') if has('due_date') else "''"

        select_statements = {
            'id': 'id',
            'serial_18': serial_18_expr,
            'serial_7': serial_7_expr,
            'registrant_name': registrant_expr,
            'bank_name': trimmed('bank_name') if has('bank_name') else "''",
            'account_owner': account_owner_expr,
            'amount': amount_expr,
            'issue_date': issue_date_expr,
            'due_date': due_date_expr,
            'payee_name': trimmed('payee_name') if has('payee_name') else "''",
            'status': status_expr,
            'notes': trimmed('notes') if has('notes') else "''",
            'created_at': 'created_at' if has('created_at') else 'CURRENT_TIMESTAMP',
            'updated_at': 'updated_at' if has('updated_at') else 'CURRENT_TIMESTAMP',
        }

        select_clause = ', '.join(select_statements[column] for column in CANONICAL_CHECK_COLUMNS)

        cur.execute(
            f"""
            INSERT INTO checks ({', '.join(CANONICAL_CHECK_COLUMNS)})
            SELECT {select_clause}
            FROM checks_legacy
            """
        )
        cur.execute('DROP TABLE checks_legacy')
        logger.info('Checks table migration completed successfully.')

    def _repair_legacy_check_foreign_keys(self, cur: sqlite3.Cursor):
        self._rebuild_table_if_referencing_legacy_checks(
            cur,
            table_name='expenses',
            create_table_sql=EXPENSES_TABLE_SQL,
            canonical_columns=CANONICAL_EXPENSE_COLUMNS,
            index_statements=EXPENSE_INDEXES_SQL,
        )
        self._rebuild_table_if_referencing_legacy_checks(
            cur,
            table_name='payments',
            create_table_sql=PAYMENTS_TABLE_SQL,
            canonical_columns=CANONICAL_PAYMENT_COLUMNS,
            index_statements=PAYMENT_INDEXES_SQL,
        )

    def _rebuild_table_if_referencing_legacy_checks(
        self,
        cur: sqlite3.Cursor,
        *,
        table_name: str,
        create_table_sql: str,
        canonical_columns: Sequence[str],
        index_statements: Sequence[str],
    ) -> None:
        if not self._table_references_legacy_checks(cur, table_name):
            return

        logger.warning(
            'Repairing %s foreign keys that still reference checks_legacy.',
            table_name,
        )
        repair_table = f'{table_name}_legacy_fk_fix'
        cur.execute(f'DROP TABLE IF EXISTS {repair_table}')
        cur.execute(f'ALTER TABLE {table_name} RENAME TO {repair_table}')
        cur.execute(create_table_sql)

        rows = cur.execute(f'PRAGMA table_info({repair_table})').fetchall()
        legacy_columns = {str(row['name']) for row in rows}
        transferable_columns = [column for column in canonical_columns if column in legacy_columns]
        if transferable_columns:
            columns_csv = ', '.join(transferable_columns)
            cur.execute(
                f"""
                INSERT INTO {table_name} ({columns_csv})
                SELECT {columns_csv}
                FROM {repair_table}
                """
            )

        cur.execute(f'DROP TABLE {repair_table}')
        for statement in index_statements:
            cur.execute(statement)

    @staticmethod
    def _table_references_legacy_checks(cur: sqlite3.Cursor, table_name: str) -> bool:
        rows = cur.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchall()
        if not rows:
            return False

        fk_rows = cur.execute(f'PRAGMA foreign_key_list({table_name})').fetchall()
        for fk_row in fk_rows:
            parent_table = str(fk_row['table'] or '').strip().lower()
            if parent_table == 'checks_legacy':
                return True
        return False

    def _normalize_existing_data(self, cur: sqlite3.Cursor):
        self._normalize_checks_data(cur)
        self._normalize_debts_data(cur)
        self._normalize_expenses_data(cur)

    def _normalize_checks_data(self, cur: sqlite3.Cursor):
        cur.execute(
            'SELECT id, amount, issue_date, due_date, status, serial_18, serial_7 FROM checks'
        )
        rows = cur.fetchall()

        for row in rows:
            row_id = int(row[0])
            raw_amount = self._normalize_amount(row[1])
            normalized_amount = self._normalize_amount(row[1])
            normalized_issue_date = self._normalize_date_text(row[2])
            normalized_due_date = self._normalize_date_text(row[3])
            normalized_status = self._normalize_status(row[4])
            normalized_serial_18 = self._normalize_serial(row[5], 16, f'{row_id:016d}'[-16:])
            normalized_serial_7 = self._normalize_text(row[6], f'SERIAL-{row_id}')

            if (
                normalized_amount == raw_amount
                and normalized_issue_date == str(row[2] or '').strip()
                and normalized_due_date == str(row[3] or '').strip()
                and normalized_status == str(row[4] or '').strip().upper()
                and normalized_serial_18 == str(row[5] or '').strip()
                and normalized_serial_7 == str(row[6] or '')
            ):
                continue

            cur.execute(
                """
                UPDATE checks
                SET amount = ?, issue_date = ?, due_date = ?, status = ?,
                    serial_18 = ?, serial_7 = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    normalized_amount,
                    normalized_issue_date,
                    normalized_due_date,
                    normalized_status,
                    normalized_serial_18,
                    normalized_serial_7,
                    row_id,
                ),
            )

    def _normalize_expenses_data(self, cur: sqlite3.Cursor):
        cur.execute('SELECT id, amount, expense_date, payment_method FROM expenses')
        rows = cur.fetchall()

        for row in rows:
            row_id = int(row[0])
            raw_amount = self._normalize_amount(row[1])
            normalized_amount = self._normalize_amount(row[1])
            normalized_expense_date = self._normalize_date_text(row[2])
            normalized_payment_method = self._normalize_payment_method(row[3])

            if (
                normalized_amount == raw_amount
                and normalized_expense_date == str(row[2] or '').strip()
                and normalized_payment_method == str(row[3] or '').strip().upper()
            ):
                continue

            cur.execute(
                """
                UPDATE expenses
                SET amount = ?, expense_date = ?, payment_method = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (normalized_amount, normalized_expense_date, normalized_payment_method, row_id),
            )

    def _normalize_debts_data(self, cur: sqlite3.Cursor):
        cur.execute(
            'SELECT id, total_amount, paid_amount, remaining_balance, due_date, status, phone FROM debts'
        )
        rows = cur.fetchall()

        for row in rows:
            row_id = int(row[0])
            total_amount = self._normalize_amount(row[1])
            paid_amount = self._normalize_amount(row[2])
            if paid_amount > total_amount:
                paid_amount = total_amount

            remaining_balance = total_amount - paid_amount
            normalized_due_date = self._normalize_date_text(row[4])
            normalized_status = self._normalize_debt_status(row[5], remaining_balance, total_amount)
            normalized_phone = ''.join(ch for ch in str(row[6] or '') if ch.isdigit())
            raw_total = self._normalize_amount(row[1])
            raw_paid = self._normalize_amount(row[2])
            raw_remaining = self._normalize_amount(row[3])

            if (
                total_amount == raw_total
                and paid_amount == raw_paid
                and remaining_balance == raw_remaining
                and normalized_due_date == str(row[4] or '').strip()
                and normalized_status == str(row[5] or '').strip().upper()
                and normalized_phone == str(row[6] or '').strip()
            ):
                continue

            cur.execute(
                """
                UPDATE debts
                SET total_amount = ?, paid_amount = ?, remaining_balance = ?,
                    due_date = ?, status = ?, phone = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    total_amount,
                    paid_amount,
                    remaining_balance,
                    normalized_due_date,
                    normalized_status,
                    normalized_phone,
                    row_id,
                ),
            )

    @staticmethod
    def _normalize_amount(value) -> int:
        text = str(value or '').replace(',', '').strip()
        if not text:
            return 0
        return int(text) if text.isdigit() else 0

    @staticmethod
    def _normalize_serial(value: object, length: int, fallback: str) -> str:
        text = str(value or '').strip()
        if len(text) == length and text.isdigit():
            return text
        return fallback

    @staticmethod
    def _normalize_text(value: object, fallback: str) -> str:
        text = str(value or '')
        return text if text.strip() else fallback

    @staticmethod
    def _normalize_status(value: object) -> str:
        candidate = str(value or '').strip().upper()
        if candidate in CHECK_STATUSES:
            return candidate
        return 'PENDING'

    @staticmethod
    def _normalize_date_text(value: object) -> str:
        text = str(value or '').strip()
        if not text:
            return ''
        try:
            return normalize_jalali_date_text(text)
        except ValueError:
            return ''

    @staticmethod
    def _normalize_payment_method(value: object) -> str:
        normalized = str(value or '').strip().upper()
        if normalized in EXPENSE_METHODS:
            return normalized
        return 'OTHER'

    @staticmethod
    def _normalize_debt_status(value: object, remaining_balance: int, total_amount: int) -> str:
        if total_amount <= 0 or remaining_balance >= total_amount:
            return 'UNPAID'
        if remaining_balance <= 0:
            return 'PAID'
        return 'PARTIAL'

    # Generic helpers
    def execute(self, query: str, params: Sequence[object] = ()) -> int:
        try:
            with self.transaction() as conn:
                cur = conn.cursor()
                cur.execute(query, tuple(params))
                return int(cur.lastrowid or 0)
        except Exception:
            logger.exception('SQL execute failed: %s | params=%s', query, params)
            raise

    def executemany(self, query: str, params: Sequence[Sequence[object]]):
        try:
            with self.transaction() as conn:
                conn.executemany(query, params)
        except Exception:
            logger.exception('SQL executemany failed: %s', query)
            raise

    def fetchone(self, query: str, params: Sequence[object] = ()) -> sqlite3.Row | None:
        try:
            with self.transaction() as conn:
                cur = conn.cursor()
                cur.execute(query, tuple(params))
                return cur.fetchone()
        except Exception:
            logger.exception('SQL fetchone failed: %s | params=%s', query, params)
            raise

    def fetchall(self, query: str, params: Sequence[object] = ()) -> list[sqlite3.Row]:
        try:
            with self.transaction() as conn:
                cur = conn.cursor()
                cur.execute(query, tuple(params))
                return cur.fetchall()
        except Exception:
            logger.exception('SQL fetchall failed: %s | params=%s', query, params)
            raise

    def iterate(
        self,
        query: str,
        params: Sequence[object] = (),
        batch_size: int = 500,
    ) -> Iterator[sqlite3.Row]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(query, tuple(params))
            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    yield row
        except Exception:
            logger.exception('SQL iterate failed: %s | params=%s', query, params)
            raise
        finally:
            conn.close()

    # Checks CRUD operations
    def create_check(self, payload: Mapping[str, object]) -> int:
        query = """
            INSERT INTO checks (
                serial_18, serial_7, registrant_name, bank_name, account_owner,
                amount, issue_date, due_date, payee_name, status, notes,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        params = (
            payload['serial_18'],
            payload['serial_7'],
            payload['registrant_name'],
            payload.get('bank_name', ''),
            payload['account_owner'],
            payload['amount'],
            payload.get('issue_date', ''),
            payload.get('due_date', ''),
            payload.get('payee_name', ''),
            payload['status'],
            payload.get('notes', ''),
        )
        return self.execute(query, params)

    def update_check(self, check_id: int, payload: Mapping[str, object]):
        query = """
            UPDATE checks
            SET serial_18 = ?, serial_7 = ?, registrant_name = ?, bank_name = ?,
                account_owner = ?, amount = ?, issue_date = ?, due_date = ?,
                payee_name = ?, status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        params = (
            payload['serial_18'],
            payload['serial_7'],
            payload['registrant_name'],
            payload.get('bank_name', ''),
            payload['account_owner'],
            payload['amount'],
            payload.get('issue_date', ''),
            payload.get('due_date', ''),
            payload.get('payee_name', ''),
            payload['status'],
            payload.get('notes', ''),
            int(check_id),
        )
        self.execute(query, params)

    def delete_check(self, check_id: int):
        self.execute('DELETE FROM checks WHERE id = ?', (int(check_id),))

    def get_check(self, check_id: int) -> sqlite3.Row | None:
        return self.fetchone('SELECT * FROM checks WHERE id = ?', (int(check_id),))

    def list_checks(
        self,
        status: str | None = None,
        from_due_date: str | None = None,
        to_due_date: str | None = None,
    ) -> list[sqlite3.Row]:
        query = 'SELECT * FROM checks WHERE 1 = 1'
        params: list[object] = []

        if status:
            query += ' AND status = ?'
            params.append(status)

        if from_due_date:
            query += ' AND due_date >= ?'
            params.append(from_due_date)

        if to_due_date:
            query += ' AND due_date <= ?'
            params.append(to_due_date)

        query += ' ORDER BY due_date ASC, id DESC'
        return self.fetchall(query, tuple(params))

    def iter_checks(
        self,
        status: str | None = None,
        from_due_date: str | None = None,
        to_due_date: str | None = None,
        batch_size: int = 500,
    ) -> Iterator[sqlite3.Row]:
        query = 'SELECT * FROM checks WHERE 1 = 1'
        params: list[object] = []

        if status:
            query += ' AND status = ?'
            params.append(status)

        if from_due_date:
            query += ' AND due_date >= ?'
            params.append(from_due_date)

        if to_due_date:
            query += ' AND due_date <= ?'
            params.append(to_due_date)

        query += ' ORDER BY due_date ASC, id DESC'
        yield from self.iterate(query, tuple(params), batch_size=batch_size)

    def serial_exists(
        self,
        *,
        serial_18: str,
        serial_7: str,
        exclude_id: int | None = None,
    ) -> bool:
        query = (
            'SELECT id FROM checks WHERE (serial_18 = ? OR serial_7 = ?)' 
            + (' AND id <> ?' if exclude_id is not None else '')
            + ' LIMIT 1'
        )
        params: list[object] = [serial_18, serial_7]
        if exclude_id is not None:
            params.append(int(exclude_id))
        row = self.fetchone(query, tuple(params))
        return row is not None

    def check_exists(self, check_id: int) -> bool:
        row = self.fetchone('SELECT id FROM checks WHERE id = ? LIMIT 1', (int(check_id),))
        return row is not None

    # Debts CRUD operations
    def create_debt(self, payload: Mapping[str, object]) -> int:
        query = """
            INSERT INTO debts (
                debtor_name, phone, total_amount, paid_amount, remaining_balance,
                due_date, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        params = (
            payload['debtor_name'],
            payload.get('phone', ''),
            payload['total_amount'],
            payload.get('paid_amount', 0),
            payload['remaining_balance'],
            payload.get('due_date', ''),
            payload['status'],
        )
        return self.execute(query, params)

    def update_debt(self, debt_id: int, payload: Mapping[str, object]):
        query = """
            UPDATE debts
            SET debtor_name = ?, phone = ?, total_amount = ?, paid_amount = ?,
                remaining_balance = ?, due_date = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        params = (
            payload['debtor_name'],
            payload.get('phone', ''),
            payload['total_amount'],
            payload.get('paid_amount', 0),
            payload['remaining_balance'],
            payload.get('due_date', ''),
            payload['status'],
            int(debt_id),
        )
        self.execute(query, params)

    def delete_debt(self, debt_id: int):
        self.execute('DELETE FROM debts WHERE id = ?', (int(debt_id),))

    def get_debt(self, debt_id: int) -> sqlite3.Row | None:
        return self.fetchone('SELECT * FROM debts WHERE id = ?', (int(debt_id),))

    def list_debts(
        self,
        status: str | None = None,
        from_due_date: str | None = None,
        to_due_date: str | None = None,
    ) -> list[sqlite3.Row]:
        query = 'SELECT * FROM debts WHERE 1 = 1'
        params: list[object] = []

        if status:
            query += ' AND status = ?'
            params.append(status)

        if from_due_date:
            query += ' AND due_date >= ?'
            params.append(from_due_date)

        if to_due_date:
            query += ' AND due_date <= ?'
            params.append(to_due_date)

        query += ' ORDER BY due_date ASC, id DESC'
        return self.fetchall(query, tuple(params))

    def debt_exists(self, debt_id: int) -> bool:
        row = self.fetchone('SELECT id FROM debts WHERE id = ? LIMIT 1', (int(debt_id),))
        return row is not None

    def get_total_outstanding_receivables(self) -> int:
        row = self.fetchone(
            """
            SELECT COALESCE(SUM(remaining_balance), 0) AS total
            FROM debts
            WHERE remaining_balance > 0
            """,
        )
        return int((row['total'] if row else 0) or 0)

    def pragma_index_list(self, table_name: str) -> list[sqlite3.Row]:
        return self.fetchall(f'PRAGMA index_list({table_name})')

    @staticmethod
    def _clean_positive_ids(values: Sequence[int]) -> list[int]:
        cleaned: list[int] = []
        for value in values:
            candidate = int(value)
            if candidate > 0:
                cleaned.append(candidate)
        return cleaned

    @staticmethod
    def _fetch_check_amounts(cur: sqlite3.Cursor, check_ids: Sequence[int]) -> dict[int, int]:
        if not check_ids:
            return {}

        placeholders = ','.join('?' for _ in check_ids)
        rows = cur.execute(
            f"SELECT id, amount FROM checks WHERE id IN ({placeholders})",
            tuple(check_ids),
        ).fetchall()
        return {int(row['id']): int(row['amount'] or 0) for row in rows}

    @staticmethod
    def _ensure_checks_not_linked_elsewhere(
        cur: sqlite3.Cursor,
        check_ids: Sequence[int],
        registration_id: int,
    ):
        if not check_ids:
            return

        placeholders = ','.join('?' for _ in check_ids)
        linked_rows = cur.execute(
            f'''
            SELECT check_id
            FROM payments
            WHERE check_id IN ({placeholders}) AND registration_id <> ?
            ''',
            tuple(check_ids) + (int(registration_id),),
        ).fetchall()
        if linked_rows:
            raise ValueError('حداقل یکی از چک های انتخاب شده قبلاً به ثبت نام دیگری لینک شده است.')


    def _ensure_customer_tables(self, cur: sqlite3.Cursor):
        cur.execute(CUSTOMERS_TABLE_SQL)
        for stmt in CUSTOMER_INDEXES_SQL:
            cur.execute(stmt)
    
    def _ensure_registrations_columns(self, cur: sqlite3.Cursor):
        cur.execute('PRAGMA table_info(registrations)')
        columns = {row['name'] for row in cur.fetchall()}

        if 'initial_payment' not in columns:
            cur.execute("ALTER TABLE registrations ADD COLUMN initial_payment INTEGER NOT NULL DEFAULT 0")

        if 'payment_method' not in columns:
            cur.execute("ALTER TABLE registrations ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'CASH'")

        if 'updated_at' not in columns:
            cur.execute("ALTER TABLE registrations ADD COLUMN updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")

        cur.execute(
            """
            UPDATE registrations
            SET payment_method = CASE upper(trim(COALESCE(payment_method, '')))
                WHEN 'CHECK' THEN 'CHECK'
                WHEN 'POS' THEN 'CARD'
                WHEN 'CARD_TO_CARD' THEN 'TRANSFER'
                WHEN 'CARD' THEN 'CARD'
                WHEN 'TRANSFER' THEN 'TRANSFER'
                WHEN 'CASH' THEN 'CASH'
                WHEN 'CASH_INCOME' THEN 'CASH'
                ELSE 'CASH'
            END
            """
        )
        cur.execute(
            """
            UPDATE registrations
            SET initial_payment = CASE
                WHEN CAST(COALESCE(initial_payment, 0) AS INTEGER) < 0 THEN 0
                WHEN CAST(COALESCE(initial_payment, 0) AS INTEGER) > CAST(COALESCE(total_fee, 0) AS INTEGER)
                    THEN CAST(COALESCE(total_fee, 0) AS INTEGER)
                ELSE CAST(COALESCE(initial_payment, 0) AS INTEGER)
            END
            """
        )

    @staticmethod
    def _needs_registrations_table_migration(cur: sqlite3.Cursor) -> bool:
        cur.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'registrations'")
        row = cur.fetchone()
        definition = (row[0] if row else '') or ''
        normalized = definition.upper()
        if "INITIAL_PAYMENT" not in normalized:
            return True
        return "CHECK(PAYMENT_METHOD IN ('CHECK', 'CASH', 'CARD', 'TRANSFER'))" not in normalized

    @staticmethod
    def _migrate_registrations_table(cur: sqlite3.Cursor):
        cur.execute('PRAGMA foreign_keys = OFF')
        try:
            cur.execute(
                """
                CREATE TABLE registrations_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    course_name TEXT NOT NULL CHECK(trim(course_name) <> ''),
                    registration_date TEXT NOT NULL DEFAULT '' CHECK(
                        registration_date = ''
                        OR (
                            length(registration_date) = 10
                            AND substr(registration_date, 5, 1) = '/'
                            AND substr(registration_date, 8, 1) = '/'
                            AND replace(registration_date, '/', '') NOT GLOB '*[^0-9]*'
                        )
                    ),
                    total_fee INTEGER NOT NULL DEFAULT 0 CHECK(total_fee > 0),
                    initial_payment INTEGER NOT NULL DEFAULT 0 CHECK(initial_payment >= 0),
                    payment_method TEXT NOT NULL DEFAULT 'CASH' CHECK(payment_method IN ('CHECK', 'CASH', 'CARD', 'TRANSFER')),
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
                );
                """
            )
            cur.execute(
                """
                INSERT INTO registrations_new(
                    id, customer_id, course_name, registration_date, total_fee, initial_payment, payment_method, description, created_at, updated_at
                )
                SELECT
                    id,
                    customer_id,
                    CASE
                        WHEN trim(COALESCE(course_name, '')) = '' THEN 'بدون دوره'
                        ELSE trim(course_name)
                    END,
                    CASE
                        WHEN registration_date IS NULL THEN ''
                        WHEN length(trim(registration_date)) = 10
                            AND substr(trim(registration_date), 5, 1) = '/'
                            AND substr(trim(registration_date), 8, 1) = '/'
                            AND replace(trim(registration_date), '/', '') NOT GLOB '*[^0-9]*'
                            THEN trim(registration_date)
                        ELSE ''
                    END,
                    CASE
                        WHEN CAST(COALESCE(total_fee, 0) AS INTEGER) <= 0 THEN 1
                        ELSE CAST(COALESCE(total_fee, 0) AS INTEGER)
                    END,
                    0,
                    CASE upper(trim(COALESCE(payment_method, '')))
                        WHEN 'CHECK' THEN 'CHECK'
                        WHEN 'POS' THEN 'CARD'
                        WHEN 'CARD_TO_CARD' THEN 'TRANSFER'
                        WHEN 'CARD' THEN 'CARD'
                        WHEN 'TRANSFER' THEN 'TRANSFER'
                        ELSE 'CASH'
                    END,
                    COALESCE(description, ''),
                    COALESCE(created_at, CURRENT_TIMESTAMP),
                    COALESCE(updated_at, CURRENT_TIMESTAMP)
                FROM registrations
                """
            )
            cur.execute('DROP TABLE registrations')
            cur.execute('ALTER TABLE registrations_new RENAME TO registrations')
        finally:
            cur.execute('PRAGMA foreign_keys = ON')

    @staticmethod
    def _ensure_payments_integrity(cur: sqlite3.Cursor):
        cur.execute(
            """
            UPDATE payments
            SET payment_method = CASE upper(trim(COALESCE(payment_method, '')))
                WHEN 'CHECK' THEN 'CHECK'
                ELSE 'CASH_INCOME'
            END
            """
        )

    def _apply_schema_hardening(self, cur: sqlite3.Cursor):
        self._normalize_customer_integrity_data(cur)
        self._normalize_check_serial_uniqueness(cur)
        self._ensure_unique_integrity_indexes(cur)
        self._ensure_business_rule_triggers(cur)

    def _normalize_customer_integrity_data(self, cur: sqlite3.Cursor):
        rows = cur.execute(
            'SELECT id, national_code, phone FROM customers ORDER BY id ASC'
        ).fetchall()
        if not rows:
            return

        primary_customer_by_national_code: dict[str, int] = {}
        for row in rows:
            customer_id = int(row['id'])
            national_code = self._normalize_national_code(row['national_code'], customer_id)
            phone = self._normalize_phone_number(row['phone'], customer_id)

            primary_customer_id = primary_customer_by_national_code.get(national_code)
            if primary_customer_id is not None and primary_customer_id != customer_id:
                cur.execute(
                    'UPDATE registrations SET customer_id = ? WHERE customer_id = ?',
                    (primary_customer_id, customer_id),
                )
                cur.execute('DELETE FROM customers WHERE id = ?', (customer_id,))
                continue

            cur.execute(
                'UPDATE customers SET national_code = ?, phone = ? WHERE id = ?',
                (national_code, phone, customer_id),
            )
            primary_customer_by_national_code[national_code] = customer_id

    def _normalize_check_serial_uniqueness(self, cur: sqlite3.Cursor):
        rows = cur.execute(
            'SELECT id, serial_18, serial_7 FROM checks ORDER BY id ASC'
        ).fetchall()
        if not rows:
            return

        used_serial_18: set[str] = set()
        used_serial_7: set[str] = set()

        for row in rows:
            check_id = int(row['id'])
            serial_18 = self._normalize_serial(row['serial_18'], 16, f'{check_id:016d}'[-16:])
            serial_7 = self._normalize_text(row['serial_7'], f'SERIAL-{check_id}')

            if serial_18 in used_serial_18:
                serial_18 = self._next_unique_numeric_text(check_id, 16, used_serial_18)
            else:
                used_serial_18.add(serial_18)

            if serial_7 in used_serial_7:
                serial_7 = self._next_unique_text(f'{serial_7}-{check_id}', used_serial_7)
            else:
                used_serial_7.add(serial_7)

            if serial_18 != str(row['serial_18'] or '').strip() or serial_7 != str(row['serial_7'] or ''):
                cur.execute(
                    """
                    UPDATE checks
                    SET serial_18 = ?, serial_7 = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (serial_18, serial_7, check_id),
                )

    def _ensure_unique_integrity_indexes(self, cur: sqlite3.Cursor):
        cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_checks_unique_serial_18 ON checks(serial_18)')
        cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_checks_unique_serial_7 ON checks(serial_7)')
        cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_unique_national_code ON customers(national_code)')

    def _ensure_business_rule_triggers(self, cur: sqlite3.Cursor):
        trigger_statements = (
            ('trg_checks_due_date_integrity_insert', """
                CREATE TRIGGER trg_checks_due_date_integrity_insert
                BEFORE INSERT ON checks
                FOR EACH ROW
                WHEN NEW.issue_date <> '' AND NEW.due_date <> '' AND NEW.due_date < NEW.issue_date
                BEGIN
                    SELECT RAISE(ABORT, 'checks.due_date cannot be earlier than checks.issue_date');
                END
            """),
            ('trg_checks_due_date_integrity_update', """
                CREATE TRIGGER trg_checks_due_date_integrity_update
                BEFORE UPDATE OF issue_date, due_date ON checks
                FOR EACH ROW
                WHEN NEW.issue_date <> '' AND NEW.due_date <> '' AND NEW.due_date < NEW.issue_date
                BEGIN
                    SELECT RAISE(ABORT, 'checks.due_date cannot be earlier than checks.issue_date');
                END
            """),
            ('trg_customers_integrity_insert', """
                CREATE TRIGGER trg_customers_integrity_insert
                BEFORE INSERT ON customers
                FOR EACH ROW
                WHEN NEW.national_code IS NULL
                    OR length(trim(NEW.national_code)) <> 10
                    OR trim(NEW.national_code) GLOB '*[^0-9]*'
                    OR NEW.phone IS NULL
                    OR length(trim(NEW.phone)) < 10
                    OR trim(NEW.phone) GLOB '*[^0-9]*'
                BEGIN
                    SELECT RAISE(ABORT, 'customers.national_code and customers.phone must be numeric and valid');
                END
            """),
            ('trg_customers_integrity_update', """
                CREATE TRIGGER trg_customers_integrity_update
                BEFORE UPDATE OF national_code, phone ON customers
                FOR EACH ROW
                WHEN NEW.national_code IS NULL
                    OR length(trim(NEW.national_code)) <> 10
                    OR trim(NEW.national_code) GLOB '*[^0-9]*'
                    OR NEW.phone IS NULL
                    OR length(trim(NEW.phone)) < 10
                    OR trim(NEW.phone) GLOB '*[^0-9]*'
                BEGIN
                    SELECT RAISE(ABORT, 'customers.national_code and customers.phone must be numeric and valid');
                END
            """),
            ('trg_registrations_integrity_insert', """
                CREATE TRIGGER trg_registrations_integrity_insert
                BEFORE INSERT ON registrations
                FOR EACH ROW
                WHEN trim(COALESCE(NEW.course_name, '')) = ''
                    OR CAST(COALESCE(NEW.total_fee, 0) AS INTEGER) <= 0
                    OR CAST(COALESCE(NEW.initial_payment, 0) AS INTEGER) < 0
                    OR CAST(COALESCE(NEW.initial_payment, 0) AS INTEGER) > CAST(COALESCE(NEW.total_fee, 0) AS INTEGER)
                    OR upper(trim(COALESCE(NEW.payment_method, ''))) NOT IN ('CHECK', 'CASH', 'CARD', 'TRANSFER')
                BEGIN
                    SELECT RAISE(ABORT, 'registrations violates course_name/total_fee/payment_method integrity rules');
                END
            """),
            ('trg_registrations_integrity_update', """
                CREATE TRIGGER trg_registrations_integrity_update
                BEFORE UPDATE OF course_name, total_fee, initial_payment, payment_method ON registrations
                FOR EACH ROW
                WHEN trim(COALESCE(NEW.course_name, '')) = ''
                    OR CAST(COALESCE(NEW.total_fee, 0) AS INTEGER) <= 0
                    OR CAST(COALESCE(NEW.initial_payment, 0) AS INTEGER) < 0
                    OR CAST(COALESCE(NEW.initial_payment, 0) AS INTEGER) > CAST(COALESCE(NEW.total_fee, 0) AS INTEGER)
                    OR upper(trim(COALESCE(NEW.payment_method, ''))) NOT IN ('CHECK', 'CASH', 'CARD', 'TRANSFER')
                BEGIN
                    SELECT RAISE(ABORT, 'registrations violates course_name/total_fee/payment_method integrity rules');
                END
            """),
            ('trg_payments_integrity_insert', """
                CREATE TRIGGER trg_payments_integrity_insert
                BEFORE INSERT ON payments
                FOR EACH ROW
                WHEN CAST(COALESCE(NEW.amount, 0) AS INTEGER) <= 0
                    OR upper(trim(COALESCE(NEW.payment_method, ''))) NOT IN ('CHECK', 'CASH_INCOME')
                    OR (
                        upper(trim(COALESCE(NEW.payment_method, ''))) = 'CHECK'
                        AND NEW.check_id IS NULL
                    )
                    OR (
                        upper(trim(COALESCE(NEW.payment_method, ''))) = 'CASH_INCOME'
                        AND NEW.check_id IS NOT NULL
                    )
                BEGIN
                    SELECT RAISE(ABORT, 'payments violates amount/payment_method/check_id integrity rules');
                END
            """),
            ('trg_payments_integrity_update', """
                CREATE TRIGGER trg_payments_integrity_update
                BEFORE UPDATE OF amount, payment_method, check_id ON payments
                FOR EACH ROW
                WHEN CAST(COALESCE(NEW.amount, 0) AS INTEGER) <= 0
                    OR upper(trim(COALESCE(NEW.payment_method, ''))) NOT IN ('CHECK', 'CASH_INCOME')
                    OR (
                        upper(trim(COALESCE(NEW.payment_method, ''))) = 'CHECK'
                        AND NEW.check_id IS NULL
                    )
                    OR (
                        upper(trim(COALESCE(NEW.payment_method, ''))) = 'CASH_INCOME'
                        AND NEW.check_id IS NOT NULL
                    )
                BEGIN
                    SELECT RAISE(ABORT, 'payments violates amount/payment_method/check_id integrity rules');
                END
            """),
            ('trg_expenses_amount_integrity_insert', """
                CREATE TRIGGER trg_expenses_amount_integrity_insert
                BEFORE INSERT ON expenses
                FOR EACH ROW
                WHEN CAST(COALESCE(NEW.amount, 0) AS INTEGER) <= 0
                BEGIN
                    SELECT RAISE(ABORT, 'expenses.amount must be greater than zero');
                END
            """),
            ('trg_expenses_amount_integrity_update', """
                CREATE TRIGGER trg_expenses_amount_integrity_update
                BEFORE UPDATE OF amount ON expenses
                FOR EACH ROW
                WHEN CAST(COALESCE(NEW.amount, 0) AS INTEGER) <= 0
                BEGIN
                    SELECT RAISE(ABORT, 'expenses.amount must be greater than zero');
                END
            """),
        )

        for trigger_name, statement in trigger_statements:
            cur.execute(f'DROP TRIGGER IF EXISTS {trigger_name}')
            cur.execute(statement)

    @staticmethod
    def _normalize_national_code(value: object, row_id: int) -> str:
        digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
        if len(digits) != 10:
            return f'{row_id:010d}'[-10:]
        return digits

    @staticmethod
    def _normalize_phone_number(value: object, row_id: int) -> str:
        digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
        if len(digits) < 10:
            return f'09{row_id:08d}'[-10:]
        return digits

    @staticmethod
    def _next_unique_numeric_text(seed: int, length: int, used: set[str]) -> str:
        modulus = 10**length
        counter = max(0, int(seed))
        while True:
            candidate = f'{counter % modulus:0{length}d}'
            if candidate not in used:
                used.add(candidate)
                return candidate
            counter += 1

    @staticmethod
    def _next_unique_text(base: str, used: set[str]) -> str:
        candidate = str(base).strip() or 'SERIAL'
        if candidate not in used:
            used.add(candidate)
            return candidate

        counter = 1
        while True:
            attempt = f'{candidate}-{counter}'
            if attempt not in used:
                used.add(attempt)
                return attempt
            counter += 1


    def create_registration_with_income(self, registration: Mapping[str, object], check_ids: Sequence[int]) -> int:
        return self._upsert_registration_with_income(None, registration, check_ids)

    def update_registration_with_income(self, registration_id: int, registration: Mapping[str, object], check_ids: Sequence[int]):
        self._upsert_registration_with_income(int(registration_id), registration, check_ids)

    def _upsert_registration_with_income(
        self,
        registration_id: int | None,
        registration: Mapping[str, object],
        check_ids: Sequence[int],
    ) -> int:
        with self.transaction() as conn:
            cur = conn.cursor()

            customer_id = int(registration.get('customer_id') or 0)
            course_name = str(registration.get('course_name') or '').strip()
            registration_date = str(registration.get('registration_date') or '').strip()
            total_fee = int(registration.get('total_fee') or 0)
            initial_payment = int(registration.get('initial_payment') or 0)
            payment_method = str(registration.get('payment_method') or 'CASH').strip().upper()
            description = str(registration.get('description') or '').strip()
            normalized_check_ids = self._clean_positive_ids(check_ids)

            if len(set(normalized_check_ids)) != len(normalized_check_ids):
                raise ValueError('چک تکراری انتخاب شده است.')

            check_amount_by_id = self._fetch_check_amounts(cur, normalized_check_ids)
            if len(check_amount_by_id) != len(set(normalized_check_ids)):
                raise ValueError('یک یا چند چک انتخاب شده معتبر نیست.')

            checks_total = sum(check_amount_by_id[int(cid)] for cid in normalized_check_ids)
            if checks_total > total_fee:
                raise ValueError('جمع مبالغ چک ها نمی تواند بیشتر از مبلغ کل ثبت نام باشد.')

            if initial_payment < 0:
                raise ValueError('پرداخت اولیه نمی تواند منفی باشد.')
            if initial_payment > total_fee:
                raise ValueError('پرداخت اولیه نمی تواند بیشتر از شهریه کل باشد.')

            covered_amount = checks_total + initial_payment
            if covered_amount > total_fee:
                raise ValueError('جمع پرداخت اولیه و چک ها نمی تواند بیشتر از شهریه کل باشد.')
            if initial_payment > 0 and payment_method == 'CHECK':
                raise ValueError('برای پرداخت اولیه باید روش پرداخت غیرچک انتخاب شود.')
            if covered_amount == 0 and payment_method == 'CHECK':
                raise ValueError('برای روش پرداخت چک، حداقل یک چک یا مبلغ اولیه ثبت کنید.')

            effective_payment_method = (
                'CHECK'
                if normalized_check_ids and covered_amount == total_fee and initial_payment == 0
                else payment_method
            )

            if registration_id is None:
                cur.execute(
                    """
                    INSERT INTO registrations(
                        customer_id, course_name, registration_date, total_fee, initial_payment, payment_method, description, created_at, updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        customer_id,
                        course_name,
                        registration_date,
                        total_fee,
                        initial_payment,
                        effective_payment_method,
                        description,
                    ),
                )
                registration_id = int(cur.lastrowid)
            else:
                existing = cur.execute(
                    'SELECT id FROM registrations WHERE id = ? LIMIT 1',
                    (int(registration_id),),
                ).fetchone()
                if existing is None:
                    raise ValueError('ثبت نام مورد نظر یافت نشد.')

                cur.execute(
                    """
                    UPDATE registrations
                    SET customer_id = ?, course_name = ?, registration_date = ?, total_fee = ?,
                        initial_payment = ?, payment_method = ?, description = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        customer_id,
                        course_name,
                        registration_date,
                        total_fee,
                        initial_payment,
                        effective_payment_method,
                        description,
                        int(registration_id),
                    ),
                )
                cur.execute('DELETE FROM payments WHERE registration_id = ?', (int(registration_id),))

            self._ensure_checks_not_linked_elsewhere(
                cur,
                normalized_check_ids,
                int(registration_id),
            )

            for check_id in normalized_check_ids:
                cur.execute(
                    """
                    INSERT INTO payments(registration_id, amount, payment_method, check_id, payment_date, notes)
                    VALUES(?, ?, 'CHECK', ?, ?, ?)
                    """,
                    (
                        int(registration_id),
                        check_amount_by_id[int(check_id)],
                        int(check_id),
                        registration_date,
                        description,
                    ),
                )

            if initial_payment > 0:
                cur.execute(
                    """
                    INSERT INTO payments(registration_id, amount, payment_method, check_id, payment_date, notes)
                    VALUES(?, ?, 'CASH_INCOME', NULL, ?, ?)
                    """,
                    (int(registration_id), initial_payment, registration_date, description),
                )

            return int(registration_id)

    def get_check_amounts_by_ids(self, check_ids: Sequence[int]) -> dict[int, int]:
        cleaned = self._clean_positive_ids(check_ids)
        if not cleaned:
            return {}
        placeholders = ','.join('?' for _ in cleaned)
        rows = self.fetchall(
            f"SELECT id, amount FROM checks WHERE id IN ({placeholders})",
            tuple(cleaned),
        )
        return {int(row['id']): int(row['amount'] or 0) for row in rows}

    def sum_checks_amount_by_ids(self, check_ids: Sequence[int]) -> int:
        return sum(self.get_check_amounts_by_ids(check_ids).values())

    def get_registration(self, registration_id: int):
        rows = self.fetchall(
            """
            SELECT
                r.*,
                c.name AS customer_name,
                c.national_code,
                c.phone,
                COALESCE(SUM(p.amount), 0) AS income_total,
                COALESCE(SUM(CASE WHEN p.payment_method = 'CHECK' THEN p.amount ELSE 0 END), 0) AS check_income_total,
                COALESCE(SUM(CASE WHEN p.payment_method = 'CASH_INCOME' THEN p.amount ELSE 0 END), 0) AS non_check_income_total,
                COUNT(p.id) AS payment_count,
                SUM(CASE WHEN p.check_id IS NOT NULL THEN 1 ELSE 0 END) AS check_count
            FROM registrations r
            JOIN customers c ON c.id = r.customer_id
            LEFT JOIN payments p ON p.registration_id = r.id
            WHERE r.id = ?
            GROUP BY r.id, c.id
            """,
            (int(registration_id),),
        )
        return rows[0] if rows else None

    def list_registrations_by_customer(self, customer_id: int):
        return self.list_registrations(customer_id=int(customer_id))

    def list_registrations(self, customer_id: int | None = None, search_text: str = ''):
        query = """
            SELECT
                r.*,
                c.name AS customer_name,
                c.national_code,
                c.phone,
                COALESCE(SUM(p.amount), 0) AS income_total,
                COALESCE(SUM(CASE WHEN p.payment_method = 'CHECK' THEN p.amount ELSE 0 END), 0) AS check_income_total,
                COALESCE(SUM(CASE WHEN p.payment_method = 'CASH_INCOME' THEN p.amount ELSE 0 END), 0) AS non_check_income_total,
                COUNT(p.id) AS payment_count,
                SUM(CASE WHEN p.check_id IS NOT NULL THEN 1 ELSE 0 END) AS check_count
            FROM registrations r
            JOIN customers c ON c.id = r.customer_id
            LEFT JOIN payments p ON p.registration_id = r.id
            WHERE 1 = 1
        """
        params: list[object] = []

        if customer_id is not None:
            query += ' AND r.customer_id = ?'
            params.append(int(customer_id))

        normalized_search = str(search_text or '').strip().lower()
        if normalized_search:
            like = f'%{normalized_search}%'
            query += """
                AND (
                    lower(c.name) LIKE ?
                    OR lower(COALESCE(c.national_code, '')) LIKE ?
                    OR lower(COALESCE(c.phone, '')) LIKE ?
                    OR lower(r.course_name) LIKE ?
                    OR lower(COALESCE(r.description, '')) LIKE ?
                )
            """
            params.extend([like, like, like, like, like])

        query += ' GROUP BY r.id, c.id ORDER BY r.registration_date DESC, r.id DESC'
        return self.fetchall(query, tuple(params))

    def delete_registration(self, registration_id: int):
        with self.transaction() as conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM registrations WHERE id = ?', (int(registration_id),))

    def list_payments_by_registration(self, registration_id: int):
        return self.fetchall(
            """
            SELECT p.*, c.serial_7, c.due_date, r.payment_method AS registration_payment_method
            FROM payments p
            LEFT JOIN checks c ON c.id = p.check_id
            JOIN registrations r ON r.id = p.registration_id
            WHERE p.registration_id = ?
            ORDER BY p.payment_date DESC, p.id DESC
            """,
            (int(registration_id),),
        )

    def list_check_ids_by_registration(self, registration_id: int) -> list[int]:
        rows = self.fetchall(
            'SELECT check_id FROM payments WHERE registration_id = ? AND check_id IS NOT NULL ORDER BY id ASC',
            (int(registration_id),),
        )
        return [int(row['check_id']) for row in rows if row['check_id'] is not None]

    def list_available_checks_for_registration(self, registration_id: int | None = None):
        owner_registration_id = int(registration_id) if registration_id is not None else -1
        return self.fetchall(
            """
            SELECT c.*
            FROM checks c
            WHERE (
                c.id IN (
                    SELECT p.check_id
                    FROM payments p
                    WHERE p.check_id IS NOT NULL AND p.registration_id = ?
                )
                OR (
                    upper(COALESCE(c.status, '')) = 'PENDING'
                    AND c.id NOT IN (
                        SELECT p.check_id
                        FROM payments p
                        WHERE p.check_id IS NOT NULL AND p.registration_id <> ?
                    )
                )
            )
            ORDER BY c.due_date ASC, c.id DESC
            """,
            (owner_registration_id, owner_registration_id),
        )

    def get_total_income(self) -> int:
        row = self.fetchone('SELECT COALESCE(SUM(amount), 0) AS total FROM payments')
        return int((row['total'] if row else 0) or 0)

    def get_total_expenses(self) -> int:
        row = self.fetchone('SELECT COALESCE(SUM(amount), 0) AS total FROM expenses')
        return int((row['total'] if row else 0) or 0)

    def get_financial_snapshot(self) -> dict[str, int]:
        total_income = self.get_total_income()
        total_expenses = self.get_total_expenses()
        return {
            'total_income': total_income,
            'total_expenses': total_expenses,
            'net_income': total_income - total_expenses,
        }
