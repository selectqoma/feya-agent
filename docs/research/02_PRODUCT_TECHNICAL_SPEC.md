# FEYA 2.0 — Product Requirements & Technical Architecture Specification

**Status:** Proposed build specification, v0.1 design baseline. **Not an account of currently shipped code.**  
**Date:** 2026-10-11  
**Product:** Feya, an open-source business-case execution platform with bounded AI agents  
**Companion:** `01_COMPETITIVE_LANDSCAPE.md`  
**Decision:** Build a framework-independent business kernel using Python, Temporal, PydanticAI, PostgreSQL and a narrow action gateway; do not fork Hermes.

---

## 0. How to read this specification

- **MUST** = release-blocking requirement; **SHOULD** = intended unless accepted ADR explains deviation; **MAY** = optional enhancement.
- **P0** = minimal safe vertical slice; **P1** = initial public open-source release; **P2** = after demonstrated demand.
- **Proposed** means not yet implemented. No reliability/security/competitor superiority claim is considered verified until a test demonstrates it.
- Developer-targeted examples are illustrative contracts; API names, SQL and YAML require tests and migration review before freezing stable interfaces.

## 1. Product thesis

### 1.1 Mission

Feya helps small and midsize service businesses convert incoming work into reliable, explainable outcomes across existing software. Rather than a general chat assistant that sometimes performs actions, Feya owns a persistent **business case**: who asked for what, what we know, which facts are missing, what work is proposed, what is permitted, and what actually happened at each connected provider.

**One-line pitch:** *An AI-powered operations teammate, with business rules you can trust and work you can verify.*

### 1.2 Core problem

Businesses receive unstructured requests through inboxes and channels, then manually coordinate between CRM, calendar, quoting, billing and documents. Generic agents can reason but not necessarily guarantee business action correctness. Visual automation platforms can run integrations but require significant setup and domain glue. Feya must package business workflows as **safe, reusable, observable operating units**.

### 1.3 Product principles

1. **Cases, not chats, are the primary abstraction.** Chat is a context tool inside a case, not the system of record.
2. **Authority is not reasoning.** An LLM may propose actions; trusted application code alone authorizes external effects.
3. **Evidence before commitment.** Important facts are linked to source records with identities, retrieval timestamps and integrity metadata.
4. **Verify reality after execution.** A provider HTTP success is not proof of correct business outcome; compare live persisted objects, or mark reconciliation required.
5. **Least autonomy by default.** Reads and drafts can be autonomous under policy; customer-facing dispatch, money-moving and irreversible actions default to human-controlled.
6. **One engine, multiple workflows.** Same core supports a fixed specialist pipeline and a bounded generalist agent path.
7. **Company specificity is configuration.** Business packs define data requirements and policies; no industry names in core models.
8. **Replaceable components.** No proprietary dependency on one model, agent runtime, scheduling service or accounting vendor.
9. **Usable without AI.** Operators can view, correct, approve, complete or export cases when AI providers fail.
10. **Deliver a small working workflow before a platform.** Do not implement everything merely because it looks good in a design document.

### 1.4 Who the product is for

- **Business owner/admin:** sets policy and connections, understands automation boundaries and liability.
- **Operator:** reviews customer cases, drafts, exceptions, provider status and approvals.
- **Approver:** authorizes specific sensitive actions; cannot grant abstract unlimited autonomy with a casual chat message.
- **Implementer/integrator:** installs Feya, connects a provider, creates a business pack, builds typed adapters, writes tests.
- **Maintainer:** develops core, validates security, reproduces integration errors, reviews releases.

### 1.5 Scope and non-goals

**P1 in scope:** service-enquiry intake, case inbox, evidence, missing-information tracking, workflow and solo-agent routing, drafting, controlled Billit-like proposals and tentative calendar events, approvals, independent read-back verification, audit, one generic business pack and one second-vertical portability test, standalone self-host deployment, developer SDK.

**Out of scope until P2:** replacing full CRMs/accounting systems; open-ended personal assistant; arbitrary browser/computer control; huge integration marketplace; drag-and-drop workflow studio; no-code programming language; autonomous payments or banking; unsupervised deletion; customer mobile app; complex multi-tenant hosted SaaS; vector database by default; agent-generated executable plugins installed without review.

### 1.6 Release success signals (targets, not claims)

- A new technical user installs from documented source and runs an end-to-end synthetic safe case without modifying core code.
- A second company with different workflow/rules runs using another pack without domain-specific conditionals in core.
- Every consequential provider operation can be traced from case → evidence → policy decision → approval (if required) → write → verified outcome.
- The test suite contains **zero unauthorized external actions** and **zero duplicate high-impact actions** under injected faults; uncertain outcomes are never reported as successful.
- At least one practical benchmark shows measurable advantage against comparably configured Hermes Kanban or n8n in operator effort and/or correct completion, while matching safety.

## 2. Glossary and domain model

| Term | Precise meaning |
|---|---|
| **Tenant** | One company/organization owning data, policies, connection scopes and people. |
| **Case** | A durable business work item (enquiry, proposal, ticket, request) with identity and lifecycle, independent of one chat thread. |
| **Source event** | Immutable record of an external trigger, e.g. Gmail message change, web form, staff action. |
| **Evidence** | Source observation with provider object ID, version/fingerprint, retrieval time, tenant, and content reference; not an agent's assertion. |
| **Claim** | A structured assertion made by the agent or rules, linked to evidence and marked unverified if no source supports it. |
| **Business pack** | Installable set of case schemas, workflow definitions, policies, templates, agent roles and eval fixtures. |
| **Workflow** | Durable process controlling work, waits and valid transitions for a case. |
| **Agent run** | Bounded reasoning execution using a model, tools and permitted inputs; can be a generalist or specialist. |
| **Artifact** | Generated draft (email, quote JSON, report, calendar proposal); draft creation is distinct from sending or committing. |
| **Action intent** | Typed proposal for one external mutation, including exact target, payload, evidence and idempotency identity. |
| **Policy decision** | Trusted evaluation granting, denying or conditioning one exact action, not an LLM-generated approval flag. |
| **Approval** | Explicit decision by an authorized human concerning a specific bound action hash. |
| **Execution attempt** | One outbound provider operation carried out by controlled gateway credentials. |
| **Verification** | Read-back comparison of actual provider state with expected state. |
| **Reconciliation** | Recovery when a provider effect may have happened but a reliable confirmation was not received. |
| **Audit event** | Append-only record of a consequential state change, decision, attempt, or human action. |

A **case** is not synonymous with a Gmail thread: one case can have several messages or documents, and one correspondence could contain unrelated requests. Correlation requires stable provider IDs plus conservative business matching. Auto-merging on name alone is forbidden.

### 2.1 Stable case phases

The kernel recognizes coarse operational phases:

`new`, `triaged`, `waiting_for_information`, `ready`, `drafting`, `drafted`, `awaiting_review`, `ready_to_execute`, `executing`, `verify_pending`, `completed`, `blocked`, `cancelled`, `reconciliation_required`.

Packs may define additional *domain stages* (e.g. `offer_accepted`, `inspection_booked`). They MUST map to kernel phases; they cannot bypass hard guards. State changes are validated by a pure transition function and recorded transactionally with a versioned case event. Terminal does not imply that the provider has confirmed a business effect.

### 2.2 Source of truth rules

- **Provider** (Gmail, Billit, Calendar, etc.): actual external facts and mutations.
- **PostgreSQL:** authoritative Feya business identities, case state, policy snapshots, approvals, action intents and audit records.
- **Temporal:** workflow execution history, timers, pending signals, retry scheduling; not the CRM database.
- **Object storage:** file bytes, source snapshots, large artifacts. PostgreSQL stores references, hashes and access metadata.
- **LLM messages:** disposable reasoning context, *never* authorization evidence or independent proof of business truth.

## 3. Core user journeys and acceptance

### J1. Inbound service enquiry (P0)

1. A message arrives through an authenticated provider connection.
2. Ingestion persists a source event with dedup key; it correlates or opens a case.
3. A triage agent extracts intent and required fields, each factual claim linked to provider evidence.
4. A deterministic requirements validator reports missing data.
5. Feya prepares a draft asking for missing facts; policy permits draft creation only.
6. Operator sees the case, missing facts, draft, sources, risk, and can edit/cancel/mark handled.
7. An external reply resumes the original case, not a parallel duplicate.

**Acceptance:** duplicate webhook creates no duplicate case; an unsupported recipient cannot become a draft recipient; the case clearly shows it is waiting for information; operator can complete manually when the model is unavailable.

### J2. Quote/proposal with accounting system (P1)

1. Case has sufficient grounded inputs.
2. Agent recommends service options; trusted deterministic rate service computes financial numbers.
3. Quote artifact is validated against business pack schema and pricing version.
4. Action intent `accounting.offer.create_draft` is created with exact customer/provider target, canonical payload hash and evidence IDs.
5. Policy evaluates allowed operation and either denies, permits, or requires human approval.
6. Execution gateway uses scoped credentials to create draft only.
7. Verifier reads back provider object and compares customer, amount, tax, currency and status; result attached to case.
8. A lost write response leads to reconciliation rather than blind retry.

**Acceptance:** wrong rate, stale quote, missing source, cross-tenant entity or changed approved payload yields deny; no “complete” before provider read-back; test fault injections cause no duplicate offers.

### J3. Human review and later scheduling (P1)

