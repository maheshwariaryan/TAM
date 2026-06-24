"""Net debt bridge — validates debt instrument inputs and produces bridge stub."""

import json
import logging

from app.storage import file_store

logger = logging.getLogger(__name__)


class NetDebtBridgeError(Exception):
    pass


def run(deal_id: str) -> dict:
    processed = file_store.get_processed_dir(deal_id)
    debt_path = processed / "debt_instruments.json"

    if not debt_path.exists():
        report = {
            "deal_id": deal_id,
            "status": "skipped",
            "message": "Debt agreements not uploaded — Net Debt bridge skipped. Upload PDF agreements to enable.",
            "instrument_count": 0,
            "total_principal_outstanding": "0",
        }
    else:
        with open(debt_path, encoding="utf-8") as f:
            debt = json.load(f)
        instruments = debt.get("instruments", [])
        total_principal = sum(
            float(i.get("principal_outstanding") or 0) for i in instruments
        )
        report = {
            "deal_id": deal_id,
            "status": "inputs_ready",
            "message": "Debt instruments ingested. Full Net Debt bridge pending implementation.",
            "instrument_count": len(instruments),
            "total_principal_outstanding": str(total_principal),
        }

    out = processed / "net_debt_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Net debt bridge complete for %s (status=%s)", deal_id, report["status"])
    return report
