"""DCF engine — validates projection inputs and produces DCF report stub."""

import json
import logging

from app.storage import file_store

logger = logging.getLogger(__name__)


class DCFEngineError(Exception):
    pass


def run(deal_id: str) -> dict:
    processed = file_store.get_processed_dir(deal_id)
    proj_path = processed / "management_projections.json"

    if not proj_path.exists():
        report = {
            "deal_id": deal_id,
            "status": "skipped",
            "message": "Management projections not uploaded — DCF skipped. Upload projections to enable.",
            "projection_periods": 0,
        }
    else:
        with open(proj_path, encoding="utf-8") as f:
            proj = json.load(f)
        report = {
            "deal_id": deal_id,
            "status": "inputs_ready",
            "message": "Projections ingested. Full DCF valuation pending implementation.",
            "projection_periods": len(proj.get("lines", [])),
        }

    out = processed / "dcf_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("DCF engine complete for %s (status=%s)", deal_id, report["status"])
    return report