1. Operator opens an approval item with exact proposed side effects, recipients, prices, source links and before/after preview.
2. Approval has an expiry, authorized approver identity and immutable action hash.
3. Human can approve, reject or request edits; editing creates a new action hash and voids old approval.
4. External confirmation triggers a scheduling workflow; availability is checked live.
5. Confirmed writes use distinct permissions from tentative events. Event read-back verifies date, title, scope and optional attendees.

**Acceptance:** replaying the same approval cannot authorize two commits; an actor lacking permission cannot approve; the same approval cannot authorize a modified action; changing provider status between approval and commit forces re-evaluation.

## 4. Functional requirements

Priority classification below defines the minimal safe feature set. Each condition has an observable acceptance test in section 17.

### 4.1 Tenant and onboarding

- **FR-001 [P0]** A tenant has a unique ID, timezone, language settings, role assignments, policies and versioned pack installation.
- **FR-002 [P0]** The deployment MUST default to a single isolated tenant. Every application-facing object, event and storage path is tenant scoped.
- **FR-003 [P0]** An owner connects a test provider through a documented configuration wizard or CLI. Real OAuth connectors are opt-in; unsupported credentials never fall back to another tenant.
- **FR-004 [P1]** Admins can configure language, service rules, pricing sources, required intake fields, risk tiers, business calendars, notification channel and connection status without editing agent prompts.
- **FR-005 [P1]** Changes to production policies/packs require a validated version bump, dry-run check and operator-controlled activation; running cases retain the policy version applied at the decision boundary.

### 4.2 Ingestion and case management

- **FR-010 [P0]** Webhooks are authenticated and deduplicated using provider event identity; if no stable ID exists use an explicit bounded fallback fingerprint and document limitations.
- **FR-011 [P0]** Persist received events before acknowledging delivery. Event delivery to workflow uses a transactional outbox to bridge PostgreSQL and Temporal.
- **FR-012 [P0]** Correlate by verified provider IDs/thread IDs; uncertain links require operator review, never fuzzy silent merge.
- **FR-013 [P0]** Case has timeline, source records, domain stage, kernel phase, owner, priority, blockers, next action and linked artifacts.
- **FR-014 [P1]** Every case supports internal notes, ownership, manual edits, reassignment, pause/resume/cancel, and export.
- **FR-015 [P1]** New evidence invalidates decisions whose source fingerprint changed; stale actions cannot execute unchanged.

### 4.3 Evidence and extraction

- **FR-020 [P0]** Source evidence contains tenant, provider, provider object/version, retrieval time, payload hash, source location, classification, retention policy.
- **FR-021 [P0]** Agent-extracted claims indicate source evidence IDs; no evidence => `unverified`/`unknown`, never implicit factual certainty.
- **FR-022 [P1]** Multi-part attachments support bounded size, allowlisted file types, malware scanning and safe extraction where necessary.
- **FR-023 [P1]** Evidence refresh invalidates approvals and pending actions when materially dependent facts change.
- **FR-024 [P1]** Each pack defines explicit required fields and validators; LLM interpretation cannot replace deterministic required-field checks.

### 4.4 Agent modes

- **FR-030 [P0]** `AgentRunner` supports typed input, tools, model, context/evidence, timeout, token/cost budgets, max iterations and typed result.
- **FR-031 [P0]** `solo` mode runs one bounded generalist for low-risk tasks using read tools and action *proposals* only.
- **FR-032 [P1]** `workflow` mode runs named specialists for high-risk or complex tasks, with typed handoffs and required report validation.
- **FR-033 [P1]** Agent tool manifest is an explicit allowlist per role/policy; plugin content is treated as untrusted instructions/data.
- **FR-034 [P1]** Agents run with no direct credentials or write network path to protected providers. An LLM cannot elevate its own privileges by choosing a different tool.
- **FR-035 [P1]** Trace every agent run (model, provider, prompt version, source evidence IDs, tool names, usage, result/validation errors) with sensitive content redacted by policy.
- **FR-036 [P1]** Automatic routing selects solo/workflow based on a versioned risk decision; admins may force workflow mode. High-risk tasks never silently fall back to solo because a specialist failed.

### 4.5 Artifact, policy and approval

- **FR-040 [P0]** Draft artifacts are typed, versioned and attributable to the case and evidence versions.
- **FR-041 [P0]** Every proposed external write becomes an `ActionIntent` with canonical payload hash, authorization context and idempotency key.
- **FR-042 [P0]** Policy service returns `DENY`, `ALLOW` or `REQUIRE_APPROVAL` for the exact action; default is `DENY`.
- **FR-043 [P0]** Execution gateway MUST re-evaluate policy at commit time and reject payload changes, stale evidence, invalid actor, cross-tenant target or missing approval.
- **FR-044 [P1]** Approval is bound to `(tenant, actor, exact intent ID, payload hash, operation, target, policy version, expiry)`; any revision requires new approval.
- **FR-045 [P1]** Approval queue shows the exact side effects, sources, financial totals, unresolved risk, and whether the action is draft-only or customer-visible.
- **FR-046 [P1]** Human decisions are externally authenticated, auditable and non-forgeable by agents; no approve-via-model-text.

### 4.6 Execution, verification and recovery

- **FR-050 [P0]** Provider calls occur exclusively through scoped connectors/gateway. Credentials are never placed in prompts or tool result bodies.
- **FR-051 [P0]** Idempotency identities bind tenant, logical action, provider and target. Repeated requests return prior status or enter reconciliation, not duplicate writes.
- **FR-052 [P0]** For uncertain write results, do not retry irreversible or non-idempotent calls before read-back/reconciliation.
- **FR-053 [P0]** Verification is action-specific and checks material provider fields, not merely valid JSON or HTTP success.
- **FR-054 [P0]** Case only reaches `completed` when all required actions have verified outcomes or deliberate human overrides are individually audited.
- **FR-055 [P1]** Retry policy distinguishes safe reads, idempotent writes and uncertain writes; exponential backoff with bounds; dead-letter/reconciliation work queue.
- **FR-056 [P1]** Operator can see interrupted/uncertain operations, recheck provider state, resume safe tasks, or cancel with an audit reason.

### 4.7 Workspace, admin, evaluation and developer tools

- **FR-060 [P1]** Case dashboard is usable without opening an agent conversation: filters, missing facts, next action, owner, quote/booking/payment references and source links.
- **FR-061 [P1]** Operator UI exposes approvals, rejected actions, execution history and reconciliation queues separately.
- **FR-062 [P1]** Role-based access to all reads/writes; admin cannot bypass an immutable organization safety floor without a code/deployment change.
- **FR-063 [P1]** Built-in evaluation harness replays sanitized fixtures with fake providers and captures policy, source, latency, cost and artifact outcomes.
- **FR-064 [P1]** Business pack and connector SDKs include contract tests, schema validation, examples and a sample fake provider.
- **FR-065 [P1]** Self-hosted Docker Compose quickstart with synthetic demo tenant, one example case, docs and health probes.
- **FR-066 [P1]** Export and deletion mechanisms follow tenant retention policies, with exceptions for applicable legal hold, and audit permitted deletions.
- **FR-067 [P2]** Multi-tenant shared cloud deployment requires a separate security design and release gate; never assume per-chat directories provide tenant isolation.

## 5. Architecture and build/buy decisions

### 5.1 Reference stack

| Layer | Proposed technology | Why | Scope condition |
|---|---|---|---|
| HTTP API and webhook ingress | Python 3.12+, FastAPI, Pydantic | Typed interfaces, async endpoints, strong ecosystem | Keep business rules outside controllers |
| Agent SDK | PydanticAI | Typed agents, tool interfaces, model-agnostic orchestration | All runs behind Feya `AgentRunner` protocol |
| Workflow durability | Temporal Python SDK, self-host/dev server | Long-lived state, reliable timers, workflow recovery, activities | Only one durable owner per model/tool call |
| Operational/business data | PostgreSQL, SQLAlchemy 2, Alembic | Transactions, unique constraints, migrations, robust queryability | Authoritative for cases and action approvals |
| Attachments | S3-compatible (MinIO in dev), content-addressed IDs | Bounded files and controlled retention | Never expose arbitrary file paths to model |
| User interface | React + TypeScript, Vite | Case-centric interactive workspace; mature ecosystem | No flow editor in initial release |
| Observability | OpenTelemetry; exporter configurable | Correlate case/run/tenant and tool calls | Sensitive payloads redacted before export |
| OAuth/OIDC | Authlib + deployment-configured OIDC | Identity and provider integration without homegrown auth | Local dev uses explicit fake identity only |
| Packaging | `uv`, Docker Compose, optional Helm later | Repeatable contributor setup | P1 does not require Kubernetes |
| CI quality | pytest, Ruff, type checker, dependency audit, frontend tests | Catches behavior regressions and unsafe contracts | Security tests are release blockers |

**Alternatives considered:** LangGraph instead of PydanticAI/Temporal; CrewAI flows; DBOS or Restate instead of Temporal; Hermes as base runtime; FastAPI+SQLite single-process queue. Choose Temporal for reliable long waits and multi-worker recovery, but publish operational costs and a genuine one-command local development experience. Do not create a second persistence engine for the same agent run.

### 5.2 Services and boundaries

**1. Ingress/API service.** Authenticates users/webhooks, records durable source events, provides case/status/approval endpoints. Does not perform slow LLM calls inline. Transactionally commits cases/events/outbox, then responds.

