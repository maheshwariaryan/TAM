# CLAUDE.md — TAM (M&A Due-Diligence Tool)

This file governs how Claude Code should work in this repository. Follow it
exactly unless the user explicitly overrides it in a session.

## 1. Branching Strategy

Every unit of work gets its own branch. Never commit directly to `main`.

| Prefix   | Used for                                                        | Branched from |
|----------|------------------------------------------------------------------|---------------|
| `feat/`  | New feature implementation                                       | `main`        |
| `test/`  | Writing/running tests for a feature (see below)                  | the `feat/` branch it tests |
| `fix/`   | Bug fixes                                                         | `main`        |
| `exp/`   | Experiments, spikes, diagnostics, one-off checks — not for prod   | `main`        |
| `chore/` | Maintenance: deps, config, refactors with no behavior change      | `main`        |

Naming: `feat/document-encryption`, `test/document-encryption`, `fix/argon2-verify-crash`,
`exp/check-pdfplumber-memory-usage`, `chore/bump-cryptography-version`.

### Feature workflow (the important one)
For every new feature:
1. Branch `feat/<feature-name>` from `main`.
2. Implement the feature on that branch, committing atomically as you go (see §2).
3. Once the implementation is in a working state, branch `test/<feature-name>` off
   the `feat/` branch.
4. Write and run tests on the `test/` branch. If tests reveal bugs, fix them back
   on the `feat/` branch (don't patch bugs inside the test branch), then rebase
   `test/` on top.
5. Once tests pass cleanly, merge `test/<feature-name>` back into `feat/<feature-name>`.
6. Open a **pull request** from `feat/<feature-name>` into `main` — do not merge
   directly. See §3a for what happens next.
7. Only start the next feature/slice once that PR has been merged (i.e. CI is
   green and the merge has actually happened) — not as soon as local testing looks
   done.

### Bugfix / check workflow
- A bug found during manual use or review → `fix/<short-bug-description>`.
- A diagnostic, spike, or "let's just check something" task → `exp/<short-description>`.
  `exp/` branches are disposable — they don't need to be merged, and Claude Code
  should say so explicitly rather than assuming an `exp/` branch is headed for `main`.

## 2. Commit Discipline

- Commit early and often — after every coherent, working unit of change, not
  just at the end of a session. A good rule of thumb: if you've touched more
  than ~3 files or ~1 logical concern without committing, stop and commit.
- Every commit must leave the repo in a working state (code runs, imports
  resolve) — no "WIP, broken" commits.
- Use Conventional Commits format:
  - `feat: add AES-256-GCM envelope encryption for uploaded documents`
  - `fix: correct nonce reuse bug in file_crypto decrypt path`
  - `test: add tamper-detection test for GCM auth tag`
  - `chore: pin cryptography to 42.x`
  - `docs: note KMS migration seam in file_crypto.py`
- Keep commits atomic: one logical change per commit. Don't bundle an
  unrelated refactor into a feature commit.
- Before merging any `feat/` or `fix/` branch into `main`, squash-check the
  history for stray WIP commits and clean it up if needed.

## 3a. CI Gate — No Self-Reported "Done"

A PR into `main` is not considered mergeable based on a self-reported summary
(e.g. "lint/build clean, verified manually"). It is only mergeable once GitHub
Actions CI has independently run and passed on that PR. Concretely:

- On every push and every PR targeting `main`, CI runs:
  - Backend: Ruff lint + `pytest -m "unit or integration"` (mocked LLM via
    `USE_MOCK_LLM=1`) — this must stay fast; never run the full `e2e` pipeline
    here.
  - Frontend: `next lint` and `next build`.
- Do not merge a `feat/` branch into `main` until that PR shows a green CI
  check. If CI is red, fix the branch and push again — don't merge around it.
- When a slice/feature is implementation-complete, the correct status update is
  "PR open, waiting on CI" — not "done and merged" — until the merge has
  actually happened post-green-CI.
- The full `e2e` pipeline (real Claude API calls, ~40 min) runs separately —
  nightly on `main` or via manual trigger — not as a merge gate.

## 3. Testing Strategy — Staged, Not Monolithic

The full pipeline (ingest → parse → financial calc → LLM agent → report) takes
~40 minutes end-to-end. Do not run the full pipeline as the default test loop.
Instead:

### Tiered test markers
```python
@pytest.mark.unit         # ms-scale, no I/O, no LLM calls — run constantly
@pytest.mark.integration  # seconds-scale, mocked LLM (USE_MOCK_LLM=1), real file I/O
@pytest.mark.e2e          # the full real pipeline, real Claude API calls
```
- Default local/dev loop: `pytest -m unit` then `pytest -m "unit or integration"`.
- `e2e` only runs before a merge to `main`, or on a nightly CI schedule —
  never as part of routine iteration.

### Stage checkpointing
Each pipeline stage (ingest, parse, financial calc, agent analysis, report
gen) must write its output to `data/processed/{deal_id}/{stage_name}.json`
before the next stage begins. The pipeline runner should:
1. Check whether a valid checkpoint already exists for a stage.
2. Skip recomputation if it does (unless `--force` is passed).
3. On failure, resume from the last good checkpoint, not from the start.

### Per-feature test branches gate progress
When building a new pipeline stage or feature, do not consider it "done" and
move to the next dependent step until:
- Its `test/` branch (see §1) passes with zero known failures.
- Its output schema is validated (Pydantic model) so downstream stages can
  assume the shape is correct rather than re-validating it themselves.

This means: build stage N fully, test it in isolation with mocked
dependencies, confirm it's solid, merge, *then* start stage N+1. Don't build
multiple stages in parallel before any of them are individually verified.

## 4. Security-Sensitive Code

This project handles sensitive financial/M&A documents. For anything touching
`security/passwords.py`, `security/file_crypto.py`, auth, or file I/O in
`data/deals`, `uploads`, `processed`:
- Never introduce custom crypto primitives — use vetted libraries
  (`argon2-cffi`, `cryptography`) only.
- Never log secrets, keys, hashed passwords, or decrypted document contents.
- Flag any change to key-loading or the encryption seam explicitly in the
  commit message and PR description — these changes deserve extra scrutiny.

## 5. General
- Don't touch business logic (deal parsing, financial calculations) when the
  task is scoped to I/O, security, or infra — keep changes surgical.
- Before starting multi-file work, state a short plan of which files will be
  touched.
- Run Ruff and the relevant test tier before considering any task complete.
