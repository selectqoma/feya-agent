# FEYA 2.0 — Competitive Landscape, Positioning & Benchmark Plan

**Status:** Strategic research and proposed evaluation protocol, not a claim of demonstrated superiority  
**Reviewed:** 2026-10-11  
**Reference implementation:** [selectqoma/feya](https://github.com/selectqoma/feya)  
**Companion:** `02_PRODUCT_TECHNICAL_SPEC.md`

## 0. Executive decision

**Build Feya as a business agent suite that owns routine work from request to result.** The agent plans, chooses tools, executes available operations, checks results and revises its work. Persistent tasks and cases retain the evidence, business context, actions and outcomes. Humans approve critical actions, including sending emails or invoices; the execution gateway enforces that approval and verifies the resulting operation.

The positioning is **“an open-source AI operations teammate for your business”**. More plainly: *Connect your tools, delegate the work, and approve the critical actions.*

Competitive advantage still requires measurement. Hermes already has durable multi-agent Kanban, role delegation, reviews, skills, cron, channels, and profiles. n8n has AI workflows and human review. CrewAI and LangGraph provide stateful workflows. Feya cannot win by saying “we have agents,” “we have approvals,” or “we use Temporal.”

The proposed distinctive combination is: **business objects + source-grounded evidence + independent action authorization + real-provider reconciliation + case-centric operator UI + reusable business packs**, available in the core self-hosted product. No individual ingredient is unique.

## 1. Comparison methodology and limits

Evidence tier **A** = official project repository or documentation; **B** = maintainers’ posts/issues; **C** = third-party commentary. Primary findings below use A wherever possible. Capability assessments refer to documented *product emphasis*, not assertions that competitors cannot implement a feature. Features and licenses change; verify again immediately before public launch. This is a documented desk review, **not** an installation, security audit, performance benchmark, or comparative usability study.

Questions applied to each comparator:

1. What is the product's main unit of work: message, chat, task, graph, workflow, or business case?
2. Does it explicitly support tools, subagents, durable state, and human decisions?
3. Can a nontechnical operator understand which customer/business object is affected and why?
4. Is provider-side authorization independent of the model? Are approvals bound to a specific action/payload?
5. Is there a demonstrable way to verify a real-world effect, reconcile uncertain results, and detect duplicates?
6. How much configuration and domain modeling are necessary for a second, unrelated company?
7. What is the legal and deployment model, especially for third-party multi-tenant hosting?

**Caution:** An unmentioned feature is categorized as *“not established in this review”*, never *“absent.”* Strong competing systems can be customized to implement much of our proposal; Feya must win on out-of-the-box coherence and business outcomes.

## 2. Competitor classes

| Class | Primary competitors | Buyer/developer goal | Implication for Feya |
|---|---|---|---|
| General agents / assistants | Hermes Agent, OpenClaw | Capable agent across channels and tools | Do not reproduce broad personal-agent tooling; treat them as potential execution adapters. |
| Automation / low-code | n8n, Activepieces | Integrate many SaaS apps into flows | Do not compete on connector count or canvas complexity. |
| AI application builders | Dify, Flowise (optional deeper audit) | Build agents, RAG apps and LLM workflows | Differentiate in operational case system of record and verification. |
| Agent/workflow SDKs | LangGraph, CrewAI, PydanticAI, Microsoft Agent Framework | Developers orchestrate agent reasoning and workflow | Use abstractions instead of rewriting generic SDK behavior. |
| Durable execution | Temporal, DBOS, Restate | Infrastructure reliability | These are building blocks, not direct end-user competitors. |
| Commercial business agents | Dust, Lindy, Relevance AI | Business users deploy agents and automations | Benchmark usability and organizational workflow, without equating source availability. |

## 3. Detailed competitor assessments

### 3.1 Hermes Agent (Nous Research) — most important direct *agent-runtime* comparison

**Documented:** Multi-model agent runtime; chat/CLI/messaging channels; 60+ tools; MCP and plugins; memory and adaptive skills; scheduled jobs; subagents; independent agent profiles. Hermes **Kanban** is a durable multi-agent task system with persistent SQLite boards, dependencies, retries, human review/block/unblock, profile workers and audit history. Hermes additionally documents scoped secrets and multi-profile gateway behavior. It is MIT-licensed as shown on the official GitHub repo.

**Real strengths:** broad model/provider support; large ready-made agent surface; low initial friction for a personal or team agent; plugin ecosystem; task-level collaboration and persistence. Its Kanban system is substantial; describing Hermes as “only a chat assistant” would be inaccurate.

**Where Feya could be different:** model **customer/business cases** rather than generic task cards; attach each AI claim to immutable provider evidence; enforce typed business actions through a gateway with authorizations bound to exact payload hashes; perform provider reconciliation and publish a case timeline visible to business staff; package business-specific operating rules and UI. Hermes Kanban's review and audit are not equivalent by default to invoice/quote-specific invariant validation, but an integrator *can build* those atop Hermes. Benchmark this explicitly.

**Threat:** Hermes may expand into organizational workspaces or business actions rapidly. A “more secure Hermes” message is weak because Hermes already develops permission and warrant controls.

**Decision:** Do **not** fork Hermes for the Feya core. A fork inherits fast-changing runtime internals and shifts the roadmap toward competing on general-agent features. Build a clean `AgentRunner` interface; consider Hermes as an optional **restricted reasoning worker** or skill-compatibility adapter after core security tests. No production side-effect credentials go to an untrusted agent runner.

Official sources: [Hermes repository](https://github.com/NousResearch/hermes-agent), [Kanban documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban), [profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles), [tool reference](https://hermes-agent.nousresearch.com/docs/reference/tools-reference/), [multi-profile gateways](https://hermes-agent.nousresearch.com/docs/user-guide/multi-profile-gateways).

### 3.2 OpenClaw — general agent/gateway comparison

**Documented:** Cross-channel assistant, agent-based workspaces, bindings from external channel/account to agents, session histories, sandbox configuration, skills ecosystem. Sandbox modes/scope and agent routing are documented explicitly.

**Strength:** end-user reach, many channels, flexible sandbox and integrations.

**Feya opportunity:** business cases with typed source-of-truth links, explicit operator workspace, account-scoped policy decisions, exact-result verification and financial operation invariants. This is product packaging and an independent control plane, not a claim that OpenClaw cannot be extended.

**Threat:** OpenClaw's ecosystem, business-oriented extensions, and security features may close obvious gaps quickly. Avoid attacking “insecurity” in marketing without comparative security tests.

Official sources: [OpenClaw repository](https://github.com/openclaw/openclaw), [multi-agent routing](https://github.com/openclaw/openclaw/blob/main/docs/concepts/multi-agent.md), [sandbox modes](https://docs.openclaw.ai/gateway/sandboxing/modes-scope-and-backend).

### 3.3 n8n — strongest automation-platform comparison

**Documented:** Visual workflow automation, 400+ app integrations, AI agents, human-in-the-loop for agent tool calls, workflow evaluation features, credential management, self-hosting/cloud. Its published license is *fair-code/Sustainable Use License*, **not equivalent to a standard OSI open-source license**.

**Strength:** huge integration breadth; accessible canvas; broad automation adoption; practical approvals and execution histories.

**Feya opportunity:** do not ask an operator to design a graph. Ship business-native case inbox, preconfigured lifecycle and evidence, customer-specific context, exact action approval and reconciliation. Demonstrate fewer setup steps and less custom glue for an actual multi-day quote/approval flow. This advantage remains hypothetical until measured.

**Threat:** n8n already supports advanced AI workflows and approvals. It can absolutely execute a comparable process with enough nodes. The win must be **time to trustworthy operation**, not possibility.

Official sources: [n8n repository](https://github.com/n8n-io/n8n), [Gmail action documentation with AI tool review](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.gmail/message-operations/), [license](https://docs.n8n.io/sustainable-use-license).

### 3.4 Activepieces — open-core automation comparison

**Documented:** Automation platform with AI agents, MCP, workflow actions and connectors. Community core is MIT; designated enterprise directories are commercially licensed, according to the official license files.

**Strength:** permissive core, broad action/connectivity ecosystem, adoption of AI/MCP.

**Feya opportunity:** case-centric operations, evidence-backed changes, business packs, first-class reconciliation and operator accountability. Avoid reproducing a comparable visual low-code editor in v1.

**Threat:** strong base to add business templates and team workflows. Licensing distinction alone is not a product moat.

Official sources: [Activepieces repo](https://github.com/activepieces/activepieces), [license explanation](https://github.com/activepieces/activepieces/blob/main/docs/about/license.mdx), [license file](https://github.com/activepieces/activepieces/blob/main/LICENSE).

### 3.5 Dify — AI application/workflow comparison

**Documented:** Collaborative AI workflow and agentic-application building with RAG, models, tools and self-hosting. Its repository license includes additional conditions beyond Apache-2.0, including limitations on certain multi-tenant uses; read the *current* license before use or adaptation. Calling it unrestricted Apache-2.0 would be misleading.

**Strength:** low-code application building, RAG, agent tooling, product UI, deployment choices.

**Feya opportunity:** not a general AI-app studio. Focus on persistent external business cases and safe operations. A quote, customer reply or ticket update is a tracked domain artifact with verified provider status, not simply the last answer from a workflow.

**Threat:** feature overlap is high, and Dify can be extended with external application code. Compare out-of-box operator workflow and license carefully.

Official sources: [Dify repo](https://github.com/langgenius/dify), [license](https://github.com/langgenius/dify/blob/main/LICENSE), [license discussion by maintainer](https://github.com/langgenius/dify/issues/14264).

### 3.6 LangGraph — developer SDK/workflow comparison

**Documented:** Stateful agent graphs, checkpoint persistence, pause/interrupt for human input, resumption, and workflow orchestration. MIT-licensed library.

**Strength:** flexible agent control flow and established ecosystem. **Do not claim LangGraph lacks durability or human-in-the-loop**; it clearly provides both.

**Feya opportunity:** Feya would be a prebuilt application/business platform, including policy gateway, provider reconciliation, tenant and case data, operator experience. LangGraph could even power an optional agent runtime; it need not be opposed.

Official sources: [LangGraph repository](https://github.com/langchain-ai/langgraph), [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

### 3.7 CrewAI — developer agent teams/workflows comparison

**Documented:** Crews of agents, event-driven Flows, structured state, routing, persistence/checkpointing and human feedback facilities. MIT-licensed core.

**Strength:** accessible role-based multi-agent composition with mature developer-facing concepts.

**Feya opportunity:** avoid selling “role-based agents” as innovation. Provide fully specified business cases, enforceable provider action controls, evidence lifecycle, business-wide audit, and operator workflows.

Official sources: [CrewAI repository](https://github.com/crewAIInc/crewAI), [Flows](https://docs.crewai.com/en/concepts/flows).

### 3.8 PydanticAI + Temporal — proposed infrastructure, not differentiators

PydanticAI supports typed tool interfaces, structured agent outputs and durable-execution integrations. Temporal provides durable workflows and activities. Their combination reduces generic framework code, but **“uses Temporal/PydanticAI” is not a product advantage**. PydanticAI now has a native Temporal durability capability; prevent accidental *double* wrapping of the same model call when composing inner and outer workflows.

Official sources: [PydanticAI durability](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/), [Temporal integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/), [Temporal Python developer guide](https://docs.temporal.io/develop/python).

### 3.9 Microsoft Agent Framework and other enterprise SDKs

A framework for Python/.NET AI agents and multi-agent workflows. It is a viable enterprise implementation choice, not an end-user business-case product. Reevaluate if target customers disproportionately use Microsoft 365 and Azure. Do not write an internal abstraction layer around five SDKs on day one.

Official source: [Microsoft Agent Framework](https://github.com/microsoft/agent-framework).

### 3.10 Commercial agents (Dust, Lindy, Relevance AI)

Include in **user-experience, adoption and workflow evaluations**, but treat them as a separate class from OSS code bases. Test how fast a nontechnical team can connect services, create a task, understand what happened, review an action, and troubleshoot. No licensing or feature-parity assertions are made here without installing and testing the current versions.

Official entry points for the next hands-on audit: [Dust](https://dust.tt/), [Lindy](https://www.lindy.ai/), [Relevance AI](https://relevanceai.com/).

## 4. Competitive matrix: observed product emphasis, not absence claims

Legend: **Primary** = defining product abstraction; **Supported** = documented substantial capability; **Custom** = generally composed by application developer; **Proposed** = intended Feya requirement (not shipped today); **Review** = implementation-specific; hands-on audit needed.

| Platform | Primary organizing abstraction | Multi-agent/workflow | Human review | External business-action policy | Case and provider reconciliation |
|---|---|---|---|---|---|
| Hermes | Assistant + durable Kanban tasks | Supported, substantial | Supported in Kanban | Tool/warrant/plugin model; assess exact deployment | Business case semantics custom |
| OpenClaw | Agent + gateway sessions | Supported | Varies by tool/runtime | Sandbox/tool policies; assess exact deployment | Business case semantics custom |
| n8n | Automation workflow graph | Primary | Supported incl. AI tool review | Node/credential/workflow configuration | Custom workflow/application modeling |
| Activepieces | Automation flow | Primary | Supported/configurable, verify edition | Connectors/flow administration | Custom business application modeling |
| Dify | AI application/workflow | Primary | Depends on workflow/edition; verify | Configurable tools/permissions; audit needed | Custom business application modeling |
| LangGraph | Stateful agent graph | Primary | Supported via interrupts | Application-defined | Application-defined |
| CrewAI | Agent crews and Flows | Primary | Supported | Application-defined | Application-defined |
| Feya 2.0 target | **Business case** | Workflow + bounded solo runner | **Mandatory business action inbox** | **Independent gateway, exact payload binding** | **First-class verified outcomes** |

This matrix does **not** establish that Feya is better. It identifies a product thesis to test. The strongest competing approach may be *n8n + CRM + careful gates* or *Hermes Kanban + business plugin*, not just either tool out of the box.

## 5. Three strategic approaches we could take

| Option | Benefits | Risks | Recommendation |
|---|---|---|---|
| **A. Hermes plugin/extension** | Fastest reuse of generic agent/messaging capabilities, established community | Feya becomes dependent on Hermes execution conventions; business policy isolation and case UX still custom | Prototype as a benchmark; keep as optional adapter |
| **B. Fork Hermes** | Immediate generic runtime | Large upstream rebase burden; dilutes business focus; hard to guarantee shared agent/tool boundary changes | **Reject** |
| **C. Independent case platform built on libraries** | Clear business abstraction; independent policy boundary; replaceable agent engine; API-first | More code and slower initial development than a plugin | **Preferred**, contingent on tests |

A fourth approach worth evaluating is **n8n orchestrations with a Feya case/policy service**, but Feya would become a product extension and inherit n8n deployment/licensing constraints. Use it as a competitor baseline and potentially as a trigger source via API/webhooks.

## 6. What could constitute a genuine advantage?

**Claim A: Business-case UX.** Unlike generic chats or task cards, every case shows its customer/business entity, stage, relevant provider records, missing facts, money/date impact, next action, owner, and evidence. Design goal: an office operator can manage work without inspecting prompts or JSON.

**Claim B: Evidence-grounded operations.** Every consequential decision refers to immutable, scoped source observations (e.g. Gmail message ID, Billit order version, Calendar event version). A model-generated claim without supporting evidence cannot satisfy a hard policy prerequisite.

**Claim C: Business-action transaction lifecycle.** Every attempted mutation passes through *propose → policy evaluate → optionally human approve exact payload → execute using narrow credentials → read-back verify → reconcile uncertain outcomes*. No direct agent egress to provider write APIs. This must be demonstrated by bypass tests, not marketing.

**Claim D: Business packs.** Company-independent engine + installable vertical packs (moving, field service, consulting/proposal operations, support). Packs include data schema extensions, intake criteria, policy defaults, prompt definitions, artifact templates, workflow definitions, replay fixtures, and tests. Configured business capability is more valuable than yet another skill prompt.

**Claim E: Measurable improvement.** A built-in case evaluation harness grades correct extraction, safe action behavior, quote/invoice accuracy, duplication, completion and operating cost. Customers can see what Feya actually did and whether it was verified.

**What is not a moat:** LLM choice, the size of a plugin list, having a Kanban board, an attractive graph canvas, supporting MCP, basic approval flows, or using a fashionable durable execution SDK.

## 7. Target user and beachhead

**Primary buyer/operator:** owner or operations manager of a service business with repeated inbound enquiries and document/schedule/accounting work. **Primary implementer:** technical operator/developer/consultant configuring a repeatable business process. **Primary user:** office staff who need a case queue, clear drafts, controlled approvals and visible progress.

**Initial wedge:** inbound enquiry → missing-info follow-up → accurate service proposal/quote draft → operator review → status tracking → booking handoff. Begin with moving services, prove portability with a structurally different consulting/proposal workflow. Do not claim generic support for every vertical at launch.

**Non-target:** open-ended personal assistants, research-only chat, code execution agents, broad robotics/browser desktop control, general CRM replacement, arbitrarily programmable low-code platforms.

## 8. Fair comparison bake-off: prerequisite before public positioning

Benchmark **Hermes (including Kanban)**, **n8n**, **Dify**, **CrewAI/LangGraph reference builds**, and Feya. Activepieces is a useful supplemental flow builder; OpenClaw is a useful supplemental general assistant. Compare self-hosted current tagged versions, record commits, dated feature descriptions and edition/license. Use controlled synthetic businesses and separate test provider accounts. Never run these experiments on real customer mailboxes.

### 8.1 Three evaluation tracks

- **T1: Out of box.** What can be done with documented installation, first-party features and simple configuration? Record setup effort.
- **T2: Reasonable integration.** Allow the same reference data, model, tools and up to a fixed implementation budget. Record all custom code/prompt nodes required.
- **T3: Hardened deployment.** Inject faults/attacks; verify that unauthorized writes and duplicates are prevented. Record compensating custom components needed by each platform.

Separating tracks avoids the dishonest comparison where we spend months hardening Feya but give competitors an afternoon of setup.

### 8.2 Controlled dataset

Use at minimum (starting targets, revise by statistical power):

| Dataset | Suggested cases | Required variation |
|---|---:|---|
| Enquiry / triage | 200 | multilingual, irrelevant, duplicate, ambiguous participants, missing dates, long threads |
| Quotes / proposals | 100 | incorrect rates, missing photos, unsupported pricing, mismatched address, taxes |
| Approval + action | 100 | approval/edit/reject/expire; changed payload; double click; unauthorized approver |
| Provider failure | 75 | timeouts before/after commit, lost responses, duplicate webhooks, partial read-back |
| Adversarial input | 100 | prompt injection in email/PDF, fabricated approval, cross-tenant references, forged tool outputs |
| Portability | 30 | moving → consulting, with different tools and pricing policies |

All prompts/fixtures must be synthetic or explicitly licensed and deidentified. Include reference expected outcomes and human adjudication of ambiguous cases.

### 8.3 Metrics and release thresholds

| Metric | Definition | Proposed release gate |
|---|---|---|
| Unauthorized mutation count | Provider-side writes without required permission in adversarial tests | **0**, required (also for Feya solo mode) |
| Duplicate consequential action | Two external mutations for same logical intent | **0** in tested fault suite; ambiguous cases flagged, not retried blindly |
| Source/recipient correctness | Exact entity, recipient and evidence matching | **100%** in high-risk test suite |
| Incorrect financial artifact | Unapproved/incorrect price or tax in provider artifact | **0** in evaluated standard supported price cases |
| Stale decision acceptance | Changes to provider facts after approval still executed | **0** in evaluated race tests |
| Verified completion | “Done” backed by source read-back or explicitly marked unverified | **100%** of consequential actions |
| Portability | Second vertical deployed without changes to core engine | **Pass** |
| Tenant data isolation | Cross-tenant read/write attempts blocked | **100%** in isolation suite |
| Operator effort | Minutes and clicks to achieve safe case resolution | Beat at least one comparable configured baseline; publish actual results |
| End-to-end completion | Cases completed correctly with controlled intervention | Aim for ≥20% relative gain vs best practical baseline, or revise positioning |
| Cost per verified case | LLM + hosted execution + operator review time | Report distribution; do not optimize cost by dropping gates |

The 20% superiority figure is a **proposed go/no-go target**, not an observed result. Report confidence intervals and failures; don't cherry-pick easy scenarios. If competitors match or beat Feya at the same risk and cost, narrow the vertical or switch to an extension strategy.

### 8.4 Benchmark setup fairness

- Pin same foundation model, temperature where supported, token limit and source data; report provider/runtime differences.
- Provide equivalent tool permissions and test fixtures; report all custom wrapper code.
- Do not use real external sends; use simulated services and one isolated staging integration.
- Include source citations in each run report: repository tag and docs URL.
- Two reviewers independently grade ambiguous outputs; adjudicate disagreements.
- Record installation instructions, total human build/configuration hours, runtime cost, LLM input/output cost, end-to-end case latency and retries.
- Blind review output artifacts where possible; then score operator UX separately.
- Include adversarial tests for the same policies on all contenders.

## 9. Strategic stop/go gates

**Before committing to architecture:** Build two thin prototypes: (1) Hermes Kanban + proposed case/policy plugin, (2) independent Python `Case/Action/Gateway` vertical slice. Measure implementation effort and bypass resistance.

**Before expanding beyond moving:** A second business pack must run with no hardcoded moving-company assumptions in the core.

**Before claiming an advantage:** Reproduce T1–T3 results and publish honest comparison, including where competitors win. If advantage comes only from extensive custom glue, be clear that our product packages that glue coherently.

**Before open sourcing:** License/rights, history hygiene, source secrets/PII review, threat model and penetration review, tests, developer docs, reproducible build, governance and legal permission for all included examples.

## 10. Open-source position

Recommend **Apache-2.0** for the *new, cleanly extracted core*, subject to a contributor-rights and dependency-license review. Keep business-policy enforcement, approval workflows, adapter API, case engine, evidence, audit and evaluations in the freely usable core; a “free demo, paid safety” strategy undermines trust. Commercial services can offer hosted operations, support and verified proprietary provider integrations without weakening OSS safety.

**Important baseline observation:** `selectqoma/feya` is public today, but the source review did not identify a root `LICENSE` file. Public visibility is not an OSI open-source grant. It also contains historically tracked client/deployment material. Do not attach an OSS license to the existing repository and declare it safe. Extract a clean core into a separate repo after reviewing both current tree and git history; preserve internal deployment secrets and rotate any credentials exposed. An incident/security audit, not a README change, is the release prerequisite.

## 11. Sources used for this desk review

- [Hermes official repository](https://github.com/NousResearch/hermes-agent)
- [Hermes Kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)
- [Hermes multi-profile routing](https://hermes-agent.nousresearch.com/docs/user-guide/multi-profile-gateways)
- [OpenClaw official repository](https://github.com/openclaw/openclaw)
- [OpenClaw sandbox](https://docs.openclaw.ai/gateway/sandboxing/modes-scope-and-backend)
- [n8n official repository](https://github.com/n8n-io/n8n)
- [n8n Gmail human tool review](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.gmail/message-operations/)
- [n8n license](https://docs.n8n.io/sustainable-use-license)
- [Activepieces license](https://github.com/activepieces/activepieces/blob/main/LICENSE)
- [Dify official repo](https://github.com/langgenius/dify)
- [Dify license](https://github.com/langgenius/dify/blob/main/LICENSE)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [CrewAI Flows](https://docs.crewai.com/en/concepts/flows)
- [PydanticAI durability](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/)
- [Temporal Python SDK](https://docs.temporal.io/develop/python)
- [Feya source](https://github.com/selectqoma/feya)

**Research confidence:** High for source-documented feature existence and project focus; medium for inferred competitive whitespace; low until hands-on benchmarking for actual superiority, time-to-value, reliability and operating cost.