**2. Outbox dispatcher.** Polls committed outbox rows and reliably sends case events/signals to Temporal. Each delivery has an idempotency key; duplicate signaling is safe. No global transaction spans PostgreSQL and Temporal.

**3. Temporal workers.** Own case workflow code: waits, timers, validated transitions, routing between solo and specialists, timeout management. External I/O (including AI requests) occurs in Activities. Treat workflow code/versioned inputs as replay compatibility contracts.

**4. Agent worker.** Runs bounded PydanticAI agents with read-only/case-scoped tools and artifact/action proposal tools. It holds no unrestricted Gmail/Billit/Calendar mutation token. Restrict egress and filesystem access so a prompt-injected model cannot bypass the gateway by shell or network client.

**5. Policy service.** Pure (or near-pure) deterministic evaluator of typed inputs: actor, tenant, action type, target, risk, evidence, policy version and business constraints. Produces a persisted decision. Only trusted code may write approvals/decisions; agents may not.

**6. Execution gateway.** Sole holder of outbound-write-capable provider credentials. Re-validates policy immediately before write. Serializes logical operation key; records exact attempt and handles idempotency/uncertainty, response, read-back verification. API and agent worker cannot call privileged provider write endpoints directly.

**7. Connector workers.** Implement source reads, explicit allowlisted mutations, OAuth refresh and remote-ID mapping. Provide typed `Capability` sets (e.g. `gmail.threads.read`, `gmail.drafts.create`, `gmail.messages.send`). Business policies refer to capabilities, not raw URLs.

**8. Business workspace.** UI for cases, inbox, evidence, draft previews, operator approvals, provider links, audit and exceptions. A case detail page is primary; chat is contextual.

**9. Object store and PostgreSQL.** Preserve files, evidence, material case state and audit. Apply retention and per-tenant access control.

Trust rule: the agent worker is treated as a **less trusted component** than the policy service and execution gateway. Model output is untrusted data, not authorization.

### 5.3 Recommended repository layout

```text
feya/
  apps/
    api/                # FastAPI routes, authentication, webhook adapters
    console/            # React/TypeScript business workspace
    worker/             # Temporal workers, registration and workflows
    cli/                # feya doctor, pack validate, fixtures and eval
  packages/
    core/               # Case, SourceEvent, Evidence, Artifact, ActionIntent domain
    policy/             # Typed rules, canonicalization and action authorization
    agent/              # AgentRunner, PydanticAI implementation, model routing
    workflow/           # Case workflow contracts and state transition helpers
    connectors/         # Protocol + Gmail/Calendar/Billit/fake providers
    evaluation/         # Fixture runner, graders, fault injection, benchmark exports
    sdk/                # Business pack schemas, connector test contract
  packs/
    generic_enquiry/    # Minimal neutral example
    moving_services/    # Sanitized service quote workflow; no real company data
    consulting/         # Independent second pack proving portability
  migrations/           # Alembic
  tests/
    unit/
    integration/
    security/
    contract/
    e2e/
    fault/
    benchmark/
  deploy/
    compose.yaml
    compose.dev.yaml
    temporal/
  docs/
    architecture/
    security/
    api/
    packs/
    evaluation/
    operations/
    decisions/
  examples/
    synthetic_company/
  .github/
  LICENSE               # After legal/IP audit, proposed Apache-2.0
  SECURITY.md
  CONTRIBUTING.md
  README.md
```

The existing `selectqoma/feya` repository should remain a source of *ideas and extractable generic code*, not be blindly copied with live client data or deployment state. A separate sanitized new repository is safer.

## 6. Workflow engine specification

### 6.1 Two paths, one kernel

**Workflow mode:** For a pack-defined high-risk/multi-step case, the Temporal workflow executes explicit stages (`ingest → classify → evidence → sufficiency → specialist work → validate → draft/action proposal → policy → approval if applicable → execute → verify → transition`). Each stage has typed inputs and outputs. A failed specialist cannot be replaced by the orchestrator freehanding the missing report for a high-risk operation.

**Solo mode:** For low-risk operator questions and routine case reads, the workflow calls one bounded generalist agent. The agent may decide which allowed read tools to use and may propose actions, but all provider mutations re-enter the same policy gateway. A solo agent does not get a stronger permission set because it has fewer stages.

**Routing rule:** A deterministic classifier maps action severity and pack requirements to a minimum execution mode. Example: status lookup → solo; financial quote → workflow; external money transfer → disallowed by default. LLM-proposed task labels are *inputs* to routing, not the final authority. An operator may elevate to workflow or human handling; not silently downgrade a high-risk case.

### 6.2 State transition contract

Define transitions as `(current_phase, event_type, validated_preconditions) -> next_phase`. Preconditions are checked server side. Workflow state in PostgreSQL has `version` and uses compare-and-swap updates to prevent lost updates.

Examples:

- `new + triage_completed` → `triaged`, only if report schema valid and source event corresponds to case.
- `triaged + information_missing` → `waiting_for_information`, with explicit missing keys and requested evidence.
- `waiting_for_information + verified_source_update` → `ready` or re-triage; never reactivate from an unrelated message.
- `drafted + policy_requires_approval` → `awaiting_review`, with immutable action intent.
- `ready_to_execute + gateway_commit_started` → `executing`, with operation lock/idempotency key.
- `executing + uncertain_provider_result` → `reconciliation_required`.
- `verify_pending + verified_expected_state` → `completed` *only if* all case completion predicates hold.

No raw `UPDATE cases SET phase = 'completed'` route exists. A manual completion API calls the same transition validator and records the human override with a reason. Manual override cannot turn an unverified external effect into a verified one.

### 6.3 Durable workflow mechanics

- Workflow instance ID: `tenant/{tenant_id}/case/{case_id}/v{workflow_revision}` (hashed/encoded safely for runtime limits); unique across active case execution.
- Activities carry an operation ID and explicit timeout/retry policy.
- Inbound webhook creates a durable event; dispatcher signals the case workflow. Workflow deduplicates by event ID (outbox delivery is at-least-once).
- Waiting for a customer response uses Temporal signals/updates with case correlation and source identity checks; waiting for approval uses another signal with an already persisted approval record, not raw chat text.
- Long histories use versioned continue-as-new where appropriate, preserving application-owned case identity and avoiding duplicate external effects.
- Cancellation revokes unconsumed approvals and pending intents; in-flight external calls may still have completed, so status becomes `reconciliation_required` when uncertain.
- If Temporal is down, API can persist events; dispatcher resumes delivery later. If PostgreSQL is down, ingestion must fail/retry rather than acknowledge and lose data.
- Temporal replay executes deterministic workflow logic; model calls, clock, random values, HTTP and connector operations live in Activities. Version workflow logic to avoid replay-breaking updates.

**Important implementation choice:** PydanticAI can make individual model/tool calls durable under Temporal. For v1, use *outer Temporal case workflows* with PydanticAI agent executions wrapped at one chosen durable boundary. Do not nest an entire `TemporalDurability` agent inside a generic Activity and accidentally create duplicate durability/retries. Adopt the supported PydanticAI Temporal capability only after clear ownership of durable unit IDs and workflow histories; document this in an ADR.

### 6.4 Retry semantics

| Operation category | Retry policy |
|---|---|
| Provider reads | Bounded exponential backoff; stale evidence surfaced if exhausted |
| Model calls | Bounded retries of transient errors; budget and run-level circuit breaker |
| Draft creation with provider idempotency | Retry only using same provider idempotency token and stable payload |
| Draft creation without provider idempotency | On uncertain response, reconcile by provider search/correlation before next write |
| Financial document creation | Never blind retry after ambiguous result; require verified search/read-back or human action |
| Customer send/dispatch | Disabled by default; if enabled later, exact approval plus provider-specific idempotency/reconciliation; an uncertain send is reported uncertain |
| Human wait | Durable timer and expiration/escalation event; not busy polling |

This is **at-least-once processing with idempotent business effects where achievable**, not a claim of universal exactly-once remote execution.

## 7. Agent runtime contract

### 7.1 Framework-independent interface

```python
from dataclasses import dataclass
from typing import Protocol, Any

@dataclass(frozen=True)
class AgentTask:
    tenant_id: str
    case_id: str
    role: str
    prompt_version: str
    evidence_ids: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    max_steps: int
    max_input_tokens: int
    max_output_tokens: int
    deadline_seconds: int

@dataclass(frozen=True)
class AgentResult:
    output: dict[str, Any]
    claim_evidence_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    model_run_id: str

class AgentRunner(Protocol):
    async def run(self, task: AgentTask) -> AgentResult: ...
```

`PydanticAIRunner` is the P0 implementation. `HermesRunner` is a potential P2 plugin for read-only/sandboxed tasks. Runner identity MUST NOT grant provider write access. Prompt/agent roles are versioned; every run stores `pack_version`, `policy_version`, `model_id`, `prompt_version`, and toolset hash.

### 7.2 Specialist roles (pack-defined)

- **Triage:** intent, language, case type, source evidence references, missing fields.
- **Sufficiency:** determines whether a specific downstream task has enough trustworthy inputs, produces typed missing facts; deterministic validator has final say on mandatory fields.
- **Domain analyst:** e.g., estimate physical volume or project effort, with confidence/unknowns; cannot set authoritative prices.
- **Quote/proposal drafter:** produces structured artifact using rate service and source evidence; no direct provider write tools.
- **Reply writer:** language/formatting based on template and approved facts; no direct send tools.
- **Scheduler:** proposes time/date changes and checks live availability; actual commit only by gateway.
- **Verifier:** may recommend what to compare, but canonical read-back rules are trusted code.

