"""
Marker defaults for the tiered testing strategy (see CLAUDE.md §3).

Most tests in this suite exercise real file I/O and/or a real pipeline agent
call — that's the `integration` tier. Rather than hand-marking every one of
those, only the genuinely pure, no-I/O, no-agent tests are explicitly marked
`unit` (or `e2e` for the two full-pipeline acceptance tests) at their
definition; anything left unmarked here defaults to `integration`.
"""

import asyncio
from pathlib import Path

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # Must run before pytest's own -m mark-expression filtering (a separate
    # pytest_collection_modifyitems implementation) — otherwise tests default-tagged
    # here arrive too late to be considered for a `-m integration` selection.
    tiers = ("unit", "integration", "e2e")
    for item in items:
        if not any(item.get_closest_marker(tier) for tier in tiers):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def shared_mapped_gl():
    """Real ingestion + CoA-mapping of sample_gl.csv, computed once per test
    session (a real LLM call, no mocking — see the "no mock" project decision).

    test_financial_builder.py, test_nwc_analyzer.py, test_net_debt_and_dcf.py,
    and test_qoe_and_redflags.py each used to independently re-derive this exact
    same classified-GL data via their own local helper, meaning every test class
    (in test_financial_builder.py, every *test method*, since it ran via
    setup_method) paid for its own real API call against identical input. This
    fixture computes it once and everyone shares it — building PnL/BS/CF from
    already-mapped lines is pure, cheap, deterministic Python, so only the
    mapping step (the actual LLM call) needed caching.
    """
    from app.agents.coa_mapper import CoAMapperAgent
    from app.pipeline.financial_builder.orchestrator import _apply_classifications
    from app.pipeline.ingestion.loader import infer_column_map, load_file
    from app.pipeline.ingestion.normalizer import normalise

    fixture_gl = Path(__file__).parent / "fixtures" / "sample_gl.csv"
    df = load_file(fixture_gl)
    col_map = infer_column_map(df)
    raw = normalise(df, col_map, "sample_gl.csv", "shared-mapped-gl-fixture")
    unique_pairs = list({(gl.account_code, gl.account_description) for gl in raw})
    agent = CoAMapperAgent()
    cls_map = asyncio.run(agent.map_accounts(unique_pairs))
    return _apply_classifications(raw, cls_map)
