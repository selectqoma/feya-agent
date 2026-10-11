# Feya Agent product development map

Research date: 11 October 2026. Planning baseline: Feya commit `7c28420`.

Feya should become a business assistant that understands a company, prepares useful work, and carries agreed tasks through to verified outcomes. The next investment should connect its working case engine to conversation, company knowledge and one real business system. Reusable playbooks and coordinated specialists become more valuable once that foundation handles real work.

Implementation update: the first conversation/delegated-task slice is implemented: browser and CLI chat, supplied text, read-only case tools, bounded background work, steering/cancellation, recovery and Markdown artifacts. Rich onboarding, editable business drafts, web research and the other milestones remain planned. See [build status](../BUILD_STATUS.md) for verified scope.

This is a proposed development sequence. Competitor capabilities below come from current first-party documentation; they are not comparative performance results. Existing Feya capabilities are taken from the current implementation and its recorded verification. The initial customer assumption is a small service business with an owner or operations lead managing enquiries, proposals and customer follow-up. Validate that assumption with pilot users before choosing the second connector.

## Where Feya starts

Feya already has a local browser workspace and command terminal, a shared pixel F, `/setup` and `/onboard`, configurable enquiry packs, structured model extraction, source evidence, deterministic pricing, exact approvals, durable workflows and simulated provider verification. Company setup currently changes a name, template and rates. It does not interview the business, connect its tools or ingest its operating procedures.

The largest gaps are natural-language interaction, real connectors, document knowledge, editable drafts and fact correction, inspectable long-term memory, scheduled routines and production identity. Two packs reuse the same enquiry-to-quote process; a second industry using that process does not establish support for unrelated workflows. See [build status](../BUILD_STATUS.md) and [architecture](../ARCHITECTURE.md).

## What the comparison products contribute