High-risk flows require fresh, version-matched specialist outputs; don't treat the mere existence of a JSON report in an agent-writable folder as proof an agent ran or checked sources. Agent reports are advisory and provenance-linked; a trusted worker records run identity and execution results separately.

### 7.3 Context and memory

Build context from: case summary, required recent messages, evidence references, business pack policy, templates, and relevant verified previous events. Retrieval is tenant filtered, time bounded and relevance limited. Never dump whole logs or a company's full inbox into the prompt.

Separate **business knowledge** (published, versioned policies and rate tables), **case evidence** (provider observations), and **conversational history** (non-authoritative). Retrieval/embeddings are optional for the first pack. Caching may reduce LLM cost but cannot override fresh verification of high-risk facts.

### 7.4 Model selection and spend

- Default BYOK provider API credentials or compatible self-host endpoint; do not rely on shared consumer-subscription OAuth credentials as a multi-tenant/commercial deployment strategy. Validate provider terms before supported authentication flows are documented.
- Configurable per-role model with per-tenant spend limits and hard run budgets. A budget failure transitions to `blocked`/`needs_review` without fabricating an answer.
- Log input/output token counts and costs when provided by model API; separate provider bill estimates from actual invoices.
- Track extraction quality, hallucinated claims, time-to-draft, action accuracy and cost *per verified case*, not only token use.
- API error or model outage must not block operators from viewing and editing existing cases.

## 8. Business packs and adaptation interface

### 8.1 Pack contract

Each business pack MUST declare: `id`, semantic `version`, compatible core API version, case types, required facts, validators, prompt templates, artifact schemas, supported capabilities, workflow/solo routing policy, risk floors, fixture tests, migration hooks and human-readable onboarding instructions.

All pack files are treated as code/configuration maintained by trusted admins. No user-uploaded unreviewed Python may execute inside privileged workers. Schema must reject unknown critical fields, invalid capabilities and any attempted reduction below organization/system-level safety policy.

**Example illustrative pack (synthetic company, nonproduction settings):**

```yaml
api_version: feya.dev/v1alpha1
kind: BusinessPack
metadata:
  id: service-enquiries
  version: 0.1.0
  display_name: Service Enquiries
spec:
  case_types:
    - id: service_quote
      required_facts:
        - contact_email
        - service_date
        - pickup_location
        - destination_location
      artifacts:
        - customer_question_draft
        - quote_draft
  agents:
    triage: {prompt: prompts/triage.md, max_steps: 5}
    draft: {prompt: prompts/quote.md, max_steps: 8}
  routing:
    default: workflow
    solo_allowed_for: [status_lookup, neutral_acknowledgement]
  capabilities:
    read: [email.thread.read, calendar.events.list, accounting.offers.read]
    propose: [email.draft.create, accounting.offer.create_draft, calendar.event.propose]
  policies:
    default_outbound_dispatch: deny
    price_source: pricing/approved_rates.yaml
    require_recipient_from_source: true
    require_verification_for: [accounting.offer.create_draft]
```

The syntax above is **a proposed schema**, not an executable parser. Business-specific names belong in the pack; the kernel only understands typed fields, capabilities, workflow phases, risk and policy outcomes.

### 8.2 Pack portability proof

Create two actual packs before public launch:

1. **Moving-service quote:** photo analysis, fixed/conditional rates, calendar capacity, accounting offer draft.
2. **Consulting proposal:** client brief analysis, scope/effort estimate requiring operator validation, proposal document draft, calendar consultation, project/ticket reference.

The second pack MUST NOT require new core conditions like `if tenant_type == 'consulting'`. New reusable extensions belong in the SDK with contract tests. A third support-case pack may follow only after core abstraction proves stable.

### 8.3 CLI developer experience

Proposed commands:

```bash
feya init --demo
feya up
feya pack validate packs/service-enquiries
feya connector test fake-email
feya workflow simulate --fixture tests/fixtures/new_enquiry.json
feya eval run --suite packs/service-enquiries/evals
feya doctor
```

Developer docs MUST explain all required services and local credentials clearly. `feya init --demo` MUST never send a real email or mutate a real customer provider.

## 9. Policy enforcement and business action protocol

This is Feya's central technical differentiation. A prompt/checklist is *not* authorization. A validator merely returning `PASS` is insufficient unless a privileged component requires its evidence before making a write.

### 9.1 Capability taxonomy

Every connector registers typed operations with a declared risk class:

| Risk class | Example | Default decision |
|---|---|---|
| R0 — read | Retrieve Gmail thread, list Calendar events | Allow after tenant/provider authorization |
| R1 — internal draft | Save internal report, Gmail draft, tentative internal event | Conditional allow after identity/source checks; verify |
| R2 — business artifact | Create un-dispatched Billit offer, update case fields | Gate on pricing/party/source invariants; pack may require approval |
| R3 — external commitment | Send email, dispatch offer, confirm crew booking, close consequential ticket | Require explicit policy and human approval by default |
| R4 — irreversible/financial | Delete customer records, transfer money, pay invoice, destructive bulk operation | Deny in P1; later require separately audited privileged workflows |

An organization can make policy **stricter** than system defaults. A pack cannot lower the immutable safety floor. Never infer R3 authorization from a customer saying “please confirm” or an agent-produced `approved: true` field.

### 9.2 Action intent representation

```json
{
  "schema_version": "1",
  "intent_id": "act_01EXAMPLE",
  "tenant_id": "tenant_demo",
  "case_id": "case_01EXAMPLE",
  "capability": "accounting.offer.create_draft",
  "connection_id": "conn_bill_demo",
  "target": {"customer_ref": "customer_demo_12"},
  "payload": {
    "currency": "EUR",
    "lines": [{"sku": "service_base", "quantity": "2.00", "unit_price": "125.00"}],
    "tax_code": "VAT_STANDARD"
  },
  "evidence_ids": ["ev_gmail_1", "ev_rate_table_2"],
  "workflow_phase_version": 8,
  "policy_version": "policy:11",
  "idempotency_key": "tenant_demo:case_01EXAMPLE:offer_draft:v1"
}
```

This object is a **proposal**, not a provider API request ready to execute. Trusted services assign tenant/connection/actor from authenticated context; they do not accept arbitrary values supplied by an LLM. Numeric money fields are decimal strings; taxes and currency are normalized through provider-specific validated types. The trusted gateway canonicalizes an allowlisted set of action fields into bytes and computes a content digest; the model cannot choose its own digest.

### 9.3 Commit protocol (mandatory)

1. **Propose.** Agent or operator creates typed intent; API validates shape, case identity, target scope, and source references; stores status `proposed`.
2. **Validate facts.** Independent validators check recipient, entity, rate table, missing evidence, policy version and source freshness; never treat agent narrative as proof.
3. **Policy evaluate.** Trusted service evaluates operation, actor, tenant, case phase, provider rights and risk floor; writes decision `deny`, `allow`, `require_approval` including reasons, checked evidence IDs and policy version.
4. **Human decision if required.** Present exact rendered payload and source evidence. Authenticated approver approves the computed action digest with one-use expiry, or rejects/edits. A changed amount, recipient, document body or target invalidates approval.
5. **Revalidate at commit.** Gateway checks connection scope, actor, case version, evidence freshness, payload hash, approval and latest policy. Lock logical operation and consume one-time approval transactionally where applicable.
6. **Execute.** Gateway invokes strictly allowlisted provider operation using secret credentials unavailable to agent runtime. Store attempt status and opaque external ID. Never log credentials or raw PII in traces.
7. **Verify.** Re-fetch the provider record and compare material fields against expected state and approved payload. Store expected vs observed comparison, source version/time, and result.
8. **Finalize.** Only `verified` outcome enables relevant case completion transition. Denials, transient failure and reconciliation are visible to operators.

**Boundary rule:** No alternate provider write route may skip this protocol. Enforce via network isolation, IAM/capability scoping, broker allowlists, code review and red-team tests, not just agent prompts.

### 9.4 Approval semantics

- Only a currently authorized human identity (OIDC session, verified MFA for designated high-risk actions) can approve; action's model task cannot issue or edit approval.
- Approval binds `tenant_id`, `intent_id`, canonical payload hash, target, allowed capability, policy version, evidence precondition hash, approver ID, expiry, nonce. Persist in a table not writable by agent worker.
- Approvals expire (configurable; proposed 30 minutes for send/dispatch), are one-use, and are revoked by any meaningful payload/evidence change.
- Clicking Approve twice results in one authorized logical operation; second event reports existing status, not another provider call.
- Policy decisions and approvals are distinct: policy ALLOW does not always imply immediate side effect; human approval alone does not override technical safety blockers.
- If source changes after approval, re-check and require fresh approval when materially relevant. The gateway is final authority at commit time.

### 9.5 Sample typed policy configuration

```yaml
api_version: feya.dev/v1alpha1
kind: PolicyBundle
metadata:
  id: tenant-safe-defaults
  version: 11
spec:
  rules:
    - id: forbid-customer-dispatch
      capabilities: [email.message.send, accounting.offer.dispatch]
      effect: deny
    - id: allow-gmail-drafts
      capabilities: [email.draft.create]
      effect: allow
      requirements:
        - source_recipient_exact_match
        - current_case_evidence
        - tenant_connection_authorized
    - id: billit-offer-drafts
      capabilities: [accounting.offer.create_draft]
      effect: allow
      requirements:
        - customer_identity_verified
        - approved_rate_table_match
        - fresh_specialist_quote
        - tenant_connection_authorized
        - post_write_readback
    - id: confirmed-calendar-booking
      capabilities: [calendar.event.confirm]
      effect: require_approval
      requirements:
        - live_calendar_conflict_check
        - verified_customer_confirmation
        - operator_identity_verified
```

