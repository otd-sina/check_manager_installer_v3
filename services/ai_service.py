from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from config import EXPORT_DIR
from services.local_financial_ai import (
    answer_local_query,
    build_single_month_payload,
    build_structured_local_analysis,
    infer_requested_period,
)


logger = logging.getLogger(__name__)

CONNECTED = 'CONNECTED'
DISCONNECTED = 'DISCONNECTED'
RECONNECTING = 'RECONNECTING'

_DIGIT_TRANSLATION = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')


class AIServiceError(RuntimeError):
    """Base exception for local analysis service failures."""


class AIConfigurationError(AIServiceError):
    """Kept for backward compatibility with previous API-based design."""


class AIConnectivityError(AIServiceError):
    """Kept for backward compatibility with previous API-based design."""


class AIResponseError(AIServiceError):
    """Kept for backward compatibility with previous API-based design."""


class AIService:
    """Advanced offline deterministic financial analysis service (no network calls)."""

    def __init__(
        self,
        check_service,
        expense_service,
        registration_service,
        export_service,
        api_url: str = '',
        api_key: str = '',
        model: str = '',
        timeout_sec: int = 0,
        healthcheck_ttl_sec: int = 0,
        max_retries: int = 0,
        retry_backoff_sec: float = 0.0,
        autoreconnect_enabled: bool = False,
        reconnect_interval_sec: float = 0.0,
        reconnect_backoff_max_sec: float = 0.0,
    ):
        # Accepted only for compatibility with old call sites.
        _ = (
            api_url,
            api_key,
            model,
            timeout_sec,
            healthcheck_ttl_sec,
            max_retries,
            retry_backoff_sec,
            autoreconnect_enabled,
            reconnect_interval_sec,
            reconnect_backoff_max_sec,
        )

        self.check_service = check_service
        self.expense_service = expense_service
        self.registration_service = registration_service
        self.export_service = export_service

        self._connection_state = CONNECTED
        self._last_api_error = ''
        self._auto_export_state_path = Path(EXPORT_DIR) / '.monthly_export_state.json'

    @property
    def api_enabled(self) -> bool:
        return True

    @property
    def last_api_error(self) -> str:
        return self._last_api_error

    def get_connection_state(self) -> str:
        return self._connection_state

    def force_reconnect(self) -> str:
        self._connection_state = CONNECTED
        self._last_api_error = ''
        return self._connection_state

    def get_runtime_mode(self) -> str:
        return 'LOCAL Advanced Offline'

    def test_connection(self, force: bool = True) -> dict[str, Any]:
        _ = force
        self._connection_state = CONNECTED
        self._last_api_error = ''
        return {
            'ok': True,
            'status': 'LOCAL_READY',
            'latency_ms': 0,
            'error': '',
            'endpoint': 'local://advanced-offline-engine',
            'state': self._connection_state,
        }

    def check_api_health(self, force: bool = False) -> bool:
        _ = force
        self._connection_state = CONNECTED
        self._last_api_error = ''
        return True

    def generate_insights(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.generate_structured_analysis(payload)

    def generate_structured_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = build_structured_local_analysis(payload or {})
            self._connection_state = CONNECTED
            self._last_api_error = ''
            return result
        except Exception as exc:  # pragma: no cover
            self._connection_state = DISCONNECTED
            self._last_api_error = str(exc)
            logger.exception('Local financial analysis failed: %s', exc)
            return self._unavailable_analysis_result(str(exc))

    def answer_query(self, query: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload or {}
        try:
            export_result = self._maybe_handle_export_request(query, data)
            if export_result is not None:
                self._connection_state = CONNECTED
                self._last_api_error = ''
                return export_result

            answer = answer_local_query(query, data)
            self._connection_state = CONNECTED
            self._last_api_error = ''
            return answer
        except Exception as exc:  # pragma: no cover
            self._connection_state = DISCONNECTED
            self._last_api_error = str(exc)
            logger.exception('Local financial Q&A failed: %s', exc)
            return {
                'answer': 'خطا در پردازش تحلیل محلی. لطفا دوباره تلاش کنید.',
                'source': 'LOCAL',
                'reasoning_steps': ['خطا در پردازش داده های محلی رخ داد.'],
                'recommendations': [],
            }

    def export_monthly_reports(
        self,
        payload: dict[str, Any],
        year: int,
        month: int,
        *,
        export_excel: bool = True,
        export_pdf: bool = True,
    ) -> list[Path]:
        if not export_excel and not export_pdf:
            raise ValueError('At least one output format must be enabled.')
        if not (1 <= int(month) <= 12):
            raise ValueError('Month must be between 1 and 12.')

        month_payload = self._build_month_payload_with_analysis(payload, year, month)
        return self._export_month_payload(
            month_payload,
            year,
            month,
            export_excel=export_excel,
            export_pdf=export_pdf,
        )

    def _export_month_payload(
        self,
        month_payload: dict[str, Any],
        year: int,
        month: int,
        *,
        export_excel: bool,
        export_pdf: bool,
    ) -> list[Path]:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        saved_paths: list[Path] = []

        if export_excel:
            excel_path = EXPORT_DIR / f'monthly_analytics_{year}_{month:02d}_{timestamp}.xlsx'
            saved_paths.append(self.export_service.export_dashboard_analytics_to_excel(excel_path, month_payload))

        if export_pdf:
            pdf_path = EXPORT_DIR / f'monthly_analytics_{year}_{month:02d}_{timestamp}.pdf'
            saved_paths.append(self._export_pdf_report(pdf_path, month_payload))

        return saved_paths

    def _build_month_payload_with_analysis(self, payload: dict[str, Any], year: int, month: int) -> dict[str, Any]:
        month_payload = build_single_month_payload(payload, year, month)
        month_analysis = build_structured_local_analysis(month_payload)
        month_payload['ai_report'] = month_analysis.get('report') or {}
        month_payload['insights'] = month_analysis.get('insights') or []
        month_payload['recommendations'] = month_analysis.get('recommendations') or []
        month_payload['ai_source'] = 'LOCAL'
        return month_payload

    @staticmethod
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

    @staticmethod
    def _available_latest_period(payload: dict[str, Any]) -> tuple[int, int] | None:
        rows = payload.get('monthly_analytics') or []
        latest: tuple[int, int] | None = None
        for row in rows:
            period = str((row or {}).get('period') or '').strip().replace('-', '/')
            parts = period.split('/')
            if len(parts) < 2:
                continue
            try:
                year = int(parts[0])
                month = int(parts[1])
            except ValueError:
                continue
            if not (1 <= month <= 12):
                continue
            candidate = (year, month)
            if latest is None or candidate > latest:
                latest = candidate
        return latest

    def _load_auto_export_state(self) -> dict[str, str]:
        try:
            if not self._auto_export_state_path.exists():
                return {}
            return json.loads(self._auto_export_state_path.read_text(encoding='utf-8'))
        except Exception:
            logger.exception('Auto monthly export state is unreadable, resetting state.')
            return {}

    def _save_auto_export_state(self, state: dict[str, str]) -> None:
        self._auto_export_state_path.parent.mkdir(parents=True, exist_ok=True)
        self._auto_export_state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

    @staticmethod
    def _normalize_format_flags(formats_text: str) -> tuple[bool, bool]:
        raw = (formats_text or '').strip().lower()
        if not raw:
            return True, True
        tokens = {item.strip() for item in raw.split(',') if item.strip()}
        export_excel = bool(tokens & {'excel', 'xlsx', 'اکسل'})
        export_pdf = bool(tokens & {'pdf', 'پی دی اف', 'پی‌دی‌اف'})
        if not export_excel and not export_pdf:
            return True, True
        return export_excel, export_pdf

    def run_auto_monthly_export(
        self,
        payload: dict[str, Any],
        *,
        enabled: bool,
        formats_text: str = 'excel,pdf',
        month_offset: int = -1,
        now: datetime | None = None,
    ) -> list[Path]:
        if not enabled:
            return []

        latest = self._available_latest_period(payload or {})
        if not latest:
            logger.info('Auto monthly export skipped: no monthly analytics rows available.')
            return []

        base_year, base_month = latest
        target_year, target_month = self._shift_month(base_year, base_month, int(month_offset))
        export_excel, export_pdf = self._normalize_format_flags(formats_text)
        if not export_excel and not export_pdf:
            return []

        state = self._load_auto_export_state()
        period_key = f'{target_year:04d}-{target_month:02d}'
        stamp = (now or datetime.now()).strftime('%Y-%m')
        dedupe_key = f'{period_key}|{stamp}|{int(export_excel)}{int(export_pdf)}'
        if state.get('last_auto_monthly_export') == dedupe_key:
            logger.info('Auto monthly export skipped; already completed for key=%s', dedupe_key)
            return []

        paths = self.export_monthly_reports(
            payload,
            target_year,
            target_month,
            export_excel=export_excel,
            export_pdf=export_pdf,
        )
        if paths:
            state['last_auto_monthly_export'] = dedupe_key
            self._save_auto_export_state(state)
            logger.info(
                'Auto monthly export completed: period=%s formats=%s paths=%s',
                period_key,
                ('excel' if export_excel else '') + ('+pdf' if export_pdf else ''),
                ', '.join(str(path) for path in paths),
            )
        return paths

    def _maybe_handle_export_request(self, query: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        text = str(query or '').strip()
        if not text:
            return None

        lowered = text.translate(_DIGIT_TRANSLATION).lower()
        wants_export = any(
            key in lowered
            for key in ('خروجی', 'گزارش', 'export', 'excel', 'اکسل', 'pdf', 'پی دی اف', 'پی‌دی‌اف')
        )
        if not wants_export:
            return None

        wants_excel = any(key in lowered for key in ('excel', 'اکسل', 'xlsx'))
        wants_pdf = any(key in lowered for key in ('pdf', 'پی دی اف', 'پی‌دی‌اف'))
        if not wants_excel and not wants_pdf:
            # If format is not explicitly specified, default to both formats.
            wants_excel = True
            wants_pdf = True

        requested_period = infer_requested_period(text, payload)
        if not requested_period:
            return {
                'answer': (
                    'برای خروجی ماهانه، ماه مشخصی پیدا نشد. مثلا بنویسید: '
                    '"خروجی اکسل 1405/01" یا ابتدا فیلتر ماه را در داشبورد انتخاب کنید.'
                ),
                'source': 'LOCAL',
                'reasoning_steps': ['تشخیص دوره ماهانه از متن یا فیلتر داشبورد ناموفق بود.'],
                'recommendations': [],
            }

        year, month = requested_period
        saved_paths = self.export_monthly_reports(
            payload,
            year,
            month,
            export_excel=wants_excel,
            export_pdf=wants_pdf,
        )

        if not saved_paths:
            return {
                'answer': 'فرمت خروجی مشخص نشد. از واژه های Excel/اکسل یا PDF استفاده کنید.',
                'source': 'LOCAL',
                'reasoning_steps': ['کلیدواژه معتبر برای فرمت فایل یافت نشد.'],
                'recommendations': [],
            }

        rendered_paths = '\n'.join(str(path) for path in saved_paths)
        format_text = ' و '.join(path.suffix.replace('.', '').upper() for path in saved_paths)
        return {
            'answer': (
                f'گزارش یک ماهه {year}/{month:02d} با موفقیت در فرمت {format_text} ذخیره شد:\n{rendered_paths}'
            ),
            'source': 'LOCAL',
            'reasoning_steps': [
                'ماه هدف از متن سوال یا فیلترهای داشبورد تشخیص داده شد.',
                'داده های همان ماه جدا شد و تحلیل محلی جدید برای گزارش تولید شد.',
                'خروجی ها در مسیر exports پروژه ذخیره شدند.',
            ],
            'recommendations': build_structured_local_analysis(
                build_single_month_payload(payload, year, month)
            ).get('recommendations')
            or [],
        }

    def generate_professional_report(
        self,
        payload: dict[str, Any],
        report_format: str,
        destination: Path,
    ) -> Path:
        fmt = (report_format or '').strip().lower()
        path = Path(destination)

        if fmt == 'excel':
            return self.export_service.export_dashboard_analytics_to_excel(path, payload)
        if fmt == 'pdf':
            return self._export_pdf_report(path, payload)

        raise ValueError('Unsupported report format. Use "excel" or "pdf".')

    def _export_pdf_report(self, destination: Path, payload: dict[str, Any]) -> Path:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ModuleNotFoundError as exc:
            raise RuntimeError('PDF export requires reportlab. Please install reportlab first.') from exc

        summary = payload.get('summary') or {}
        insights = payload.get('insights') or []
        recommendations = payload.get('recommendations') or []
        structured_report = payload.get('ai_report') or {}

        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf = canvas.Canvas(str(destination), pagesize=A4)
        width, height = A4
        y = height - 48

        pdf.setFont('Helvetica-Bold', 14)
        pdf.drawString(40, y, 'Financial Local Analysis Report')
        y -= 28

        pdf.setFont('Helvetica', 10)
        pdf.drawString(40, y, f"Period: {payload.get('period_label', '-')}")
        y -= 18
        pdf.drawString(40, y, f"Income: {int(summary.get('incomes', 0) or 0):,}")
        y -= 16
        pdf.drawString(40, y, f"Expense: {int(summary.get('expenses', 0) or 0):,}")
        y -= 16
        pdf.drawString(40, y, f"Net: {int(summary.get('net', 0) or 0):+,}")
        y -= 26

        metrics = structured_report.get('key_metrics') or {}
        if metrics:
            pdf.setFont('Helvetica-Bold', 11)
            pdf.drawString(40, y, 'Key Metrics')
            y -= 16
            pdf.setFont('Helvetica', 10)
            for key, value in list(metrics.items())[:10]:
                pdf.drawString(48, y, f'- {key}: {value}')
                y -= 14
                if y < 80:
                    pdf.showPage()
                    y = height - 40
                    pdf.setFont('Helvetica', 10)
            y -= 8

        pdf.setFont('Helvetica-Bold', 11)
        pdf.drawString(40, y, 'Insights')
        y -= 16
        pdf.setFont('Helvetica', 10)
        for item in insights[:10]:
            pdf.drawString(48, y, f'- {item}')
            y -= 14
            if y < 80:
                pdf.showPage()
                y = height - 40
                pdf.setFont('Helvetica', 10)

        y -= 8
        pdf.setFont('Helvetica-Bold', 11)
        pdf.drawString(40, y, 'Recommendations')
        y -= 16
        pdf.setFont('Helvetica', 10)
        for item in recommendations[:10]:
            pdf.drawString(48, y, f'- {item}')
            y -= 14
            if y < 80:
                pdf.showPage()
                y = height - 40
                pdf.setFont('Helvetica', 10)

        pdf.save()
        return destination

    def _unavailable_analysis_result(self, error_text: str) -> dict[str, Any]:
        return {
            'source': 'LOCAL',
            'report': {
                'summary': 'تحلیل محلی موقتا در دسترس نیست.',
                'key_metrics': {},
                'risks': [],
                'trends': [],
                'recommendations': [],
                'reasoning_steps': [error_text or 'خطا در تحلیل محلی'],
            },
            'insights': ['تحلیل محلی ناموفق بود.'],
            'recommendations': [],
            'risk_items': [],
            'automations': [],
            'api_commentary': 'این ماژول کاملا محلی است و از سرویس خارجی استفاده نمی کند.',
        }