| Product | Documented capability worth studying | Proposed adaptation for Feya |
|---|---|---|
| Hermes Agent | Durable Kanban tasks, named workers, dependencies and human review | Standalone delegated tasks, optionally linked to a business case, with an owner, completion conditions, handoff evidence and explicit blocked states. Reuse Feya's existing durability engine. [Kanban documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban) |
| Hermes Agent | Persistent memory, skills loaded on demand, and recurring or event-triggered tasks | Company knowledge, reviewable operating playbooks and visible follow-up commitments. [Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory), [skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills), [scheduling](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) |
| Claude Code | Persistent instructions, slash-invoked skills, isolated subagents, hooks and MCP extensions | A conversational CLI with explicit commands; load relevant procedures when needed; use code for mandatory checks. [Extension model](https://code.claude.com/docs/en/features-overview) |
| OpenClaw | Agent routing and a memory architecture that records provenance and separates episodic observations from curated memory | Keep company, customer and case knowledge scoped; distinguish imported claims from approved facts and operating rules. [Routing](https://docs.openclaw.ai/concepts/multi-agent/index.html), [memory architecture](https://docs.openclaw.ai/concepts/memory-architecture) |
| Letta | Persistent, shareable memory blocks, including read-only blocks | An inspectable company profile and shared approved policy context, with separate editable working notes. Prompt context remains separate from enforceable execution policy. [Memory blocks](https://docs.letta.com/v1-sdk/memory/memory-blocks) |
| n8n | Approval of individual agent tool calls through separate channels; evaluations against datasets | Review actions where operators already work; replay representative cases before changing models, prompts or playbooks. [Tool approval](https://docs.n8n.io/advanced-ai/human-in-the-loop-tools/), [evaluations](https://docs.n8n.io/advanced-ai/evaluations/overview/) |
| Activepieces | Agents bound to projects with their own connections and resources; a connector development workflow | Show the actual connected company account before enabling capabilities. Build a small connector contract and use existing integrations where they fit. [Agent scope](https://www.activepieces.com/docs/agents/manage), [building pieces](https://www.activepieces.com/docs/build-pieces/building-pieces/build-with-ai) |
| Dust | Shared spaces containing conversations, human or agent tasks, and files, with restricted membership | A business workspace where people and agents share the same case context and deliverables. [Pods](https://docs.dust.tt/docs/user-documentation/pods/overview) |
| Relevance AI | Tool-level autonomy settings, explicit human approval, and configurable agent teams | Permission presets for each capability, named escalation owners and a clear exception queue. [Approval modes](https://relevanceai.com/docs/build/agents/give-your-agent-tasks/approval-mode), [platform overview](https://relevanceai.com/docs/get-started/introduction) |

Approvals, memory and multiple agents are established product patterns. Feya's opportunity is the quality of the combined business experience: how quickly an operator can teach a process, inspect a proposal, correct it and trust the recorded outcome. That advantage needs a measured comparison.

## The intended product experience

An operator opens Feya and asks, “What needs my attention today?” Feya answers from accessible cases and sources. They can then ask it to prepare a proposal, collect missing information or monitor a deadline. Once a request creates an ongoing commitment or a proposed external action, it becomes visible work with an owner, state and completion evidence.

The conversation agent is the default entry point in both the CLI and browser. It can answer questions, discuss ideas and accept open-ended assignments without requiring a business pack or a predefined workflow. Examples include researching a supplier, comparing proposals, drafting a document and investigating a blocked case. It chooses useful steps within the available tools and permissions, asks for missing information when necessary, and reports unsupported capabilities clearly.

A simple question can remain a conversation. Delegated work gets a durable task, which can exist independently of a business case. A repeatable business process can optionally use an approved workflow. The CLI, browser and later team channels should call the same services and show the same state.

### Conversation and delegation

| Object | Purpose | Example |
|---|---|---|
| Conversation | Discuss, clarify, answer and steer work | “What should we consider when choosing this supplier?” |
| Delegated task | Carry an assignment to a defined result, with progress and recovery | “Compare these three suppliers and produce a recommendation with sources.” |
| Business case or workflow | Apply a repeatable process with domain rules and external actions | “Prepare an offer using our approved rates and review process.” |

A delegated task records the originating conversation, objective, expected deliverable, available sources and capabilities, owner, budget, optional deadline, progress, blockers and result artifacts. It can move through queued, running, waiting for input, waiting for approval, completed, failed and cancelled states. Users can check progress, redirect, cancel or resume work. Reopening the app must recover the assignment and its latest state; closing a terminal must not imply cancellation.

Short tasks may finish in the conversation. Longer tasks run under the durable worker and return results to the originating conversation and task list. The conversation remains available while a background task runs. A correction to the assignment updates its recorded scope and invalidates affected pending proposals; it must not silently leave the old plan executing.

Start with one bounded general agent that can plan, use approved research and document tools, and produce artifacts. It may use a specialist later when the task benefits. A delegated assignment does not require a swarm or a new workflow definition. Model reasoning can choose the steps; durable orchestration preserves state, budgets and recovery. External business actions still use the existing intent, policy, approval and verification path.

Completion means the requested deliverable exists and is accessible, with supporting sources and unresolved limitations where relevant. A research task can complete with a saved report; a provider write requires provider verification. An unsupported request or a statement that work was done is not a completed task.

The following describes the target command surface. `/work` now lists local delegated tasks and `/onboard` configures an existing business pack; the richer behavior and other commands remain proposed:

```text
/onboard      Teach Feya the company and review its proposed configuration
/connect      Connect and verify one business or model account
/knowledge    Inspect sources, permissions and freshness
/memory       Review facts, corrections and pending memory changes
/skills       Inspect and test reusable business procedures
/teach        Turn an operator correction into a proposed procedure change
/routines     Review scheduled work, next runs and delivery destinations
/work         Inspect delegated tasks, results, owners, blockers and deadlines
/usage        Inspect model usage and configured budgets
/replay       Test a proposed change against saved examples
```

## Prioritized capability map

Priority means the proposed order of investment. M is a moderate extension across existing components; L introduces a substantial new subsystem or external integration. These are relative complexity estimates, not delivery dates. Split large items into the smallest working journeys listed below.

| Priority | Capability | First useful version | Dependency and acceptance condition | Size |
|---|---|---|---|---|
| Now | Conversation agent | Discuss ideas, research approved sources, draft artifacts, inspect cases and accept open-ended assignments from the CLI or browser | Scoped tools and resumable conversations. No business pack is required for an ad hoc assignment. External writes still go through the gateway. | L |
| Now | Delegated task execution | Persist an assignment, run it in the background, report progress, accept steering and return a saved result | Independent task identity with an optional case link; budgets, cancellation, restart recovery and observable completion criteria. The conversation stays available. | L |
| Now | Company onboarding beyond a form | Interview the owner about services, hours, language, tone, approval owners and operating rules; import a small set of approved examples | Show inferred settings separately from confirmed ones. Preview the changes and run a synthetic case before activation. | M |
| Now | Operator correction and draft revision | Correct an extracted fact, edit a reply or offer, explain why and regenerate the proposal | Preserve source versus human correction, immutable versions and price validation. An old approval must fail after a material edit. | M |
| Now | One real inbox connector | Select one mailbox, ingest a limited folder or label, correlate replies and create provider drafts | Production identity and secrets boundary, narrow capabilities, deduplication and provider read-back. Choose Gmail or Microsoft 365 according to the first pilot. | L |
| Now | Model accounts and usage | Inspect selected model, credential owner, connection health, configured limits and authentication failures | Use documented supported authentication paths; separate subscriptions from API billing. Expose unknown quota data as unknown. No silent paid fallback. | M |
| Now | Pilot deployment and regression examples | Reproducible single-company install, authenticated operator, separate runtime permissions, backup and restore, representative example cases | Required before real business data. Include negative authorization tests, secret isolation, versioned migrations and recovery checks. | L |
| Next | Company knowledge and documents | Approved price lists, procedures and sample deliverables with cited retrieval; customer context linked to existing records | Source permissions, versions, expiry and explicit conflict handling. Support text first; add document parsing as a scoped increment. | L |
| Next | Inspectable memory | Company facts, customer preferences and case decisions that survive sessions | Source, scope, owner, timestamp and correction history. Imported text cannot automatically become approved policy. | M |
| Next | Business playbooks | Versioned procedure packages with required capabilities, inputs, outputs, examples and tests | On-demand loading; explicit activation. Skills describe the procedure; code enforces action permissions. | M |
| Next | Routines and follow-up commitments | A daily brief and one rule for overdue cases, with timezone, quiet hours and next-run preview | Durable scheduling, deduplication, stop conditions, bounded retries and per-routine budgets. Disabled by default until configured. | M |
| Next | Advanced task coordination | Human or agent handoffs, task dependencies, due dates and escalation across standalone tasks and business cases | Reuse PostgreSQL and Temporal. Surface missed deadlines and uncertain provider outcomes without starting endless retry loops. | M |
| Next | Evaluation and learning from corrections | Record operator edits; propose a playbook change; replay examples; let the owner activate or reject it | Separate draft and active versions. Check authorization, accuracy and cost before activation. Preserve rollback to the previous procedure. | L |
| Later | Bounded specialist agents | Introduce an intake role and a research or preparation role where measured workloads benefit | Explicit tool and knowledge scopes, structured handoffs, concurrency and spend limits. Keep arithmetic and mandatory checks deterministic. | M |
| Later | Team channels and permissions | Notifications in one team channel, then authenticated approvals with links to the exact action | Member identity, revocation, case access and action freshness must work before accepting channel approvals. | L |
| Later | Curated extensions and company bundles | Install a reviewed connector or playbook bundle with declared capabilities and fixtures | Version pinning, permission review, upgrade tests and independent company credentials. No automatic activation of imported executable content. | L |

Core evaluation should start with the first new conversational tools. The later evaluation item adds an operator-facing learning loop; it does not postpone testing until that stage.

## Four delivery milestones

| Milestone | User-visible result | Build sequence | Evidence required to move on |
|---|---|---|---|
| 1. Useful local assistant | “I can talk to Feya, delegate a task and come back to a result.” | Scoped conversation tools → durable standalone tasks and artifacts → approved local knowledge → richer onboarding → fact correction and draft versions → regression examples | Delegate a document comparison without a business pack, keep chatting, restart the worker and recover the result. Test steering, cancellation, missing capabilities and approval bypass attempts. |
| 2. Connected company pilot | “Feya helps with actual enquiries in one mailbox.” | Runtime and identity hardening → account connection → limited inbox ingestion → reply correlation → draft creation and read-back → usage limits | Duplicate events, expired auth, lost write responses and operator edits produce understandable outcomes. A backup restores the workspace. No unattended customer sends. |
| 3. Repeatable operations | “Feya follows our process and remembers useful corrections.” | Playbooks and memory → daily brief and overdue routine → owned tasks and escalation → reviewed learning → a distinct second workflow | Complete a support request through triage, evidence gathering, human escalation and resolution without quote-specific assumptions. Measure operator effort and error rates. |
| 4. Team product | “Several people can delegate and review work consistently.” | Team access → one notification channel → authenticated remote approvals → bounded specialist roles → reviewed bundle installation | Access revocation works; one team's context cannot leak into another's; shared workload and handoffs stay auditable after restarts. |

Basic identity is a milestone 2 prerequisite. Milestone 4 expands the collaboration model; it is not the first time authorization is implemented. Parallel technical spikes can reduce uncertainty, but a later milestone must not bypass an earlier execution boundary.

## The highest value product additions

### A reviewable company handbook

Onboarding should produce a company profile that the owner can inspect and change: services, people, customer promises, tone, working hours, pricing sources, escalation rules and connected systems. Imported websites and documents supply candidate facts. An owner confirms authoritative settings.

Keep a short approved summary in routine context and retrieve detailed material when needed. Hermes documents a similar separation between persistent memory and searchable past sessions, while Letta provides explicit read-only context blocks. Feya can adopt the organization pattern without adding another memory runtime immediately. [Hermes memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory), [Letta memory blocks](https://docs.letta.com/v1-sdk/memory/memory-blocks).

### Learning that an owner can inspect

When an operator repeatedly changes a proposal, Feya should ask whether that correction expresses a reusable rule. For example, “You changed the discovery package description in three proposals. Save this wording in the consulting playbook?” A proposed change includes its examples, expected effect and regression results. Activation is a separate decision.

Hermes skills use progressive loading, and its skill system supports learning from sources. The proposed Feya addition is an explicit business change-management step around learned procedures. The portable Agent Skills format is a useful starting point, but imported instructions do not establish permission to run scripts or call business tools. [Hermes skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills), [Agent Skills specification](https://agentskills.io/specification).

### Visible commitments

An agent saying “I will follow up tomorrow” should create a visible record: what it will check, for which case, when, where the result goes, and when it stops. Operators can pause or cancel it. Start with a daily digest and overdue-case reminders.

Hermes supports scheduled and event-triggered work, including a mode that runs without a model. Feya should likewise use deterministic queries and timers for routine checks, calling a model only when interpretation or drafting is needed. [Hermes scheduling](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron).

### Action receipts and recovery

After an operation, show a compact receipt: requested action, approving person or policy, affected account, provider object, verification time and current outcome. When an outcome is uncertain, offer the appropriate reconciliation path and explain what remains unknown.

This extends Feya's existing verification model into an understandable product feature. Connector-specific compensation may be possible, but an “undo everything” promise would be misleading for sent messages or other irreversible actions.

## Efficiency and integration decisions

Keep one reasoning agent as the default for a delegated task or case. Add a specialist when isolated context, independent research or measured quality gains justify its additional latency and cost. Named roles can share one bounded runtime; every role does not require a separate persistent process. Hermes profiles illustrate persistent role configuration, but profile separation alone is not a production tenant boundary. [Hermes profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles).

Use a small always-present company summary, retrieve only relevant evidence and load playbooks on demand. Preserve deterministic pricing and validation. Use events for incoming changes and ordinary timers for deadlines. Set budgets per case and routine, account for retries, and record quality alongside cost. Model routing should use measured task results rather than an assumption that the cheapest or largest model is always appropriate.

Use MCP selectively for approved retrieval tools. Its connectivity does not prove that a write is authorized, idempotent or verifiable. A business write exposed through MCP or an automation platform still needs a typed Feya intent and a connector with known verification behavior. Hermes itself documents per-server tool filtering and connection setup, useful interaction patterns for `/connect`. [Hermes MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp).

Integrate with existing automation platforms for useful existing flows instead of duplicating their connector catalogs. Keep business-case state and authorization in Feya. Before embedding or redistributing another project's components, review that component's current license and edition; this map does not grant reuse rights.

## What to defer

| Candidate | Why defer it | Evidence that would justify it |
|---|---|---|
| Full CRM | Contact and account references may be enough for the first workflows | Pilot users repeatedly need relationship management that existing connected systems cannot supply |
| Visual workflow canvas | The current weakness is breadth of proven workflows, not a lack of graph editing | Multiple tested playbooks need frequent operator-authored branching |
| Large autonomous agent teams | Extra coordination and model calls can obscure simple work | Same-case evaluations show an improvement in quality or operator time at acceptable cost |
| Public skill marketplace | Discovery adds little before installation, permissions and updates are reliable | A small curated catalog has repeated external adoption and safe upgrade behavior |
| Voice and elaborate pixel effects | Useful personality, but little immediate effect on completion of business work | Users need hands-free operation or a specific accessibility improvement |
| General browser automation | Harder to verify and maintain than a supported business API | A necessary pilot workflow has no viable API; a narrow browser adapter can be tested |
| Broad automatic dispatch | Current evidence establishes local draft workflows | A particular capability has authorization, recovery and operational evidence sufficient for its explicitly configured autonomy level |

## The next implementation backlog

1. **Conversation agent with scoped tools.** Add resumable natural-language sessions, approved source retrieval, artifact drafting and case inspection. Keep explicit CLI commands available. Test ordinary discussion and ad hoc requests without a business pack, inaccessible sources and injected instructions in evidence.
2. **Durable delegated tasks.** Let conversation create an independent assignment with a deliverable and budget. Run it in the background; support progress, steering, cancellation, missing-input waits and restart recovery. Return the actual artifact to the conversation. Prove this with a comparison of supplied documents before adding live web research.
3. **Fact correction and proposal versions.** Let the operator correct an extraction and edit a draft with a reason. Preserve the original observation; invalidate the exact approval when its bound content changes. This makes early pilots correctable.
4. **Company handbook and onboarding interview.** Extend the local setup into a reviewed configuration proposal and a small approved knowledge collection. Include a test enquiry and a visible record of unresolved assumptions.
5. **Connection contract and first mailbox spike.** Establish account identity, allowed operations, auth expiry, event cursor, duplicate handling and read-back. Test in an isolated staging mailbox. Choose the provider from pilot demand before committing to broad integration work.
6. **Pilot runtime boundary.** Complete authentication, least-privilege execution, secret storage and restore checks before onboarding real business data. Run end-to-end examples against the first connector, then expose the connected journey in both interfaces.

## How to judge the roadmap

Use the same synthetic inputs to compare Feya with a configured Hermes workflow and an n8n workflow. Record versions, configuration effort, models, permitted tools and what each implementation had to add. Compare four journeys: a standalone research or document task delegated through conversation, enquiry to reviewed draft, missing-information follow-up, and a response lost after a provider write. Add the distinct support workflow when it exists.

Measure time to first useful draft, operator minutes per completed case, correctness of recipient and amount, evidence quality, recovery from uncertainty, duplicate effects, latency and model cost per verified case. Record subscriptions separately from metered API costs; do not equate subscription usage with zero cost or unlimited capacity. n8n's evaluation documentation supports the general practice of comparing representative datasets across prompts and models. [n8n evaluations](https://docs.n8n.io/advanced-ai/evaluations/overview/).

Set numerical pilot targets after measuring a human baseline and reviewing risk for the chosen workflow. No comparative benchmark, customer interview, independent security audit or subscription-entitlement audit was performed for this map. The main product risk is broadening the agent surface before one connected workflow proves useful to an operator.
