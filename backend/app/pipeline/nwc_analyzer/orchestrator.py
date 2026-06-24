"""NWC analyzer — validates aging inputs and produces NWC report stub."""

import json
import logging

from app.storage import file_store

logger = logging.getLogger(__name__)


class NWCAnalyzerError(Exception):
    pass


def run(deal_id: str) -> dict:
    processed = file_store.get_processed_dir(deal_id)
    ar_path = processed / "ar_aging.json"
    ap_path = processed / "ap_aging.json"

    has_ar = ar_path.exists()
    has_ap = ap_path.exists()

    if not has_ar and not has_ap:
        report = {
            "deal_id": deal_id,
            "status": "skipped",
            "message": "AR/AP aging not uploaded — NWC analysis skipped. Upload aging summaries to enable.",
            "has_ar_aging": False,
            "has_ap_aging": False,
        }
    else:
        report = {
            "deal_id": deal_id,
            "status": "inputs_ready",
            "message": "Aging data ingested. Full NWC peg calculation pending Step 6 implementation.",
            "has_ar_aging": has_ar,
            "has_ap_aging": has_ap,
        }

    out = processed / "nwc_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("NWC analyzer complete for %s (status=%s)", deal_id, report["status"])
    return report
