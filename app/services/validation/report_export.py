"""Формирование сводных отчётов валидации УП ↔ РПД ↔ ФОС."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any

from app.models import StudyPlan
from app.services.validation.fos_engine import FosPlanValidationReport, FosValidationReport
from app.services.validation.engine import PlanValidationReport, ValidationReport
from app.services.validation.rules import RuleResult


def _rule_row(item: RuleResult) -> dict[str, Any]:
    return {
        "rule_id": item.rule_id,
        "name": item.name,
        "passed": item.passed,
        "skipped": item.skipped,
        "severity": item.severity,
        "message": item.message,
        "expected": item.expected,
        "actual": item.actual,
    }


def _discipline_rpd_item(report: ValidationReport) -> dict[str, Any]:
    return {
        "discipline_id": str(report.discipline_id) if report.discipline_id else None,
        "discipline_code": report.discipline_code,
        "document_id": report.document_id,
        "passed": report.passed,
        "skipped": report.skipped,
        "reason": report.reason,
        "results": [_rule_row(item) for item in report.results],
    }


def _discipline_fos_item(report: FosValidationReport) -> dict[str, Any]:
    return {
        "discipline_id": str(report.discipline_id) if report.discipline_id else None,
        "discipline_code": report.discipline_code,
        "rpd_document_id": report.rpd_document_id,
        "fos_document_id": report.fos_document_id,
        "passed": report.passed,
        "skipped": report.skipped,
        "reason": report.reason,
        "results": [_rule_row(item) for item in report.results],
    }


def build_validation_report_payload(
    plan: StudyPlan,
    *,
    rpd_report: PlanValidationReport,
    fos_report: FosPlanValidationReport,
) -> dict[str, Any]:
    profile = plan.profile
    direction = profile.direction
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study_plan": {
            "id": str(plan.id),
            "source_file": plan.source_file,
            "source_format": plan.source_format,
            "direction_code": direction.code,
            "direction_name": direction.name,
            "profile_name": profile.name,
            "form": plan.form,
            "year": plan.year,
        },
        "rpd_validation": {
            "total_disciplines": rpd_report.total_disciplines,
            "checked": rpd_report.checked,
            "passed": rpd_report.passed,
            "failed": rpd_report.failed,
            "missing_rpd": rpd_report.missing_rpd,
            "passed_all": rpd_report.passed_all,
            "items": [_discipline_rpd_item(item) for item in rpd_report.items],
        },
        "fos_validation": {
            "total_disciplines": fos_report.total_disciplines,
            "checked": fos_report.checked,
            "passed": fos_report.passed,
            "failed": fos_report.failed,
            "missing_fos": fos_report.missing_fos,
            "fos_only": fos_report.fos_only,
            "passed_all": fos_report.passed_all,
            "items": [_discipline_fos_item(item) for item in fos_report.items],
        },
    }


def render_validation_report_html(payload: dict[str, Any]) -> str:
    plan = payload["study_plan"]
    rpd = payload["rpd_validation"]
    fos = payload["fos_validation"]
    title = (
        f"Отчёт сверки — {html.escape(plan['direction_code'])} "
        f"{html.escape(plan['profile_name'] or '')}"
    )

    def summary_block(label: str, data: dict[str, Any], extra: str = "") -> str:
        status = "OK" if data["passed_all"] else "Есть замечания"
        badge = "ok" if data["passed_all"] else "fail"
        return f"""
        <section class="summary-card">
          <h2>{html.escape(label)}</h2>
          <p class="badge {badge}">{status}</p>
          <ul>
            <li>Проверено: {data['checked']} / {data['total_disciplines']}</li>
            <li>Успешно: {data['passed']}</li>
            <li>Ошибки: {data['failed']}</li>
            {extra}
          </ul>
        </section>
        """

    def discipline_table(items: list[dict[str, Any]], kind: str) -> str:
        rows: list[str] = []
        for item in items:
            if item.get("skipped") and not item.get("results"):
                continue
            failed_rules = [
                r["rule_id"]
                for r in item.get("results", [])
                if not r.get("skipped") and r.get("severity") == "critical" and not r.get("passed")
            ]
            status_class = "ok" if item.get("passed") else "fail"
            status_text = "OK" if item.get("passed") else ", ".join(failed_rules) or "FAIL"
            rows.append(
                "<tr>"
                f"<td>{html.escape(item.get('discipline_code') or '')}</td>"
                f'<td class="{status_class}">{html.escape(status_text)}</td>'
                f"<td>{html.escape(item.get('reason') or '')}</td>"
                "</tr>"
            )
        if not rows:
            rows.append(f'<tr><td colspan="3">Нет данных ({kind})</td></tr>')
        return (
            "<table>"
            "<thead><tr><th>Дисциплина</th><th>Результат</th><th>Примечание</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    rpd_extra = f"<li>Без РПД: {rpd['missing_rpd']}</li>"
    fos_extra = (
        f"<li>Без ФОС: {fos['missing_fos']}</li>"
        f"<li>Только ФОС (без РПД): {fos['fos_only']}</li>"
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <style>
    body {{ font-family: Segoe UI, sans-serif; margin: 24px; color: #1a1a1a; }}
    h1 {{ margin-bottom: 4px; }}
    .meta {{ color: #666; margin-bottom: 24px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
    .summary-card {{ border: 1px solid #e1e1e1; border-radius: 8px; padding: 16px; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-weight: 600; }}
    .badge.ok {{ background: #dff6dd; color: #107c10; }}
    .badge.fail {{ background: #fde7e9; color: #d13438; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border: 1px solid #e1e1e1; padding: 8px; text-align: left; }}
    th {{ background: #fafafa; }}
    td.ok {{ color: #107c10; font-weight: 600; }}
    td.fail {{ color: #d13438; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">
    Файл: {html.escape(plan['source_file'])} ·
    сформирован: {html.escape(payload['generated_at'])}
  </p>
  <div class="grid">
    {summary_block('РПД ↔ УП', rpd, rpd_extra)}
    {summary_block('ФОС ↔ УП/РПД', fos, fos_extra)}
  </div>
  <h2>Детализация РПД</h2>
  {discipline_table(rpd['items'], 'rpd')}
  <h2>Детализация ФОС</h2>
  {discipline_table(fos['items'], 'fos')}
</body>
</html>"""


def payload_to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