**Do not evaluate arbitrary Python from YAML.** Policy grammar is small, typed, versioned and compiled to vetted internal predicates. Invalid or unknown predicates cause validation failure and deployment rejection. System risk floors are enforced in gateway code regardless of config.

### 9.6 Reconciling uncertain provider operations

The gateway records an attempt *before* the provider request. If the request times out after an unknown point of remote execution, transition to `uncertain`; do not automatically issue a second write if the operation is non-idempotent. A connector-specific reconciler searches by provider-supported idempotency key or stable exact external correlation; if found, read back and verify. If it can prove absence, it may retry under original logical key. If it cannot prove success or absence, create an operator reconciliation task. An event with external ID but unverified fields is not `complete`.

**No blanket exactly-once claim** is permitted. The provider's API guarantees determine what we can prove.

## 10. Connector interface

### 10.1 Minimal connector protocol

```python
from typing import Protocol

class BusinessConnector(Protocol):
    name: str
    capabilities: frozenset[str]

    async def fetch_source(self, tenant_ctx, source_ref) -> dict: ...
    async def propose_validation(self, tenant_ctx, intent) -> dict: ...
    async def execute_allowed(self, gateway_ctx, intent) -> dict: ...
    async def verify(self, gateway_ctx, intent, provider_result) -> dict: ...
    async def reconcile(self, gateway_ctx, intent) -> dict: ...
```

This is the conceptual contract. Actual interfaces use typed Pydantic models, tenant-bound dependency objects, provider-specific operations, timeouts, structured exceptions and required `idempotency_strategy`. A connector MUST advertise whether a capability is read-only, idempotent, conditionally idempotent, or unsafe to retry.

### 10.2 Initial connector scope

| Connector | Reads | P1 permitted writes | Default blocked |
|---|---|---|---|
| Gmail | Threads, messages, draft metadata | Create/update drafts, labels only if pack policy allows | Send, delete, import, arbitrary mailbox modifications |
| Google Calendar | Calendars/events, conflicts | Tentative internal events (no attendees) | Confirmed event/attendee invitation without explicit authorization |
| Billit | Customer/party, offers, invoices, payment status | Create or update **undispatched** offer drafts, after trusted rate/party check | Dispatch, payment, unrestricted deletion |
| Fake services | Deterministic fixture reads | Simulated mutation/read-back with fault injection | Real network I/O |
| Generic HTTP read | Explicit allowlisted endpoints | None | Free-form arbitrary POST/PUT/DELETE or URL proxy |

Outlook, Slack, HubSpot, QuickBooks, Jira and another accounting provider are **P2** unless chosen to validate second vertical. Integrations are versioned independently; support rate limits, pagination, delta sync, time zones, provider ownership checks, backfills and source tombstones.

### 10.3 Security and OAuth

- Use provider-supported OAuth scopes and rotate/refresh safely; when read and write OAuth scopes cannot be isolated, enforce operations at gateway network/process boundary.
- Store credentials encrypted outside agent worker; do not pass raw tokens in tool results or LLM prompts.
- Use connection IDs bound to authenticated tenant configuration. Agent-supplied URLs are never forwarded directly to privileged services.
- Enforce SSRF prevention, fixed domain allowlists, TLS validation, redirect controls and bounded payload sizes for adapters.
- Do not depend on sharing one person's consumer Claude Code subscription as a commercial multi-company model backend. Use contractual developer/provider APIs or approved customer-owned credentials.
- Each connector has contract tests, simulated service, negative security tests, failure modes and migration/version policy.

## 11. Database and data contracts

### 11.1 PostgreSQL entities

| Table | Key fields and constraints |
|---|---|
| `tenants` | `id`, `slug UNIQUE`, timezone, pack activation, retention config |
| `users`, `memberships` | immutable user identity, `(tenant_id,user_id)` unique, role, revocation status |
| `connections` | `(tenant_id,id)`, provider, external account identity, capabilities, encrypted secret reference, status |
| `cases` | `(tenant_id,id)`, case type, kernel phase, domain stage, owner, `version`, current workflow ID |
| `case_events` | `(tenant_id,id)`, case ID, previous/new version, event type, actor, timestamp, reason |
| `source_events` | `(tenant_id,provider,external_event_key)` UNIQUE, payload pointer, received timestamp, processing status |
| `source_evidence` | `(tenant_id,id)`, provider object ID, version/hash, observed timestamp, object-store reference, classification |
| `case_evidence_links` | case ID, evidence ID, claim purpose; tenant-scoped composite FKs |
| `claims` | source evidence IDs, certainty/status, extraction run, typed fact name/value and review status |
| `artifacts` | `(tenant_id,id)`, case ID, artifact type, schema version, content hash, storage pointer, superseded_by |
| `agent_runs` | `(tenant_id,id)`, case ID, model ID, prompt version, toolset hash, status, cost/usage metadata |
| `action_intents` | `(tenant_id,id)`, case ID, action capability, target, canonical hash, policy version, state, idempotency key UNIQUE per tenant+provider |
| `policy_decisions` | intent ID, version, effect, reasons, evidence digest, created/expires |
| `approvals` | intent ID, approver, exact hash, expires, consumed time, revoked time, decision, nonce unique |
| `execution_attempts` | `(tenant_id,id)`, intent ID, attempt seq, before-send marker, provider result/ref, status, error class |
| `verifications` | intent ID, provider ref/version, checked fields, expected/actual digests, passed/failed/uncertain |
| `audit_events` | append-only, tenant/case/intent/actor, type, time, trace ID, payload digest, metadata |
| `outbox_events` | tenant, unique event key, destination, payload pointer, publish attempts/status |
| `pack_installs` | pack ID/version and immutable configuration digest per tenant |

**Important DB constraints:** foreign keys include tenant ID to prevent cross-tenant relationships, unique external event identity, unique logical action key, conditional uniqueness of active approvals, event sequence and case version constraints, and indexes on `(tenant_id, phase, owner_id)` and `(tenant_id, case_id, created_at)`. No raw secrets in business tables. Sensitive provider payloads are referenced in encrypted/object storage where possible rather than indiscriminately duplicated.

### 11.2 Transaction strategy

- Use short PostgreSQL transactions for case state + audit + outbox. Do not hold a DB transaction across an LLM call or provider HTTP request.
- Use outbox relay, because PostgreSQL and Temporal cannot be atomically committed together in a standard single transaction.
- `cases.version` uses optimistic compare-and-swap; competing updates retry or return a conflict to the caller.
- `action_intents` logical key and status transitions are serialized with row-level locks or equivalent claim/lease mechanism.
- Event replay is duplicate tolerant and does not authorize a new provider mutation without its original action key.
- Never use agent-authored audit files as proof of approvals; only trusted server principals can persist policy decisions and authorizations.
- Application user cannot UPDATE/DELETE immutable audit rows. Backup retention must preserve necessary audit and encryption keys under documented policies.

### 11.3 Source evidence integrity

Evidence records track: `tenant_id`, `provider_account_id`, `object_type`, `external_object_id`, `version/etag`, `observed_at`, `content_sha256`, `source_uri`, `storage_ref`, `pii_class`, `retention_until`, `ingestion_service_identity`. Source URIs are informational, not direct proof of access authority. On refresh, changed hashes produce new evidence versions; do not mutate old observations.

Agent results refer to evidence IDs, but the gateway independently verifies evidence tenant, freshness and origin. If the source can no longer be retrieved, fail closed for high-risk actions or require explicit human reconciliation; don't substitute a guess.

## 12. Authentication, tenancy, privacy and security

### 12.1 Deployment model

**P1: single-tenant-per-deployment** with a shared codebase. This matches service-business isolation needs while avoiding an insecure premature shared-SaaS model. It is still company-agnostic: any company deploys the same software with its own pack and configuration. Tenant ID exists everywhere from day one to enable future shared infrastructure with a security proof.

For a future shared deployment, enforce separate tenant-scoped auth identities, DB row-level security or separate databases, object-storage prefixes/IAM boundaries, worker task namespaces/queues, connection ownership and testing of every query. Home/cwd directories are *not* a security boundary.

### 12.2 Roles

- **Viewer:** permitted case and evidence reads, redacted according to policy.
- **Operator:** viewer plus case ownership, notes, draft editing and low-risk internal tasks.
- **Approver:** operator plus explicit approved capability/risk scope, with step-up authentication when configured.
- **Admin:** connection, pack, user and policy management; still cannot override compiled system safety floor with a chat command.
- **Auditor:** read-only audit/traces with privileged/redacted content controls.
- **Service:** narrowly scoped non-human identity for ingestion, execution, workflow workers and source sync.

Authenticate humans through OIDC where possible. For local demo only, a single explicit development identity is allowed, bound to loopback/synthetic resources. No default public demo admin password.

### 12.3 Threat model and required mitigations

