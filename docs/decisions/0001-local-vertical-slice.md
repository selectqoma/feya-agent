# ADR-001 — Build the independent case/gateway slice first

Status: provisional implementation decision, 11 October 2026.

The research recommends comparing a Hermes Kanban extension with an independent case kernel. The user's immediate instruction is to start building locally and support lab subscriptions where possible. This checkout implements the independent synthetic slice on the specified Python/FastAPI, PostgreSQL, Temporal, PydanticAI and React/TypeScript stack. It is not a Hermes fork and claims no measured advantage over Hermes or n8n.

The first deliverable is a complete, locally runnable case journey with the adversarial and recovery tests that make the architecture assessable. The existing deployment has uncommitted changes and company data; it stays untouched. No production source/credentials/fixtures were imported. The supplied research was preserved with its original filenames.

## Implemented decisions

- One Python package rather than an early multi-package monorepo: domain, persistence, policy, runtime and gateway remain separate modules/processes with clear dependency boundaries. Split packages only when separate releases or teams need them.
- PostgreSQL is authoritative for business state, exact approvals, attempt records and source deduplication. Temporal alone owns long waits and execution history. Outbox delivery is at least once, with application event deduplication.
- The outer Temporal workflow invokes reasoning as one activity boundary. No nested PydanticAI durability engine.
- Tool-free extraction is sufficient for the first two packs. Deterministic validation, drafting, pricing and verification avoid unnecessary model calls and agent delegation.
- API, reasoning and gateway are separate processes. The reasoning process receives an agent-specific token and model auth, not a gateway token or business credentials. This local process split is **not yet production egress/IAM isolation**.
- Only two mutation capabilities: email draft creation and undispatched accounting offer creation. Everything else is rejected. Simulated providers persist separately committed observations; gateway results are verified by a second read.
- Approval consumes one exact intent digest, current source revision, current pack digest and current policy version. A model does not choose its own digest or approver identity.
- After an ambiguous provider call, there is no blind write retry. Correlation read-back can establish success; absence/mismatch stays unresolved for a human. This deliberately does not claim universal exactly-once execution.
- Consumer subscriptions are explicit local, account-owner choices, based on current documented paths. API billing is a separate explicit selection. No fallback to another billing mode.
- Compose runs infrastructure; host Python runs application processes for fast local development. Full containerized self-host packaging remains a release task.

## Remaining decision gates

The installed Hermes CLI was inspected and does expose durable Kanban. A fair end-to-end Hermes/n8n build, setup-effort measurements and adversarial comparison have **not** been performed. Complete those before declaring a product advantage or committing to a public platform roadmap. The current independent implementation is a concrete comparison candidate.

Apache-2.0 remains proposed, not granted. Production auth, least-privilege DB roles, write-provider network isolation, provider staging tests and rights/security review are supported-production-release blockers. Public source publication is an experimental preview, not a sign-off of those gates. Local fake identity, development database credentials and simulated read-back cannot establish production safety.
