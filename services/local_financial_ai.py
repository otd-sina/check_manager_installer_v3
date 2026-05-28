from __future__ import annotations

import re
from typing import Any


OPEN_STATUSES = {'PENDING', 'DEPOSITED', 'ENDORSED'}
PAID_STATUSES = {'PAID', 'CLEARED'}
BOUNCED_STATUSES = {'BOUNCED', 'RETURNED'}

_DIGIT_TRANSLATION = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_text(value: Any) -> str:
    return str(value or '').strip()


def _normalize_digits(value: Any) -> str:
    return _normalize_text(value).translate(_DIGIT_TRANSLATION)


def _extract_year_month(value: Any) -> tuple[int, int] | None:
    text = _normalize_digits(value).replace('-', '/').strip()
    parts = text.split('/')
    if len(parts) < 2:
        return None

    try:
        year = int(parts[0])
        month = int(parts[1])
    except ValueError:
        return None

    if not (1 <= month <= 12):
        return None
    return year, month


def _format_period(year: int, month: int) -> str:
    return f'{year}/{month:02d}'


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    y = int(year)
    m = int(month)
    step = 1 if delta >= 0 else -1
    for _ in range(abs(delta)):
        m += step
        if m > 12:
            y += 1
            m = 1
        elif m < 1:
            y -= 1
            m = 12
    return y, m


def _month_match(value: Any, year: int, month: int) -> bool:
    parsed = _extract_year_month(value)
    return bool(parsed and parsed[0] == year and parsed[1] == month)


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return ((current - previous) / abs(previous)) * 100.0


def _pct_text(current: float, previous: float) -> str:
    value = _pct_change(current, previous)
    sign = '+' if value >= 0 else ''
    return f'{sign}{value:.1f}%'


def _std_dev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((item - mean) ** 2 for item in values) / len(values)
    return variance ** 0.5


def _monthly_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get('monthly_analytics') or []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        period_text = _normalize_text(row.get('period'))
        parsed = _extract_year_month(period_text)
        if not parsed:
            continue
        normalized.append(
            {
                'period': _format_period(parsed[0], parsed[1]),
                'year': parsed[0],
                'month': parsed[1],
                'income': _to_int(row.get('income')),
                'expense': _to_int(row.get('expense')),
                'net': _to_int(row.get('net')),
                'registrations': _to_int(row.get('registrations')),
                'checks_count': _to_int(row.get('checks_count')),
                'checks_amount': _to_int(row.get('checks_amount')),
            }
        )
    normalized.sort(key=lambda item: (item['year'], item['month']))
    return normalized