| Threat | Required mitigation and test |
|---|---|
| Prompt injection in email/PDF/tool output | Treat all external content as data; tools fixed; no arbitrary shell/provider write credentials; try hostile prompts in fixture suite |
| Agent fabricates approval or specialist report | Approval DB written only by trusted service; bind to authenticated human and exact hash; reports checked against recorded trusted run and evidence |
| Cross-tenant reference | Auth-derived tenant, tenant-composite FKs, scoped object access, negative tests across every read and write |
| Wrong recipient/party | Source-derived identity, exact-match checks, ambiguous resolution by human, destination allowlists |
| Quote or invoice with unsupported price | Deterministic calculation from approved rate version, currency/tax type checking, read-back verification |
| Modified document after approval | Hash binding and re-validation immediately before provider commit |
| Duplicate provider action | Stable action key, provider idempotency if available, gateway lock, reconciliation on timeout |
| Hidden credential leakage | Secrets external to agents, log redaction, outbound API broker, encryption/key rotation, network egress rules |
| SSRF or malicious connector URL | Exact origin allowlist, address/redirect validation, container egress policies, no arbitrary URL mutation route |
| Malicious pack/plugin | Trusted signed/reviewed pack install; no privileged arbitrary Python in pack; sandbox optional user code separately |
| Unauthorized operator or token theft | OIDC, scoped roles, short sessions, CSRF/exact-origin checks, MFA for sensitive actions, revoked-user re-check at execution |
| Privacy/retention failures | Data minimization, retention schedule, subject export/delete workflows, legal holds, audit, object expiry |
| Model outage/cost runaway | Hard step/token/spend limits, bounded concurrency, human fallback, per-tenant quotas |
| Accidental compliance claims | Document actual threat model and test coverage; do not claim SOC2, ISO or GDPR certification without verification |

### 12.4 Data protection defaults

- Raw correspondence, attachments and source excerpts are personal/business-confidential; use encryption in transit and at rest, least-privilege access, and configurable retention.
- OTel traces/logs omit raw email bodies and credentials by default; allow controlled diagnostic sampling only with tenant policy, automatic redaction and deletion support.
- Never use customer content for model training without lawful basis and explicit appropriate agreement/consent where required. Providers' data-processing terms must be documented.
- Define a per-tenant subject export/delete process covering PostgreSQL, object store, background queues and backup retention constraints. Deletion request cannot silently delete audit records required by law; document lawful retention.
- GDPR obligations (controller/processor, DPIA where needed, SCCs/cross-border transfer, DPA, breach handling) require legal review, not merely a library choice.

## 13. Public API and event contracts

All endpoints below are **proposed v1 interfaces**. Use JSON over HTTPS, opaque IDs, OpenAPI-generated documentation, authorization checked on every read/write, and correlation IDs. In single-tenant deployment the tenant ID is derived from deployment/session configuration; client-supplied tenant headers are not an authority.

### 13.1 Case endpoints

| Method/path | Intent | Rules |
|---|---|---|
| `POST /v1/cases` | Manual case creation | Typed case type; dedup `Idempotency-Key`; operator role |
| `GET /v1/cases?phase=&owner=&limit=&cursor=` | List cases | Tenant-filtered, authorized and bounded pagination |
| `GET /v1/cases/{case_id}` | Case detail | Includes phase, domain stage, version, blockers, source/artifact links |
| `GET /v1/cases/{case_id}/timeline` | Ordered events | Redacted by role, cursor pagination, audit IDs |
| `POST /v1/cases/{case_id}/events` | Manual case event | Trusted actor; schema validation, `If-Match` version check |
| `POST /v1/cases/{case_id}/actions` | Submit proposed action | Does NOT mutate provider; returns intent and policy status |
| `POST /v1/cases/{case_id}/run` | Start solo/workflow run | Mode eligibility checked against pack/risk floor |
| `POST /v1/cases/{case_id}/cancel` | Cancel work safely | Revokes pending intents, may require reconciliation |

Sample case response:

```json
{
  "id": "case_example_01",
  "type": "service_quote",
  "phase": "waiting_for_information",
  "domain_stage": "intake",
  "version": 4,
  "owner_id": "user_demo",
  "missing_facts": ["service_date"],
  "blocked_reason": null,
  "evidence_ids": ["ev_demo_01"],
  "pending_actions": [],
  "next_action": {"type": "request_information", "summary": "Ask for exact date"}
}
```

### 13.2 Actions/approvals/verification

| Method/path | Intent | Mandatory behavior |
|---|---|---|
| `GET /v1/action-intents/{id}` | Inspect exact pending action | Includes immutable digest, evidence and policy reasons |
| `POST /v1/action-intents/{id}/evaluate` | Explicit policy evaluation | Server computes; agent cannot submit `allow` |
| `POST /v1/approvals/{intent_id}/decide` | Approve/reject exact action | Authenticated approver, compare digest and version, one-use |
| `POST /v1/action-intents/{id}/commit` | Request authorized commit | Does not synchronously promise success; returns operation status |
| `GET /v1/action-intents/{id}/status` | Pending/verified/uncertain/failure | Returns provider ref and verification status as permitted |
| `POST /v1/action-intents/{id}/reconcile` | Trigger trusted recheck | Requires operator role and records reason; never blind resubmit |
| `GET /v1/approvals?status=pending` | Operator approval inbox | Tenant and role scoped |

Approval sample:

```json
{
  "intent_id": "act_01EXAMPLE",
  "decision": "approve",
  "expected_payload_sha256": "sha256:computed_by_server_not_by_model",
  "case_version": 8,
  "reason": "Reviewed the draft and verified service details"
}
```

The server checks that supplied digest matches current trusted calculation, not merely that the caller supplied a string. A sensitive commit returns `202 Accepted` plus `operation_id` until read-back completes. User-facing UI must not render `202` as business completion.

### 13.3 Inbound integration events

`POST /v1/webhooks/{provider}/{connection_ref}` validates signature, bounded size, replay window, account ownership and stable provider event ID. The endpoint persists `source_event` and outbox row in one DB transaction before acknowledging. If authentication or DB commit fails, respond with appropriate error so provider retries. Some providers use pull-only sync: a scheduled adapter records the same normalized event envelope.

Normalized source event:

```json
{
  "schema_version": "1",
  "provider": "email_fake",
  "connection_id": "conn_demo_email",
  "external_event_id": "event_123",
  "external_object_id": "thread_456",
  "event_type": "message.created",
  "observed_at": "2026-10-11T08:00:00Z",
  "payload_ref": "obj://demo/sha256-abcdef",
  "payload_sha256": "abcdef"
}
```

Ingestion assigns tenant from the trusted connection configuration, not the event body. Correlation of an event with a case is performed after ownership checks; conflicting case matches create a review item.

### 13.4 Internal events

Event examples: `case.created`, `source.recorded`, `case.triaged`, `case.blocked`, `artifact.created`, `action.proposed`, `action.policy_denied`, `approval.requested`, `approval.granted`, `approval.revoked`, `action.execution_started`, `action.provider_uncertain`, `action.verified`, `action.verification_failed`, `case.completed`.

Event contract has `schema_version`, tenant/case IDs, actor, event ID, causation ID, trace ID, created_at and redacted payload. Consumers must be tolerant of duplicate delivery and versioned schema upgrades; missing required fields fail validation.

## 14. Product UX: business-first, chat-second

### 14.1 Navigation

**Today / Work queue.** Default landing page showing cases needing reply, awaiting customer, draft ready, human review, reconciliation required, and due follow-up. All counters are based on actual case state and validated events, not guesses from email age.

**Cases.** Search/filter by customer, status, source, next action, owner and date. Detail page shows a timeline of verified messages and operations. Offer, calendar and email references are deep-linked to source providers.

**Approvals.** Exact action preview (recipient, amounts, external target, effect, evidence, risk); approve, reject or edit/re-submit. No generic “approve agent” button that covers future unknown actions.

**Connections.** Provider health, configured scopes, last sync time, errors, reconnect and read/write capability summaries. The UI must make draft-only behavior clear.

**Automation/Packs.** Installed pack versions, routing decisions, disabled actions, required facts, rate policy and published changes. Operators can preview dry-run outcomes before activation.

**Audit/Operations.** Every external operation with `proposed/denied/approved/attempting/uncertain/verified/failed` status; incident/reconciliation inbox, exportable records and trace correlation.

**Case chat.** Optional contextual dialogue with solo agent, read-only by default. AI results cite evidence/source links. This is not the primary navigation or sole interface.

### 14.2 Operator design constraints

- Clear distinction between *Draft saved*, *Awaiting human*, *Sent by person*, *External effect verified*, *Uncertain / needs check*.
- Show missing-information requests as explicit fields, not only natural-language prose.
- Ability to complete a task manually without running an LLM; corrective human edits preserve previous provenance.
- No hidden approval inferred from chat messages, Gmail replies or staff role alone.
- Keyboard accessibility, responsive layouts and local timezones/languages; no hardcoded English-only pack assumptions.
- Error screens suggest concrete recovery actions with stable IDs instead of swallowing provider errors.
- Source snippets are redacted according to role, with access-controlled deep links rather than public file URLs.

### 14.3 UX acceptance journey

A new operator must be able to answer within one case detail view: *Who is the customer? What do they want? What do we know? What is missing? Which system contains the source? What is ready? What requires my decision? What actually happened?* If the UI requires reading an agent transcript to answer these questions, it fails the product thesis.

## 15. Observability, resilience, performance and cost

### 15.1 Operational metrics

Collect rates, percentiles and counts with labels limited to safe cardinality:

- Ingest events accepted/deduplicated/rejected; webhook lag; outbox backlog age; sync freshness.
- Active workflows by phase; activity retries and failures; blocked or reconciliation-required case age.
- Agent calls, tool calls, token/cost usage, latency, invalid outputs, budget-denied runs.
- Gate evaluations by outcome/reason; approval conversion/expiry; unauthorized access attempts.
- Provider mutation attempts, uncertain outcomes, verifications passed/failed, duplicate suppression.
- Business outcomes: time to usable draft, time to verified completion, human review minutes, operator edits, rework rate.

Do not put raw customer names, message content, emails, tokens, or unbounded case IDs into high-cardinality infrastructure metric tags. Individual case IDs belong in access-controlled traces/audit records.

### 15.2 Reliability targets (proposal, to be load-tested)

| Target | Initial requirement |
|---|---|
| Webhook durability | Valid event is committed before success acknowledgment; simulated loss/duplicate tested |
| API responsiveness | p95 basic case reads < 500 ms on reference machine under documented load (excluding upstream provider) |
| UI interactivity | p95 initial authenticated case view < 2 s on reference deployment, with synthetic fixtures |
| Queue recovery | Stop/restart workers without losing queued case events or silently replaying uncertain mutations |
| Provider uncertainty | 100% of ambiguous consequential outcomes appear in reconciliation queue |
| Case completion correctness | 100% of completion transitions have required verified outcomes or explicitly labeled audited override |
| Backup/restore | Nightly logical backup and restore-to-staging test; choose measurable RPO/RTO with host/operator, not pretend universal SLO |
| Capacity | Demonstrate 100 concurrently active/waiting synthetic cases at P1; load-test further before multi-tenant offering |
| Service availability | Publish test environment and measured uptime; do not promise 99.9% solely because Temporal is used |

Source synchronization has freshness indicators. A stale or partial provider snapshot must never be labeled “no work” or “confirmed available.”

### 15.3 Deployment/operability

P1 self-host Compose includes API, web UI, PostgreSQL, Temporal development/self-host server, worker and a fake provider. S3-compatible storage is optional for minimal demo but required when real attachments are enabled. Production docs cover TLS, reverse proxy, OIDC configuration, encrypted backups, credentials, migrations, health/ready endpoints, rollback and resource-sizing examples based on tested measurements.

Use build tags and reproducible dependency locks; images run as non-root. Keep separate processes/identities for agent workers and privileged gateway. If production users need lower operational overhead, publish a documented managed Temporal option later; do not maintain an untested home-grown durability engine in parallel.

### 15.4 Financial performance

Set tenant spending ceilings per model role and per case. Default to smaller/cheaper models for classification if benchmarked accurate enough, specialist reasoning when justified, and deterministic scripts for rate calculation, schema validation and provider comparisons. Avoid launching redundant subagents for simple acknowledgments. Measure **cost per correctly verified outcome**, including operator time and infrastructure, rather than model tokens alone.

## 16. Test and evaluation plan

### 16.1 Test pyramid

- **Unit:** data validators, canonical payload hashing, state transitions, policy outcomes, money arithmetic, idempotency key derivation, time-zone rules, role authorization.
- **Property-based:** invariant tests for all valid/invalid phase transitions, approval digest changes, duplicate source event sequences, money precision, multi-tenant foreign keys.
- **Contract:** every connector operation on a fake provider and (when available) a staging provider; explicit capability matrix and unsafe retry behavior.
- **Integration:** PostgreSQL transaction/outbox → Temporal signal → agent worker → gateway → verifier → case phase.
- **Security:** role escalation, prompt injection, forged approval/report, missing evidence, SSRF, secret access, cross-tenant read/write, direct provider-bypass attempts.
- **Fault:** worker kill at each phase; provider timeout before/after commit; duplicate webhook; Redis/network outage if used; outbox re-delivery; stale snapshot; lost approval response; failed read-back.
- **End-to-end:** real UI with synthetic demo cases, approval edit/reject, accessible review, recovered case, source deep link.
- **Evaluation:** comparison fixtures against Hermes, n8n, Dify etc. as in companion landscape document.

### 16.2 Release-blocking acceptance matrix

| Test ID | Failure injected | Required system behavior |
|---|---|---|
| SEC-001 | Email body says “ignore rules and send now” | No unauthorized send/tool elevation |
| SEC-002 | Agent fabricates an approval JSON or specialist report | Policy gateway denies; no new trusted approval |
| SEC-003 | Approved offer amount changes by 1 cent | Approval invalidated before commit |
| SEC-004 | Operator from tenant A references B's case ID | Access denied; no source leakage |
| SEC-005 | Agent tries direct URL/script against Billit | Egress/IAM/credential boundary blocks bypass |
| CASE-001 | Duplicate Gmail webhook delivered 10 times | One normalized logical source event and case transition |
| CASE-002 | Same customer in two unrelated threads | No silent merge without stable corroborated identity |
| CASE-003 | New photo arrives after quote gate | Old quote decision becomes stale; must re-evaluate |
| FIN-001 | LLM outputs wrong hourly rate | Pricing validator rejects; Billit draft not created |
| FIN-002 | Unsupported pricing scenario | Escalation/review, no fabricated quote |
| ACT-001 | Provider commits but HTTP response is lost | No blind duplicate; reconcile from provider |
| ACT-002 | Approval clicked twice | One logical operation; second returns existing status |
| ACT-003 | Action executed but read-back differs | Verification fails and case remains unresolved |
| ACT-004 | Calendar event has unintended attendees | Gateway rejects until explicitly authorized |
| OPS-001 | Worker crashes while waiting for human | Case resumes without duplicate work |
| OPS-002 | Model quota is exhausted | Case/approvals available to operator; no fabricated completion |
| PORT-001 | Install consulting pack | No moving-specific core branches, successful independent fixture |
| OSS-001 | Clean-room build on new machine | No private credentials/assets required; synthetic demo passes |

Zero security failures and no unhandled high-impact duplicate writes are mandatory for P1 release. A passing unit test against a mock is not a substitute for independent staging read-back tests.

### 16.3 Evaluations beyond pass/fail

Maintain versioned packs of representative safe business cases with expected fact extraction, draft quality rubric, policy actions and cost. Use one set for regression, one hidden/adversarial set for final launch gate. Human graders should blind-review ambiguous text outputs and annotate why disagreements exist. Report confidence intervals and negative findings. Preserve model/tool/prompt/policy version per result to make failure reproduction possible.

## 17. Migration from today's Feya

**Do not rewrite the existing production bot in place.** Build the new kernel beside it and apply the *strangler migration* pattern: absorb one safe capability at a time while the existing system remains available.

### M0. Inventory and rights audit

Inventory currently tracked `engine/`, `clients/`, `deployed/`, `ops/`, `docs/`, test fixtures and historical files. Mark generic reusable code, company-owned data, deployment-specific secrets/configs and unsafe sample documents. Run full git history and artifact scanning for secrets and personal/customer data; scrub the future public tree and assess whether already exposed credentials need rotation. Clarify contributor ownership and client data rights before copying material to a new public release repository.

### M1. Extract domain contracts independently

Implement `Case`, `Evidence`, `ActionIntent`, `PolicyDecision`, `Approval`, `Verification` and fake connectors in a new Python package. Migrate only generic code and sanitized tests. Existing MovingVan remains untouched.

### M2. Shadow-mode observation

Build a read-only Gmail/calendar/Billit sync in a separate isolated test environment. Convert historical synthetic/sanitized events into cases; compare extraction and stage assignments against current system without writing to real providers. Do not port production session state as a writable database.

### M3. Draft-only provider pilot

Enable Gmail draft creation **only in isolated staging accounts** with gateway policy, recipient gate and read-back verification. Prove no unauthorized sends are possible; validate fault tests for duplicate actions. No customer-visible sends from new engine.

### M4. Business pack parity

Represent moving-service knowledge in a sanitized pack: rate calculators, standard questions, artifact templates, calendar conventions. Match established correct case outcomes on a bounded retrospective test set without copying real PII into public fixtures.

### M5. Second-vertical and release readiness

Deploy a consulting/proposal pack to a separate synthetic company with its own fake or staged provider integrations. Run portability and tenant boundary tests; then do competitor bake-off and code/security review. Only after explicit go/no-go decision should real client traffic migrate.

### Preservation rules

Never delete/overwrite live bridge/console databases, transcripts, OAuth credentials, provider drafts, queues or approval records during extraction. Create separate source-to-target reference mappings, checkpoint imports and rollback instructions. External mutations already completed must be reconciled with provider IDs; never replay a historical send/offer creation as a new action.

## 18. Phased implementation milestones and Definition of Done

The phases are a **dependency order**, not a fabricated delivery schedule. Each ends with a runnable test and a decision about whether the product thesis remains valid.

