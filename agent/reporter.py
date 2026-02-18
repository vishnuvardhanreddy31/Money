"""
Report Generator - Produces the output report.json in the required schema.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import List

logger = logging.getLogger(__name__)


def generate_report(bugs: List[dict], output_path: str) -> str:
    """Generate report.json at the specified output path.

    Args:
        bugs: List of bug dictionaries in the required schema.
        output_path: Directory where report.json should be written.

    Returns:
        Full path to the generated report file.
    """
    os.makedirs(output_path, exist_ok=True)

    report = {"bugs": bugs}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"report_{timestamp}.json"
    filepath = os.path.join(output_path, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    report_path = os.path.join(output_path, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("Report written to %s (%d bugs)", filepath, len(bugs))
    logger.info("Report also written to %s", report_path)

    _log_summary(bugs)

    return filepath


def _log_summary(bugs: List[dict]):
    """Log a summary of detected bugs."""
    if not bugs:
        logger.info("No bugs detected.")
        return

    severity_counts = {}
    category_counts = {}
    confidence_counts = {}
    for bug in bugs:
        sev = bug.get("severity", "UNKNOWN")
        cat = bug.get("category", "Unknown")
        conf = bug.get("confidence", "UNKNOWN")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        category_counts[cat] = category_counts.get(cat, 0) + 1
        confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

    logger.info("=== Bug Detection Summary ===")
    logger.info("Total bugs: %d", len(bugs))
    logger.info("By severity:")
    for sev in ["HIGH", "MEDIUM", "LOW"]:
        count = severity_counts.get(sev, 0)
        if count:
            logger.info("  %s: %d", sev, count)
    logger.info("By confidence:")
    for conf in ["HIGH", "MEDIUM", "LOW"]:
        count = confidence_counts.get(conf, 0)
        if count:
            logger.info("  %s: %d", conf, count)
    logger.info("By category:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        logger.info("  %s: %d", cat, count)
    bugs_with_fix = sum(1 for b in bugs if b.get("fixed_code", "").strip())
    bugs_with_explanation = sum(1 for b in bugs if b.get("explanation", "").strip())
    logger.info("Bugs with suggested fix: %d/%d", bugs_with_fix, len(bugs))
    logger.info("Bugs with explanation: %d/%d", bugs_with_explanation, len(bugs))