def _category_totals(expense_rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
    totals: dict[str, int] = {}
    for row in expense_rows:
        category = _normalize_text(row.get('category_name')) or 'سایر'
        totals[category] = totals.get(category, 0) + _to_int(row.get('amount'))
    return sorted(totals.items(), key=lambda item: item[1], reverse=True)


def _customer_income_totals(registrations_rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
    totals: dict[str, int] = {}
    for row in registrations_rows:
        name = _normalize_text(row.get('customer_name')) or 'نامشخص'
        totals[name] = totals.get(name, 0) + _to_int(row.get('income_total'))
    return sorted(totals.items(), key=lambda item: item[1], reverse=True)


def _compute_totals_from_rows(payload: dict[str, Any]) -> tuple[int, int]:
    registrations_rows = payload.get('registrations_rows') or []
    expense_rows = payload.get('expenses_rows') or []
    incomes = sum(_to_int(row.get('income_total')) for row in registrations_rows)
    expenses = sum(_to_int(row.get('amount')) for row in expense_rows)

    if not registrations_rows and not expense_rows:
        summary = payload.get('summary') or {}
        incomes = _to_int(summary.get('incomes'))
        expenses = _to_int(summary.get('expenses'))

    return incomes, expenses


def infer_requested_period(query: str, payload: dict[str, Any]) -> tuple[int, int] | None:
    text = _normalize_digits(query)

    direct = re.search(r'(\d{4})[/-](\d{1,2})', text)
    if direct:
        year = int(direct.group(1))
        month = int(direct.group(2))
        if 1 <= month <= 12:
            return year, month

    named_one = re.search(r'سال\s*(\d{4}).{0,12}?ماه\s*(\d{1,2})', text)
    if named_one:
        year = int(named_one.group(1))
        month = int(named_one.group(2))
        if 1 <= month <= 12:
            return year, month

    named_two = re.search(r'ماه\s*(\d{1,2}).{0,12}?سال\s*(\d{4})', text)
    if named_two:
        month = int(named_two.group(1))
        year = int(named_two.group(2))
        if 1 <= month <= 12:
            return year, month

    filters = payload.get('filters') or {}
    f_year = filters.get('year')
    f_month = filters.get('month')
    if f_year is not None and f_month is not None:
        try:
            year = int(f_year)
            month = int(f_month)
            if 1 <= month <= 12:
                return year, month
        except (TypeError, ValueError):
            pass

    rows = _monthly_rows(payload)
    if rows:
        last = rows[-1]
        return int(last['year']), int(last['month'])

    for container_name, date_key in (
        ('registrations_rows', 'registration_date'),
        ('expenses_rows', 'expense_date'),
        ('checks', 'due_date'),
    ):
        rows = payload.get(container_name) or []
        parsed_rows = [_extract_year_month(row.get(date_key)) for row in rows]
        parsed_rows = [item for item in parsed_rows if item]
        if parsed_rows:
            parsed_rows.sort()
            return parsed_rows[-1]

    return None


def build_single_month_payload(payload: dict[str, Any], year: int, month: int) -> dict[str, Any]:
    period_text = _format_period(year, month)
    prev_year, prev_month = _shift_month(year, month, -1)

    checks = [row for row in (payload.get('checks') or []) if _month_match(row.get('due_date'), year, month)]
    expense_rows = [
        row
        for row in (payload.get('expenses_rows') or [])
        if _month_match(row.get('expense_date'), year, month)
    ]
    registrations_rows = [
        row
        for row in (payload.get('registrations_rows') or [])
        if _month_match(row.get('registration_date'), year, month)
    ]

    prev_expense_rows = [
        row
        for row in (payload.get('expenses_rows') or [])
        if _month_match(row.get('expense_date'), prev_year, prev_month)
    ]
    prev_registrations_rows = [
        row
        for row in (payload.get('registrations_rows') or [])
        if _month_match(row.get('registration_date'), prev_year, prev_month)
    ]
    prev_checks = [
        row
        for row in (payload.get('checks') or [])
        if _month_match(row.get('due_date'), prev_year, prev_month)
    ]

    incomes = sum(_to_int(row.get('income_total')) for row in registrations_rows)
    expenses = sum(_to_int(row.get('amount')) for row in expense_rows)
    net = incomes - expenses
    checks_amount = sum(_to_int(row.get('amount')) for row in checks)

    prev_incomes = sum(_to_int(row.get('income_total')) for row in prev_registrations_rows)
    prev_expenses = sum(_to_int(row.get('amount')) for row in prev_expense_rows)

    category_totals = _category_totals(expense_rows)
    category_breakdown = [
        {'دسته بندی': category, 'مبلغ': amount, 'سهم درصدی': round((amount / expenses * 100), 1) if expenses else 0.0}
        for category, amount in category_totals
    ]

    open_risks = []
    for check in checks:
        status = _normalize_text(check.get('status')).upper()
        if status in OPEN_STATUSES:
            open_risks.append(
                {
                    'شناسه': check.get('id'),
                    'نام ثبتنام کننده': _normalize_text(check.get('registrant_name')),
                    'مبلغ': _to_int(check.get('amount')),
                    'تاریخ سررسید': _normalize_text(check.get('due_date')),
                    'وضعیت': status,
                }
            )

    month_row = {
        'period': period_text,
        'income': incomes,
        'expense': expenses,
        'net': net,
        'registrations': len(registrations_rows),
        'checks_count': len(checks),
        'checks_amount': checks_amount,
    }

    comparison_rows = [
        {
            'دوره': period_text,
            'درآمد': incomes,
            'هزینه': expenses,
            'خالص': net,
        },
        {
            'دوره': _format_period(prev_year, prev_month),
            'درآمد': prev_incomes,
            'هزینه': prev_expenses,
            'خالص': prev_incomes - prev_expenses,
        },
    ]

    return {
        'period_label': period_text,
        'filters': {'year': year, 'month': month},
        'summary': {
            'incomes': incomes,
            'expenses': expenses,
            'net': net,
            'registrations_count': len(registrations_rows),
            'checks_count': len(checks),
            'checks_amount': checks_amount,
        },
        'growth': {
            'incomes': _pct_text(incomes, prev_incomes),
            'expenses': _pct_text(expenses, prev_expenses),
            'registrations': _pct_text(len(registrations_rows), len(prev_registrations_rows)),
            'checks': _pct_text(len(checks), len(prev_checks)),
        },
        'monthly_analytics': [month_row],
        'monthly_comparison': comparison_rows,
        'category_breakdown': category_breakdown,
        'upcoming_risks': open_risks,
        'checks': checks,
        'expenses_rows': expense_rows,
        'registrations_rows': registrations_rows,
    }


def build_financial_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    registrations_rows = payload.get('registrations_rows') or []
    expense_rows = payload.get('expenses_rows') or []
    checks = payload.get('checks') or []

    incomes, expenses = _compute_totals_from_rows(payload)
    net = incomes - expenses

    summary = payload.get('summary') or {}
    if not registrations_rows and not expense_rows and summary:
        net = _to_int(summary.get('net'))

    categories_ranked = _category_totals(expense_rows)
    top_categories = categories_ranked[:3]

    customers_ranked = _customer_income_totals(registrations_rows)
    top_customers = customers_ranked[:3]

    open_checks_amount = 0
    open_checks_count = 0
    paid_checks_amount = 0
    paid_checks_count = 0
    bounced_checks_amount = 0
    bounced_checks_count = 0

    for item in checks:
        status = _normalize_text(item.get('status')).upper()
        amount = _to_int(item.get('amount'))
        if status in OPEN_STATUSES:
            open_checks_count += 1
            open_checks_amount += amount
        elif status in PAID_STATUSES:
            paid_checks_count += 1
            paid_checks_amount += amount
        elif status in BOUNCED_STATUSES:
            bounced_checks_count += 1
            bounced_checks_amount += amount

    total_check_flow = open_checks_count + paid_checks_count
    collection_rate = (paid_checks_count / total_check_flow * 100.0) if total_check_flow else 0.0

    expense_ratio = (expenses / incomes * 100.0) if incomes > 0 else 0.0
    margin_ratio = (net / incomes * 100.0) if incomes > 0 else 0.0

    top1_share = (top_categories[0][1] / expenses * 100.0) if expenses and top_categories else 0.0
    top3_share = (
        sum(item[1] for item in top_categories) / expenses * 100.0 if expenses and top_categories else 0.0
    )

    monthly_rows = _monthly_rows(payload)
    recent = monthly_rows[-6:]
    recent_income = [float(item['income']) for item in recent]
    recent_expense = [float(item['expense']) for item in recent]
    recent_net = [float(item['net']) for item in recent]

    avg_income_3m = sum(recent_income[-3:]) / len(recent_income[-3:]) if recent_income[-3:] else 0.0
    avg_expense_3m = sum(recent_expense[-3:]) / len(recent_expense[-3:]) if recent_expense[-3:] else 0.0
    avg_net_3m = sum(recent_net[-3:]) / len(recent_net[-3:]) if recent_net[-3:] else 0.0

    net_volatility = _std_dev(recent_net)

    income_change_pct = 0.0
    expense_change_pct = 0.0
    net_change_pct = 0.0
    if len(monthly_rows) >= 2:
        prev = monthly_rows[-2]
        curr = monthly_rows[-1]
        income_change_pct = _pct_change(curr['income'], prev['income'])
        expense_change_pct = _pct_change(curr['expense'], prev['expense'])
        net_change_pct = _pct_change(curr['net'], prev['net'])

    expected_next_net = avg_net_3m

    return {
        'period_label': _normalize_text(payload.get('period_label')) or '-',
        'incomes': incomes,
        'expenses': expenses,
        'net': net,
        'expense_ratio': expense_ratio,
        'margin_ratio': margin_ratio,
        'registrations_count': _to_int(summary.get('registrations_count') or len(registrations_rows)),
        'checks_count': _to_int(summary.get('checks_count') or len(checks)),
        'checks_amount': _to_int(summary.get('checks_amount') or sum(_to_int(item.get('amount')) for item in checks)),
        'open_checks_count': open_checks_count,
        'open_checks_amount': open_checks_amount,
        'paid_checks_count': paid_checks_count,
        'paid_checks_amount': paid_checks_amount,
        'bounced_checks_count': bounced_checks_count,
        'bounced_checks_amount': bounced_checks_amount,
        'collection_rate': collection_rate,
        'top_categories': top_categories,
        'all_categories': categories_ranked,
        'top_customers': top_customers,
        'top1_share': top1_share,
        'top3_share': top3_share,
        'income_change_pct': income_change_pct,
        'expense_change_pct': expense_change_pct,
        'net_change_pct': net_change_pct,
        'avg_income_3m': avg_income_3m,
        'avg_expense_3m': avg_expense_3m,
        'avg_net_3m': avg_net_3m,
        'net_volatility': net_volatility,
        'expected_next_net': expected_next_net,
        'monthly_rows': monthly_rows,
    }


def build_persian_summary(snapshot: dict[str, Any]) -> str:
    incomes = _to_int(snapshot.get('incomes'))
    expenses = _to_int(snapshot.get('expenses'))
    net = _to_int(snapshot.get('net'))

    top_categories = snapshot.get('top_categories') or []
    top_labels = ' و '.join(name for name, _ in top_categories[:2]) if top_categories else 'بدون دسته بندی شاخص'

    collection_rate = _to_float(snapshot.get('collection_rate'))
    expense_ratio = _to_float(snapshot.get('expense_ratio'))

    return (
        f"در بازه {snapshot.get('period_label', '-')} مجموع درآمد {incomes:,}، مجموع هزینه ها {expenses:,} "
        f"و تراز خالص {net:+,} است. بیشترین هزینه ها در دسته های {top_labels} ثبت شده و "
        f"نرخ وصول چک {collection_rate:.1f}% با نسبت هزینه به درآمد {expense_ratio:.1f}% بوده است."
    )


def _build_risks(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []

    net = _to_int(snapshot.get('net'))
    if net < 0:
        risks.append(
            {
                'title': 'تراز خالص منفی',
                'severity': 'HIGH',
                'count': 1,
                'description': 'هزینه ها از درآمدها بیشتر شده اند و نقدینگی نیاز به اصلاح فوری دارد.',
            }
        )

    expense_ratio = _to_float(snapshot.get('expense_ratio'))
    if expense_ratio > 95:
        severity = 'HIGH'
    elif expense_ratio > 80:
        severity = 'MEDIUM'
    else:
        severity = ''
    if severity:
        risks.append(
            {
                'title': 'نسبت هزینه به درآمد بالا',
                'severity': severity,
                'count': 1,
                'description': 'حاشیه سود فشرده شده و فضای مانور عملیاتی کاهش یافته است.',
            }
        )

    if _to_int(snapshot.get('open_checks_count')) > 0:
        risks.append(
            {
                'title': 'ریسک چک های باز',
                'severity': 'MEDIUM',
                'count': _to_int(snapshot.get('open_checks_count')),
                'description': 'چک های باز می توانند جریان نقدی ماه های آتی را تحت فشار قرار دهند.',
            }
        )

    if _to_int(snapshot.get('bounced_checks_count')) > 0:
        risks.append(
            {
                'title': 'سابقه چک برگشتی/عودتی',
                'severity': 'HIGH',
                'count': _to_int(snapshot.get('bounced_checks_count')),
                'description': 'وصول برخی چک ها ناموفق بوده و احتمال تاخیر نقدینگی بالا است.',
            }
        )

    if _to_float(snapshot.get('top1_share')) > 45:
        risks.append(
            {
                'title': 'تمرکز هزینه بالا در یک دسته',
                'severity': 'MEDIUM',
                'count': 1,
                'description': 'وابستگی زیاد به یک دسته هزینه ریسک انحراف بودجه را افزایش می دهد.',
            }
        )

    if _to_float(snapshot.get('net_volatility')) > abs(_to_float(snapshot.get('avg_net_3m'))) * 1.2:
        risks.append(
            {
                'title': 'نوسان شدید تراز ماهانه',
                'severity': 'MEDIUM',
                'count': 1,
                'description': 'تراز ماهانه پایدار نیست و برنامه ریزی نقدینگی را دشوار می کند.',
            }
        )

    return risks


def _build_recommendations(snapshot: dict[str, Any], risks: list[dict[str, Any]]) -> list[str]:
    recommendations = [
        'پایش هفتگی بودجه برای 3 دسته پرهزینه و ثبت انحراف نسبت به سقف هدف.',
        'طراحی تقویم وصول چک ها و اولویت بندی پیگیری بر اساس مبلغ و سررسید.',
        'تهیه گزارش ماهانه جریان نقدی و مقایسه با میانگین 3 ماهه برای اصلاح سریع.',
    ]

    if _to_int(snapshot.get('net')) < 0:
        recommendations.insert(0, 'تا بازگشت تراز به محدوده مثبت، هزینه های غیرضروری و تعهدات قابل تعویق را کنترل کنید.')

    if _to_float(snapshot.get('top1_share')) > 45:
        recommendations.append('برای دسته هزینه غالب سقف مصوب و تایید دو مرحله ای پرداخت تعریف کنید.')

    if _to_int(snapshot.get('bounced_checks_count')) > 0:
        recommendations.append('برای مشتریان پرریسک، سیاست پیش پرداخت یا ضمانت مکمل اعمال کنید.')

    if any(item.get('title') == 'ریسک چک های باز' for item in risks):
        recommendations.append('سناریوی جایگزین نقدی برای حداقل 30 درصد از چک های باز آماده کنید.')

    return recommendations[:6]


def _build_trends(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {'metric': 'درآمد ماهانه', 'change_pct': round(_to_float(snapshot.get('income_change_pct')), 1)},
        {'metric': 'هزینه ماهانه', 'change_pct': round(_to_float(snapshot.get('expense_change_pct')), 1)},
        {'metric': 'خالص ماهانه', 'change_pct': round(_to_float(snapshot.get('net_change_pct')), 1)},
        {'metric': 'پیش بینی خالص ماه بعد', 'change_pct': round(_to_float(snapshot.get('expected_next_net')), 1)},
    ]


def build_structured_local_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = build_financial_snapshot(payload)
    summary_text = build_persian_summary(snapshot)
    risks = _build_risks(snapshot)
    recommendations = _build_recommendations(snapshot, risks)

    top_categories = snapshot.get('top_categories') or []
    top_categories_text = '، '.join(f'{name}: {amount:,}' for name, amount in top_categories) or 'داده ای موجود نیست'

    top_customers = snapshot.get('top_customers') or []
    top_customers_text = '، '.join(f'{name}: {amount:,}' for name, amount in top_customers) or 'داده ای موجود نیست'

    trends = _build_trends(snapshot)

    reasoning_steps = [
        'داده های ثبت نام، هزینه و چک از پایگاه داخلی استخراج و نرمال سازی شد.',
        'شاخص های کلیدی شامل درآمد، هزینه، تراز، نرخ وصول و تمرکز هزینه محاسبه شد.',
        'الگوهای تغییر ماهانه و میانگین متحرک 3 ماهه برای تخمین روند استفاده شد.',
        'ریسک ها بر اساس آستانه های عددی ثابت و قابل بازتولید استخراج شدند.',
    ]

    risk_items = [
        {
            'title': item.get('title', ''),
            'severity': item.get('severity', 'LOW'),
            'note': item.get('description', ''),
        }
        for item in risks
    ]

    automations = [
        'هشدار خودکار وقتی نسبت هزینه به درآمد از 85 درصد عبور کند.',
        'هشدار خودکار وقتی سهم دسته اول هزینه از 45 درصد بیشتر شود.',
        'یادآوری روزانه چک های باز نزدیک سررسید.',
    ]

    return {
        'source': 'LOCAL',
        'report': {
            'summary': summary_text,
            'key_metrics': {
                'period': snapshot.get('period_label', '-'),
                'incomes': f"{_to_int(snapshot.get('incomes')):,}",
                'expenses': f"{_to_int(snapshot.get('expenses')):,}",
                'net': f"{_to_int(snapshot.get('net')):+,}",
                'expense_ratio_pct': f"{_to_float(snapshot.get('expense_ratio')):.1f}",
                'margin_ratio_pct': f"{_to_float(snapshot.get('margin_ratio')):.1f}",
                'collection_rate_pct': f"{_to_float(snapshot.get('collection_rate')):.1f}",
                'open_checks_amount': f"{_to_int(snapshot.get('open_checks_amount')):,}",
                'top_expense_categories': top_categories_text,
                'top_income_customers': top_customers_text,
                'avg_net_3m': f"{_to_int(snapshot.get('avg_net_3m')):+,}",
            },
            'risks': risks,
            'trends': trends,
            'recommendations': recommendations,
            'reasoning_steps': reasoning_steps,
        },
        'insights': [
            summary_text,
            f"سهم دسته پرهزینه اول از کل هزینه {_to_float(snapshot.get('top1_share')):.1f}% است.",
            f"میانگین خالص 3 ماه اخیر {int(_to_float(snapshot.get('avg_net_3m'))):+,} بوده است.",
        ],
        'recommendations': recommendations,
        'risk_items': risk_items,
        'automations': automations,
        'api_commentary': 'این تحلیل کاملا محلی، قطعی و بدون اتصال شبکه تولید شده است.',
    }


def answer_local_query(query: str, payload: dict[str, Any]) -> dict[str, Any]:
    text = _normalize_text(query)
    if not text:
        return {
            'answer': 'لطفا یک سوال معتبر وارد کنید.',
            'source': 'LOCAL',
            'reasoning_steps': ['سوال خالی بود و پاسخی تولید نشد.'],
            'recommendations': [],
        }

    snapshot = build_financial_snapshot(payload)
    summary_text = build_persian_summary(snapshot)
    risks = _build_risks(snapshot)
    recommendations = _build_recommendations(snapshot, risks)

    lowered = _normalize_digits(text).lower()

    if any(key in lowered for key in ('خلاصه', 'summary', 'وضعیت کلی', 'overall')):
        answer = summary_text
    elif any(key in lowered for key in ('دسته', 'category', 'گروه هزینه')):
        categories = snapshot.get('top_categories') or []
        if categories:
            answer = 'پرهزینه ترین دسته ها: ' + '، '.join(
                f'{name} ({amount:,})' for name, amount in categories
            )
        else:
            answer = 'دسته بندی هزینه معناداری برای این بازه ثبت نشده است.'
    elif any(key in lowered for key in ('روند', 'trend', 'ماهانه')):
        answer = (
            f"تغییر درآمد {_to_float(snapshot.get('income_change_pct')):+.1f}%، "
            f"تغییر هزینه {_to_float(snapshot.get('expense_change_pct')):+.1f}% و "
            f"تغییر خالص {_to_float(snapshot.get('net_change_pct')):+.1f}% بوده است."
        )
    elif any(key in lowered for key in ('ریسک', 'risk')):
        if risks:
            answer = 'ریسک های اصلی: ' + '، '.join(item.get('title', '-') for item in risks)
        else:
            answer = 'بر اساس داده های فعلی، ریسک برجسته ای شناسایی نشده است.'
    elif any(key in lowered for key in ('پیشنهاد', 'recommend', 'راهکار')):
        answer = 'اقدام های پیشنهادی: ' + ' | '.join(recommendations[:3])
    elif any(key in lowered for key in ('نقد', 'cash', 'تراز', 'خالص', 'balance', 'net')):
        answer = (
            f"تراز خالص {_to_int(snapshot.get('net')):+,} است، "
            f"نسبت هزینه به درآمد {_to_float(snapshot.get('expense_ratio')):.1f}% "
            f"و نرخ وصول چک {_to_float(snapshot.get('collection_rate')):.1f}% می باشد."
        )
    elif any(key in lowered for key in ('درآمد', 'income', 'مشتری')):
        top_customers = snapshot.get('top_customers') or []
        customer_text = '، '.join(f'{name} ({amount:,})' for name, amount in top_customers) if top_customers else 'داده کافی نیست'
        answer = (
            f"مجموع درآمد این بازه {_to_int(snapshot.get('incomes')):,} است. "
            f"مشتریان با بیشترین سهم درآمد: {customer_text}."
        )
    else:
        answer = summary_text

    return {
        'answer': answer,
        'source': 'LOCAL',
        'reasoning_steps': [
            'پاسخ با قواعد تحلیلی محلی و مبتنی بر داده های ثبت شده تولید شد.',
            'هیچ سرویس خارجی یا API در این فرآیند استفاده نشده است.',
        ],
        'recommendations': recommendations,
    }