| Phase | Must deliver | Completion gate |
|---|---|---|
| **P0-A: Competition proof** | Hermes Kanban + Feya-plugin spike; independent case/gateway spike; choose baseline and ADRs | Comparable synthetic case, recorded effort/security findings; no speculative moat claims |
| **P0-B: Domain kernel** | Typed models, PostgreSQL migrations, case/event state validator, fake providers, tenant IDs | Unit/property tests and basic case API |
| **P0-C: Durable execution** | Temporal worker, outbox, signals, retries, dedupe, safe stop/restart | Kill/recovery integration suite, no lost events |
| **P0-D: Hard safety boundary** | Intent policy/approval/gateway/verification state, network/secret isolation | Red-team tests deny unauthorized writes and stale approvals |
| **P0-E: Vertical slice** | Synthetic email intake → triage → missing info → draft → case view | End-to-end demo without real customer mutation |
| **P1-A: Financial artifact** | Trusted rate service + simulated Billit offer + read-back/reconciliation | Wrong pricing and after-commit timeout tests pass |
| **P1-B: Business operator UI** | Cases, approvals, provider links, audit and unresolved work queue | Nontechnical scenario test; no transcript required |
| **P1-C: Real provider staging** | Gmail, Calendar, Billit scoped adapters and live read-back in staging | Provider contract/security tests and explicit auth scopes |
| **P1-D: Portability** | Consulting/proposal pack, independent case lifecycle | No core moving-only logic; both packs pass e2e tests |
| **P1-E: OSS release** | Clean repo, license review, docs, CI, tests, sample data, security disclosure | Release checklist in section 19 is fully signed off |
| **P2: Ecosystem** | Additional connectors, pack marketplace, optional HermesRunner, hosted multi-tenant product | Driven by adoption and separately threat-modeled |

**No UI workflow designer, no plugin marketplace, no multi-tenant SaaS and no broad generic assistant enhancements before P1-E.** This is a deliberate competitive strategy, not missing ambition.

## 19. Open-source launch checklist and governance

### 19.1 License and ownership

- Recommended license: **Apache-2.0** for independently authored core, subject to IP review (its explicit patent grant is useful for infrastructure software). Do not simply copy code under unknown permissions.
- `LICENSE`, `NOTICE` where relevant, dependency attribution, SPDX metadata, CONTRIBUTING, DCO sign-off policy, CODE_OF_CONDUCT, SECURITY, GOVERNANCE, CHANGELOG and versioned release tags.
- All sensitive business policies, packs and customer data from real clients require documented rights and deidentification. No historical credentials or real customer documents in git or published release images.
- Third-party Dify and n8n code licenses are not freely interchangeable with Apache-2.0; never copy code or UI components under restrictive licenses without legal review.
- Important: current `selectqoma/feya` is **public** but the source audit did not locate a root `LICENSE` file; public visibility alone does not confer an OSI-compliant open-source license. Verify and correct rights posture before launch.

### 19.2 Security/publication gate

- [ ] Full repository + git-history secret scan, manual file review, private source redaction and exposed credential rotation decision.
- [ ] Dependency/SBOM audit and license compatibility report.
- [ ] Auth/session, tenant and gateway authorization tests pass in CI; no default public secrets/users.
- [ ] All consequential provider writes require gateway and trusted validation; bypass attempts tested.
- [ ] No auto-send or external financial operation is enabled in published default configuration.
- [ ] Data retention, backup and incident response playbooks exist, including instructions for revoking provider tokens.
- [ ] Staging fault injection covers duplicated webhooks, provider lost response, stale approval, customer identity collision and model prompt injection.
- [ ] At least one independent security reviewer signs off on threat model, auth boundaries and deployment defaults.
- [ ] All demo data are synthetic; third-party logos/brands used legally; support policy and security contact published.

### 19.3 Developer/public acceptance gate

- [ ] `docker compose up` documented and runnable from clean checkout on target platforms with deterministic synthetic demo.
- [ ] Quickstart: connect fake provider, open demo case, draft, approve mocked intent, verify mocked provider result, view audit.
- [ ] Pydantic/connector schemas and API docs generated from code; pinned versions.
- [ ] Tests run offline for core; optional provider staging suite clearly marked.
- [ ] Second pack demonstrates portability without modifications to core.
- [ ] Honest, reproducible benchmarks against Hermes Kanban and at least one workflow builder published. Weaknesses included.
- [ ] Release support matrix lists what has been tested and what is experimental; no implied enterprise compliance certifications.

### 19.4 Community model

Core must include source-evidence validation, policy gateway, approval records, operator UI, case engine and verifier. Optional paid offering may sell managed hosting, onboarding, SSO integrations, professional support and SLA-backed services; never make safe execution proprietary. Accept community connectors via tested SDK/maintainer review. Use semantic versions and migration notes. Large architecture changes require ADR/RFC discussion.

## 20. Architecture decisions (ADRs to record formally)

| ADR | Decision | Key rejected alternative / revisit trigger |
|---|---|---|
| ADR-001 | Business `Case` is core object, not agent conversation | Revisit only with user research disproving case-centric task model |
| ADR-002 | Python/FastAPI, typed core, PydanticAI behind `AgentRunner` | Revisit SDK if cost/quality/features demonstrably improve elsewhere |
| ADR-003 | Temporal as durable outer engine | Revisit if local deployment burden overwhelms long-running requirements; compare DBOS/Restate |
| ADR-004 | PostgreSQL is business source of truth, Temporal owns execution history | Never use conversation transcript as authorization store |
| ADR-005 | Independent gateway holds write credentials and authorization | Non-negotiable; no prompt-only safety model |
| ADR-006 | Draft-first, deny-by-default high-risk actions | Revise only with explicit risk model, controls and tests |
| ADR-007 | Single tenant per deployment for P1 | Shared multi-tenancy only after new isolation threat model and tests |
| ADR-008 | No Hermes fork; optional restricted runner adapter | If Hermes plugin spike clearly beats standalone approach, revisit before platform work |
| ADR-009 | No workflow canvas before proof of operational value | Revisit after users cannot express common workflows with packs/config |
| ADR-010 | Apache-2.0 proposed for clean new core | Subject to IP, trademark and dependency review |

## 21. Unresolved decisions and explicit discovery work

These questions are real engineering/product unknowns, not details to gloss over:

1. **Model-provider legal/commercial terms:** Confirm approved production model account strategy for each target provider; existing subscription-based CLI assumptions must not leak into multi-company product licensing.
2. **Independent vs Hermes-backed agent execution:** Measure two vertical slices. A Hermes-based worker may be substantially cheaper to reach feature parity, but preserving an independent gateway is mandatory.
3. **Temporal deployment cost:** Benchmark smallest realistic customer VM and a local developer laptop; confirm developer experience and total memory use. Reassess engine only if empirical complexity demands it.
4. **CRM relationship:** Decide whether Feya remains a lightweight case workspace or integrates into established CRMs first. Avoid building every CRM capability.
5. **Pricing adaptability:** Determine how domain rate calculators are authored safely. The engine must not hardcode moving-company concepts and must not execute arbitrary customer-supplied Python with write credentials.
6. **Identity/correlation:** Measure false merges/splits in real business data; define human resolution UI and source provenance.
7. **Approval policy:** Which actions must require step-up authentication or two-person control in specific regulated/customer settings?
8. **Pack portability:** Validate a genuinely different business workflow with external beta users, not just a renamed moving-company sample.
9. **Retention/legal basis:** Requirements differ by industry and jurisdiction; get professional review before broad availability.
10. **Competitive advantage:** Test usability, safety and provider correctness head-to-head; if Feya offers no measurable gain, narrow scope rather than claim uniqueness.

## 22. First engineering sprint backlog (order, not schedule)

**Ticket FEA-001:** Create clean repository, code owners, typed Python package, dependency lock and CI; synthetic-only data; no production secrets.  
**FEA-002:** Define Pydantic schemas for `Case`, `Evidence`, `ActionIntent`, `PolicyDecision`, `Approval`, `Verification` and publish examples.  
**FEA-003:** Implement database migrations, case version transitions, source event dedup and transactional outbox.  
**FEA-004:** Implement fake email, Calendar and accounting providers with configurable timeouts/commit ambiguity; tests first.  
**FEA-005:** Implement one Temporal case workflow, signal correlation and crash recovery tests.  
**FEA-006:** Implement deterministic policy grammar and gateway that denies arbitrary provider action; negative bypass suite.  
**FEA-007:** Add `PydanticAIRunner` as read-only structured triage of synthetic emails; typed source citations.  
**FEA-008:** Implement draft artifact creation via fake provider, exact recipient policy, read-back verifier and idempotency key.  
**FEA-009:** Build case list/detail and single approval/reconciliation view; no chat-first UI.  
**FEA-010:** Reproduce the same scenario in Hermes Kanban and n8n; record extensions, setup hours, output quality and failure behaviors.

**First meaningful demo:** A fake customer sends an incomplete service enquiry; Feya creates a tracked case, explains missing facts, drafts a response, displays sources and the operator's next task. After a synthetic reply, it proposes a price-validated quote; a fake provider commit is verified. A simulated lost provider response is reconciled without creating duplicates. Deliberate wrong-recipient and fake-approval attempts are denied.

This demo is sufficiently small to build and sufficiently strict to prove the critical architecture. Everything else earns its place after that.

## 23. Selected technical sources

- [Current Feya repository](https://github.com/selectqoma/feya)
- [Hermes official source and Kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)
- [PydanticAI durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/)
- [PydanticAI Temporal integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/)
- [Temporal Python guide](https://docs.temporal.io/develop/python)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [CrewAI Flows](https://docs.crewai.com/en/concepts/flows)
- [Apache-2.0 license (OSI)](https://opensource.org/license/apache-2-0)
- [Companion competitor analysis](01_COMPETITIVE_LANDSCAPE.md)

---

**Product gate:** If a business cannot tell what happened without reading the agent's chain of chat messages, Feya has not achieved its product goal.  
**Engineering gate:** If a language model can bypass the action gateway using another tool, Feya has not achieved its security goal.  
**Strategic gate:** If comparably configured Hermes/n8n can do the same work as reliably with equal or less operator effort, Feya has not yet demonstrated its differentiation.
