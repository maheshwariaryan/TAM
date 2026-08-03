"""
Parser for Group C files — lease schedules, fixed asset registers, equity/cap-table
rollforwards, payroll/headcount, and bank statements. No pipeline stage models these
domains yet (each would be its own feature), so they're classified correctly, parsed
into plain row records, and persisted/exposed for viewing rather than silently dropped.
"""

import logging

from app.pipeline.ingestion.loader import load_bytes

logger = logging.getLogger(__name__)


def parse_supporting_schedule_bytes(raw_bytes: bytes, filename: str) -> list[dict]:
    """Parse a Group C file into a list of row dicts, preserving original column names
    and string values — this is a raw, viewable table, not a normalised report."""
    df = load_bytes(raw_bytes, filename)
    records = df.to_dict("records")
    logger.info("Parsed supporting schedule '%s': %d row(s)", filename, len(records))
    return records
