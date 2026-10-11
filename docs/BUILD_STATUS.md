# Build status — 11 October 2026

The enquiry-to-quote demo, conversation/delegated-task slice and first reliability increment are implemented. Source is published at [selectqoma/feya-agent](https://github.com/selectqoma/feya-agent) as an experimental prototype. The application runs locally at http://127.0.0.1:8010; credentials and runtime data are excluded from Git. No implementation or company data was imported from the older deployment.

## What works

- Saved browser and CLI conversations, ordinary questions, standalone task delegation, supplied text sources and read-only case inspection. Tasks run independently of chat and need no workflow pack.
- Task progress, missing-input waits, steering, active cancellation, paused/failed resumption, Markdown artifacts and results returned to the originating conversation.
- Concrete acceptance criteria, persisted candidate drafts, a separate model review, and deterministic source excerpt/citation/arithmetic checks before a task becomes **Draft prepared**. The agent automatically revises substantive failures when budget allows; exact excerpt mismatches remain advisory notes. Unresolved candidates remain available with failed checks. Older results remain labelled unreviewed.
- Typed, redacted failures; budget-bounded persisted retry backoff for transient failures; visible recovery instructions and lifetime work reservations across resumption.
- Separate transactional work outbox, ordered chat events, tenant-composite references, duplicate-message IDs, persisted model-call reservations, leases and generation fences against stale results. Four requests per generation, with lifetime task limits of 12 calls, 420,000 reserved tokens and 1,080 reserved active seconds; source snapshots and bounded context. Successful calls record returned token counts; interrupted or failed calls may have unknown usage.

- Pixel Feya terminal (`feya`) with `/setup` and `/onboard`, private company pack configuration, service controls, case inspection, exact approval/rejection and reconciliation through the existing API. The browser shares the full pixel wordmark and company name.

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
| Backend suite against PostgreSQL | 182 passed |
| Conversation browser/API journey | Live payment task: acceptance criteria, passed review, lifetime budget and Markdown download from real API; desktop/mobile, no JS errors or horizontal overflow |
| Conversation browser regression fixtures | Concurrent chat, source, progress, steering, waiting/failed resumption, terminal cancellation, download; passed |
| Task restart / replay | SIGKILL worker while task waited for input, add source and resume while stopped, restart, review and redeliver; one checked artifact and prior lifetime reservations retained |
| Task concurrency and budgets | Duplicate messages, stale versions, inflight steering/cancellation, authenticated cancel before/after request arrival, queue deadline, scoped reads, retry backoff, lifetime resume limits, saved-review recovery and context covered |
| Fresh and upgrade migrations | All three migrations applied in an isolated schema; upgrade from seeded revision 0002 preserved artifacts and backfilled prior usage; passed |
| Terminal company journey | `/onboard` → `/up` → `/demo` → `/reply` → `/approve` → verified EUR 1,815 draft; passed with a synthetic company |
| Company setup validation | Cancellation/EOF preserves files; private file mode; invalid financial inputs reprompt; running services and stale settings rejected |
| Pixel Feya styling | Full wordmark in browser and terminal; conversation and case dashboard inspected at desktop, mobile at 390px and 320px without horizontal overflow; terminal ASCII/NO_COLOR at 40 and 80 columns |
| Offline evaluation calibration | 24/24 scenario reference/counterexample checks; not a model-quality score |
| Live model evaluation | 23/24 observable checks with Codex, one request per scenario; missing contract dates still triggered an unnecessary case lookup instead of asking for input |
| Agent-owned repair | Previously rejected supplier report resumed with no new instructions; agent repaired saved draft and passed review in two calls, retaining all eight lifetime reservations |
| Live persisted completion review | Payment summary → saved candidate → independent review → checked Markdown artifact; two task calls |
| Live cancellation | Cancelled a running delegated task through the API; private reasoning cancellation endpoint acknowledged; no artifact published and call reservation retained |
| SDK retry boundaries | Mock transports verified one HTTP attempt on timeout, connection failure, 429 and 503 for OpenAI, Codex and Anthropic |
| Ruff | Passed |
| mypy | Passed for 21 source files |
| TypeScript + Vite production build | Passed |
| npm dependency install audit | 0 reported vulnerabilities at install |
| Browser end-to-end journey | Enquiry → reply → approve → lost response → reconciliation → verified completion; passed |
| Browser source view / new-case form | Passed |
| Browser JavaScript errors | None in exercised journey |
| Desktop and 390px mobile | Screenshots inspected; no document overflow |
| Worker crash / durable approval / replay | SIGKILL worker, approve while stopped, restart, redeliver outbox; exactly one verified offer |
| Live Codex subscription smoke | Structured result returned without an API key |
| Live Codex conversation and task | Ordinary CLI chat and a persisted supplier-comparison report with source citations, correct EUR 1,000/1,400 calculations, delivery recommendation and unknowns; passed |
| Live Codex full preparation | 4 grounded consulting facts, 0 validation warnings, deterministic EUR 1,815.00 offer; awaiting review |
| Claude subscription smoke | Adapter invoked official CLI; account reported **not logged in**; no successful inference claimed |
| Real Gmail / Calendar / Billit staging | Not attempted |
| Full production threat model / pentest | Not completed |
| Hermes/n8n end-to-end comparative benchmark | Not performed; no competitive-superiority claim |

Conversation screenshots: `.local/conversation-live-desktop.png` and `.local/conversation-live-mobile.png`. Case screenshots are in ignored local artifacts: `.local/workspace-desktop.png`, `.local/workspace-mobile.png`, `.local/verification-needed.png`. Reproduce with `uv run python scripts/browser_check.py`. Generated screenshots reflect the offline browser test; the live subscription configuration used during development is recorded below.

## Local model verification on 11 October 2026

The original development machine used a local `.env` selecting `FEYA_RUNNER=pydantic-ai` and `FEYA_MODEL=openai-codex:gpt-5.6-luna`, using its account-owner Codex sign-in. Model calls consumed that subscription's allowance. Set `FEYA_RUNNER=fixture` and restart for offline use. The repository default remains the offline runner; `.env` and account credentials are not tracked.

Live testing exposed unnecessary repeated case lookups, null optional response fields, and review false rejections. The application rejects repeated tools and preserves candidates when review fails. Independent review accepted a valid supplier report and rejected an unsupported VAT assertion; this is evidence that the checks execute, not proof of semantic accuracy. The reviewer uses a separate call to the same configured model and can share its mistakes. Claims not extracted by the reviewer can escape arithmetic/evidence checks.

Before the automatic-revision increment, the full live evaluation used prompt/schema hash `031cf7d8aa7e9274`, model `openai-codex:gpt-5.6-luna`, and 24 reserved requests. Initial testing scored 16/24 before fixing two checker false positives and response/routing issues. The final 23/24 result remains a failure of the full live suite; the missing-dates case is an unresolved routing weakness, not waived. A targeted recheck had passed it, which shows model variability. A supplier comparison also required corrections and remained blocked by strict evidence-excerpt review checks. The subsequent automatic-revision increment makes those excerpt checks advisory and lets the agent repair substantive review failures itself. The previously blocked supplier report subsequently completed after an empty resume using the saved feedback, without additional operator instructions. That targeted check does not replace the full live benchmark. Reports stay under ignored `.local/evals/`; re-run with `--live --limit 24 --requests-per-case 1 --request-budget 24`. No competitor comparison or production-readiness inference follows from this small set.

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
| FEA-007 structured agent | PydanticAI and live Codex extraction implemented; offline runner and Claude adapter included. Bounded conversation and standalone task reasoning added. Web research, a specialist suite and a company-wide spend ledger remain open. |
| FEA-008 drafts/verification | Reply and offer drafts, source recipient check, approved pricing, exact read-back, correlation recovery implemented. |
| FEA-009 operator UI | Case list/detail, approvals/rejection, sources, audit, reconciliation and manual handling implemented. Draft editing/version history, owner assignment and advanced filters remain open. |
| FEA-010 competitive spike | Independent runnable comparison candidate delivered. Hermes CLI Kanban capabilities inspected. Fair Hermes/n8n scenario implementation and measurements remain open. |

## Next implementation order

The [product development map](research/03_PRODUCT_DEVELOPMENT_MAP.md) expands this sequence. The first conversation/task and reliability slices are complete; broader company knowledge, richer onboarding, corrections and real connectors remain pending. The 24-scenario offline harness calibrates validators and counterexamples, while explicit live runs measure limited observable model behavior. Neither substitutes for a production evaluation set or the competitor benchmark.

1. Complete a fair same-fixture Hermes/n8n comparison and record measured setup/reliability tradeoffs before claiming a platform advantage.
2. Harden deployment boundaries: OIDC and real roles, separate least-privilege DB users, agent/gateway network isolation, active member revocation, secret storage, durable failed-work recovery UI, immutable versioned migrations, full container packaging.
3. Add operator fact correction and immutable draft edit/re-approval history; add explicit connector/pack SDK contracts.
4. Add isolated staging Gmail draft/read-back first, then tentative Calendar and undispatched accounting connectors with their provider-specific identity/idempotency contracts. No live customer migration.
5. Complete retention/attachments, supported pricing-scenario expansion, benchmark coverage, dependency/license/IP/secret-history review and independent security review before a supported production release.

This is a substantial first local slice, not completion of every P0/P1 requirement. Default human identity, developer DB credentials and simulated verification make it inappropriate for public hosting or customer operations until the listed boundaries are implemented and tested.
