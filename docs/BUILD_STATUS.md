# Build status — 11 October 2026

The first enquiry-to-quote demo from the supplied spec is implemented. Source is published at [selectqoma/feya-agent](https://github.com/selectqoma/feya-agent) as an experimental prototype. The application runs locally at http://127.0.0.1:8010; credentials and runtime data are excluded from Git. No implementation or company data was imported from the older deployment.

## What works

- Pixel-F terminal (`feya`) with `/setup` and `/onboard`, private company pack configuration, service controls, case inspection, exact approval/rejection and reconciliation through the existing API. The browser shares the pixel F and company name.

- Case queue/detail with missing facts, source text, draft/offer preview, approval/rejection, manual handling, cancellation, JSON export, timelines, provider verification/reconciliation, pack inspection and runner status.
- PostgreSQL migration with tenant-composite references, source-event uniqueness, atomic ingestion, case version checks, outbox, recorded runs, exact intents, approvals, execution attempts and append-only audit trigger.
- Persistent Temporal outer case workflow, signal delivery, durable human waits, duplicate-tolerant activities and outbox replay. Database/source/approval transactions are separate from provider I/O.
- Separate HTTP API, bounded reasoning process, trusted workflow worker and privileged simulated execution gateway. Separate agent/gateway service tokens; model worker has no business-API tools.
- Deterministic offline parser, PydanticAI provider adapter (including Codex subscription) and official Claude CLI adapter. Explicit provider selection, no billing fallback, bounded input/output/turns/deadline/concurrency.
- Source-grounded extraction, missing-field checks, exact source recipient, Decimal pricing, pack/policy/source version binding, expiring one-use approvals, safe rejection of forged/stale/tampered proposals.
- Fake email and accounting providers with independent persisted read-back and fault modes: timeout before/after commit, altered output, read failure.
- Service-enquiry and consulting packs exercise the same core without industry-specific branches.

## Observed verification

| Check | Observed result |
|---|---|
| Backend suite against PostgreSQL | 36 passed |
| Terminal company journey | `/onboard` → `/up` → `/demo` → `/reply` → `/approve` → verified EUR 1,815 draft; passed with a synthetic company |
| Company setup validation | Cancellation/EOF preserves files; private file mode; invalid financial inputs reprompt; running services and stale settings rejected |
| Shared pixel F and company name | Browser rendering inspected at desktop and 390px mobile; no page errors |
| Ruff | Passed |
| mypy | Passed for 13 source files |
| TypeScript + Vite production build | Passed |
| npm dependency install audit | 0 reported vulnerabilities at install |
| Browser end-to-end journey | Enquiry → reply → approve → lost response → reconciliation → verified completion; passed |
| Browser source view / new-case form | Passed |
| Browser JavaScript errors | None in exercised journey |
| Desktop and 390px mobile | Screenshots inspected; no document overflow |
| Worker crash / durable approval / replay | SIGKILL worker, approve while stopped, restart, redeliver outbox; exactly one verified offer |
| Live Codex subscription smoke | Structured result returned without an API key |
| Live Codex full preparation | 4 grounded consulting facts, 0 validation warnings, deterministic EUR 1,815.00 offer; awaiting review |
| Claude subscription smoke | Adapter invoked official CLI; account reported **not logged in**; no successful inference claimed |
| Real Gmail / Calendar / Billit staging | Not attempted |
| Full production threat model / pentest | Not completed |
| Hermes/n8n end-to-end comparative benchmark | Not performed; no competitive-superiority claim |

Screenshots are in ignored local artifacts: `.local/workspace-desktop.png`, `.local/workspace-mobile.png`, `.local/verification-needed.png`. Reproduce with `uv run python scripts/browser_check.py`. Generated screenshots reflect the offline browser test; the live subscription configuration used during development is recorded below.

## Local model verification on 11 October 2026

The original development machine used a local `.env` selecting `FEYA_RUNNER=pydantic-ai` and `FEYA_MODEL=openai-codex:gpt-5.6-luna`, using its account-owner Codex sign-in. Model calls consumed that subscription's allowance. Set `FEYA_RUNNER=fixture` and restart for offline use. The repository default remains the offline runner; `.env` and account credentials are not tracked.

The live preparation case is **Customer journey discovery workshop** (`jordan@example.test`). It is synthetic and left awaiting operator review. Existing synthetic cases also demonstrate waiting and verified-completed states.

## Spec backlog: concrete implementation status

| Ticket | Status |
|---|---|
| FEA-001 clean repo / package / locks / CI | Python/npm lockfiles and CI present. Initial GitHub CI passed lint, types, all 25 backend tests and console build. Production and licensing gates remain open. |
| FEA-002 domain models | Input/agent/artifact/pack/decision contracts and phase validator implemented; persistence uses tenant-scoped SQLAlchemy tables. Stable public entity SDK remains unfinished. |
| FEA-003 cases/events/outbox | Implemented, including concurrent deduplication and transactional event capture. |
| FEA-004 fake providers | Email/accounting implemented with fault injection. Calendar simulator not built. |
| FEA-005 durable workflow | Implemented and exercised with actual Temporal, worker kill, approval wait and redelivery. Exhaustive crash-at-every-instruction suite remains future work. |
| FEA-006 hard gateway | Policy/approval/attempt/read-back path and negative tests implemented for the two fake capabilities. Production DB principals, OIDC and egress/IAM enforcement remain open. |
| FEA-007 structured agent | PydanticAI and live Codex extraction implemented; offline runner and Claude adapter included. Generalist solo mode, a full specialist suite and per-tenant spend ledger remain open. |
| FEA-008 drafts/verification | Reply and offer drafts, source recipient check, approved pricing, exact read-back, correlation recovery implemented. |
| FEA-009 operator UI | Case list/detail, approvals/rejection, sources, audit, reconciliation and manual handling implemented. Draft editing/version history, owner assignment and advanced filters remain open. |
| FEA-010 competitive spike | Independent runnable comparison candidate delivered. Hermes CLI Kanban capabilities inspected. Fair Hermes/n8n scenario implementation and measurements remain open. |

## Next implementation order

1. Complete a fair same-fixture Hermes/n8n comparison and record measured setup/reliability tradeoffs before claiming a platform advantage.
2. Harden deployment boundaries: OIDC and real roles, separate least-privilege DB users, agent/gateway network isolation, active member revocation, secret storage, durable failed-work recovery UI, immutable versioned migrations, full container packaging.
3. Add operator fact correction and immutable draft edit/re-approval history; add explicit connector/pack SDK contracts.
4. Add isolated staging Gmail draft/read-back first, then tentative Calendar and undispatched accounting connectors with their provider-specific identity/idempotency contracts. No live customer migration.
5. Complete retention/attachments, supported pricing-scenario expansion, benchmark coverage, dependency/license/IP/secret-history review and independent security review before a supported production release.

This is a substantial first local slice, not completion of every P0/P1 requirement. Default human identity, developer DB credentials and simulated verification make it inappropriate for public hosting or customer operations until the listed boundaries are implemented and tested.
