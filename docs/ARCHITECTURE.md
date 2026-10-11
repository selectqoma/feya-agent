# How Feya Agent works

Feya supports conversations and independent delegated tasks alongside business cases. A case records the incoming request, its evidence, missing facts, proposed actions, approvals and observed outcomes. The current implementation handles one enquiry-to-quote workflow with two business packs.

## A case from start to finish

1. The API records an incoming message, its case and an outbox event in PostgreSQL. Duplicate source events are deduplicated.
2. The outbox dispatcher signals a durable Temporal case workflow. Its worker calls the reasoning process to extract structured facts with source citations.
3. Application code validates the facts against source text and pack requirements. Missing information produces a reply draft. Complete information produces a deterministically priced offer proposal.
4. The operator reviews the exact offer. Approval binds its payload, recipient, source revision, pack and policy versions; it expires and can be consumed once.
5. The separate execution gateway checks authorization, journals an attempt, and calls a simulated provider. Independent read-back must match the intended result before the case is marked verified.
6. If a response is lost after a write, the case waits for verification. Reconciliation looks for the existing object instead of blindly repeating the write. Unresolved outcomes remain visible to the operator.

PostgreSQL owns business state. Temporal owns workflow execution and durable waits. The model proposes facts; it does not calculate authoritative prices, grant approvals or call business-provider tools.

## Conversation and delegated tasks

A chat message and its work event commit together in PostgreSQL, with a client request ID for duplicate suppression. Conversation events run in order. A reasoning step may answer, ask for input, request a read-only case tool, or delegate an objective and deliverable. Delegation creates a task and a separate durable workflow, so the conversation can continue independently.

The trusted worker executes only `list_cases` and `read_case`, scoped to its workspace. Sources are immutable snapshots for a generation. Task outputs have no provider-write authority. A completed task saves Markdown and posts the result to its originating conversation. Missing material leaves the task waiting for input; an operator can add sources and resume it.

Four persisted model-call reservations bound each event, including uncertain calls after interruption. A lease rejects duplicate execution results; a task generation rejects stale results after steering or cancellation. An in-flight read/model call may finish after cancellation, but it cannot publish a result for the cancelled generation. Paused and failed tasks can resume with a fresh generation and budget; cancelled and completed tasks are terminal. Model-call budgets are finite per generation, not a company-wide spend cap.

`work_db.py` has separate metadata and an additive migration, preserving existing case data. PostgreSQL owns messages, sources, tasks, progress and the outbox; Temporal coordinates the work. There is one durability engine. The API and CLI expose the same task state, version checks and downloads.

## What can be reused

| Layer | Current extension point | Limit |
|---|---|---|
| Business rules | YAML packs define required facts, service rates, currency, tax and reply wording | Both supplied packs use the same enquiry-to-quote workflow |
| Reasoning | Offline fixture, PydanticAI model adapter, or official Claude CLI adapter | Extraction plus bounded conversation/task reasoning; only supplied text and read-only case tools |
| Case infrastructure | Evidence, approvals, audit, outbox, execution attempts and verification | New business workflows still need code and tests |
| Providers | Email and accounting simulators with failure injection | Real connectors are not implemented; there is no stable public connector SDK |
| Operator workspace | Queue, case detail, sources, approvals, reconciliation and export | No contact/account CRM, role administration or general workflow designer |

To add another enquiry business, start with `packs/consulting.yaml`, change the pack ID, required facts, rates and synthetic fixture, then run `uv run feya pack validate packs`. Packs are loaded at startup; restart the app after edits. A changed pack invalidates proposals bound to its earlier digest. Run the same successful and failure journeys before claiming the new pack works.

An onboarding or support-resolution workflow is future work, not something arbitrary YAML can currently create. Keep its workflow-specific logic outside the reusable authorization and verification rules.

## Process boundaries

The API serves the local React workspace and the command terminal. `feya` opens the terminal; `/setup` saves a validated company pack in ignored `.local/company.yaml`. API, worker and gateway load that same pack on startup. The terminal checks that the running company matches local configuration before operating on cases. A trusted worker coordinates case processing. The reasoning service has its own token and model authentication; the gateway has a different token. Only the gateway implements the simulated business-provider writes.

These are local process boundaries, not a production sandbox. The development database role has broad privileges, the operator identity is fixed, and production network isolation is absent. See [SECURITY.md](../SECURITY.md) before changing deployment assumptions.

## Design references

The [implementation decision](decisions/0001-local-vertical-slice.md) explains why this slice uses an independent case kernel. The [original specification](research/02_PRODUCT_TECHNICAL_SPEC.md) is a target design; [build status](BUILD_STATUS.md) records implemented behavior, verification and remaining work. No measured advantage over Hermes or other agent/workflow products is claimed.
