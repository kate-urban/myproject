#!/usr/bin/env python3
"""Пакетная валидация эталонных пар ФОС (шаг 3)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.fos_extractor import extract_fos
from app.services.rpd_extractor import extract_rpd
from app.services.validation import validate_fos_bundle, validate_fos_only_bundle
from tests.golden_fos_data import GOLDEN_FOS_PAIRS
from tests.golden_fos_helpers import failed_critical_rules, plan_and_discipline_from_pair


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate golden FOS pairs")
    parser.add_argument("--pair", action="append", help="Pair id (default: all)")
    args = parser.parse_args()

    pairs = GOLDEN_FOS_PAIRS
    if args.pair:
        selected = set(args.pair)
        pairs = [pair for pair in pairs if pair.id in selected]

    failed = 0
    for pair in pairs:
        if not pair.files_present:
            print(f"[SKIP] {pair.id}: sample files missing")
            continue

        plan, discipline = plan_and_discipline_from_pair(pair)
        fos = extract_fos(pair.fos_path.read_bytes(), pair.fos_path.name)
        if pair.fos_only:
            report = validate_fos_only_bundle(plan, discipline, fos)
        else:
            rpd = extract_rpd(pair.rpd_path.read_bytes(), pair.rpd_path.name)
            report = validate_fos_bundle(plan, discipline, rpd, fos)

        critical_failed = failed_critical_rules(report)
        if pair.validation_passes:
            status = "PASS" if report.passed else "FAIL"
        else:
            status = "PASS" if set(critical_failed) == set(pair.expected_fail_rules) else "FAIL"

        mode = "fos_only" if pair.fos_only else "triple"
        print(f"[{status}] {pair.id} ({pair.discipline_code}, {mode})")
        if status == "FAIL":
            failed += 1
            for item in report.results:
                if item.skipped or item.passed or item.severity != "critical":
                    continue
                print(f"  - {item.rule_id}: {item.message}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
