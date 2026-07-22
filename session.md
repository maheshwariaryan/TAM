# YC Coding Agent Session — TAM

## 1. Project Overview

TAM is an AI-powered financial due diligence platform designed to automate portions of the work traditionally performed by Transaction Advisory Services (TAS) and Quality of Earnings (QoE) teams.

The goal is not to replace financial professionals. The goal is to eliminate repetitive manual work such as:

* General ledger normalization
* Chart of accounts mapping
* Financial statement construction
* Quality of earnings adjustment identification
* Red flag detection
* Supporting schedule generation

The system combines deterministic financial computation with LLM-powered analysis to create an auditable workflow suitable for professional financial review.

This document describes how I used AI coding agents (primarily Cursor and Claude) to architect and build the platform.

---

## 2. My Development Philosophy

I do not use AI as an autonomous software engineer.

Instead, I use AI as a force multiplier.

My workflow is:

1. Define the business problem.
2. Decompose it into subsystems.
3. Define invariants and constraints.
4. Write implementation plans.
5. Use AI agents to accelerate implementation.
6. Validate outputs through tests and manual review.

The architecture and business logic are human-defined.

AI accelerates implementation, debugging, testing, and exploration.

---

## 3. The Core Problem

When performing financial due diligence, analysts spend significant time:

* Cleaning messy accounting exports
* Mapping accounts into standardized categories
* Constructing financial statements
* Identifying non-recurring adjustments
* Investigating related-party transactions
* Creating supporting schedules

Most of this work follows repeatable patterns.

The challenge is building a system that can automate the process while remaining auditable.

A financial reviewer must always be able to answer:

> Where did this number come from?

That requirement drove every technical decision.

---

## 4. Architecture Decisions

### Decision #1: Financial calculations must never be performed by LLMs

Financial outputs must be deterministic.

LLMs are non-deterministic by nature.

Therefore:

* Python performs all calculations.
* Pandas performs transformations.
* Decimal preserves precision.
* LLMs only classify, review, and enrich.

**Rule:**

> Agents never compute money.

---

### Decision #2: Modular Monolith First

Many engineers immediately reach for microservices.

I intentionally did not.

Current architecture:

```text
Ingestion
    ↓
Financial Builder
    ↓
QoE Engine
    ↓
Red Flag Engine
    ↓
Reporting
```

Benefits:

* Faster iteration
* Easier debugging
* Lower operational overhead
* Clear future service boundaries

Future migration path:

```text
BackgroundTasks
    → Celery + Redis

JSON Storage
    → PostgreSQL

Local Files
    → S3
```

---

### Decision #3: Structured Agent Interfaces

A common source of LLM failures is malformed JSON.

To eliminate this:

* All agents use Pydantic schemas.
* Inputs are validated.
* Outputs are validated.
* Anthropic tool-use mode is enforced.

This significantly improved reliability.

---

### Decision #4: Mock-First Development

The platform defaults to:

```bash
USE_MOCK_LLM=true
```

This allows:

* Local development
* CI execution
* End-to-end testing

without requiring API keys or incurring model costs.

---

## 5. Alternative Approaches Considered

### End-to-End LLM Financial Analysis

Rejected.

Reasons:

* Non-deterministic
* Difficult to audit
* Impossible to verify consistently

---

### Rule-Only Classification

Rejected.

Reasons:

Real client charts of accounts vary dramatically.

Pure rule systems break quickly.

A hybrid approach proved superior.

---

### Database-First Design

Deferred.

For early-stage iteration:

* JSON files
* Storage abstractions
* Repository patterns

were significantly faster.

The migration path to PostgreSQL remains straightforward.

---

### Microservices from Day One

Rejected.

The complexity cost outweighed the benefits.

A modular monolith provided better speed while preserving future flexibility.

---

### RAG for Everything

Rejected.

Many AI systems immediately introduce vector databases.

For TAM:

* Financial computations are structured.
* Rules are deterministic.
* Retrieval adds complexity.

Future narrative analysis may use RAG, but financial processing does not require it.

---

## 6. How I Used AI During Development

My typical workflow:

### Step 1

Create implementation plans.

Examples:

* STEPS.md
* Architecture specifications
* API contracts

---

### Step 2

Use Cursor to implement individual modules.

Examples:

* Ingestion
* QoE Engine
* Reporting
* Red Flag Detection

---

### Step 3

Run tests.

Examples:

```bash
pytest
npm run build
```

---

### Step 4

Feed failures back into the agent.

Example prompts:

> Why is this trial balance failing?

> Explain the root cause.

> Suggest the smallest possible fix.

---

### Step 5

Review manually.

I never merge code solely because the agent generated it.

The agent proposes.

I decide.

---

## 7. Major Engineering Challenges

### Challenge: Messy Accounting Exports

Client files contain inconsistent column names.

Examples:

* Account
* Acct Code
* GL Account
* Net Amount

Solution:

Built column inference and validation logic with explicit failure modes.

---

### Challenge: Debit/Credit Normalization

Accounting systems export transactions differently.

Solution:

Normalize all records into signed Decimal values while preserving audit traces.

---

### Challenge: Cost-Efficient CoA Mapping

Large account sets can create significant LLM cost.

Solution:

Batch processing and deterministic mock classification during development.

---

### Challenge: Exact QoE Waterfalls

Financial adjustments must reconcile perfectly.

Solution:

All waterfall calculations are performed through deterministic Python logic with test assertions validating every output.

---

### Challenge: Multi-Document Data Rooms

Deals often contain:

* GL exports
* AR aging reports
* Debt agreements
* Forecasts

Solution:

Built a document registry that classifies inputs and routes them through the appropriate pipeline.

---

## 8. Testing and Reliability

Current repository includes:

* 71+ automated tests
* End-to-end API testing
* Financial validation tests
* Logging and audit trails
* CI pipelines
* Frontend build verification

Examples of enforced guarantees:

* Trial balances must reconcile
* QoE waterfalls must reconcile
* Financial calculations preserve cent-level precision
* Invalid uploads fail early

---

## 9. LLM Orchestration

Current agents include:

### CoAMapperAgent

Maps raw account descriptions to standardized categories.

---

### QoEReviewerAgent

Reviews potential adjustments and provides reasoning.

---

### RedFlagAnalystAgent

Generates diligence questions and identifies risks.

---

### ContractParserAgent

Extracts structured data from debt agreements and supporting documents.

---

All agents:

* Use structured schemas
* Support mock and production modes
* Log token usage
* Implement retry logic
* Validate outputs

---

## 10. What Has Been Built

Current platform includes:

* Financial data ingestion
* Financial statement construction
* QoE adjustment workflows
* Red flag detection
* Excel databook exports
* Audit logging
* Next.js dashboard
* Backend APIs
* CI/CD pipelines
* Automated testing

---

## 11. What I Learned

The biggest lesson from building TAM was that AI is most effective when paired with strong system design.

The hard part was never generating code.

The hard part was defining the architecture, constraints, validation rules, and audit requirements that make the system trustworthy.

AI dramatically accelerated implementation, testing, debugging, and iteration, but the core product decisions remained human-driven.

That combination allowed me to move significantly faster while maintaining confidence in the correctness of the system.
