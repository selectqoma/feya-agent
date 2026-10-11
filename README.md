# Feya Agent

<img src="apps/console/src/feya-wordmark.svg" width="208" height="72" alt="Feya pixel wordmark"/>

[![Checks](https://github.com/selectqoma/feya-agent/actions/workflows/check.yml/badge.svg)](https://github.com/selectqoma/feya-agent/actions/workflows/check.yml)

A local business assistant you can talk to, delegate work to, and use to manage evidence-linked customer cases. Feya saves conversations, runs bounded background assignments, and returns reports and drafts to the same workspace.

**Experimental business operations workspace with a bounded agent engine.** The current prototype demonstrates enquiry-to-quote workflows using simulated email and accounting providers. It is not a full CRM or a production deployment.

The agent extracts source-grounded facts; deterministic application code calculates prices and controls approvals; the execution gateway verifies provider results. Business packs configure required facts and rates. Two packs demonstrate reuse of this workflow; unrelated workflows still require implementation.

Read the [architecture](docs/ARCHITECTURE.md), [implementation status and roadmap](docs/BUILD_STATUS.md), or original [research and specification](docs/research/00_START_HERE.md). The specification describes the intended product, including features not yet built.

## Start locally

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+, Docker with Compose.

```sh
git clone https://github.com/selectqoma/feya-agent.git
cd feya-agent
uv sync --locked --python 3.12
uv run feya init --demo
uv run feya up
uv run feya doctor
uv run feya demo
```

Open **http://127.0.0.1:8010**. Temporal's local UI is at **http://127.0.0.1:58233**.

`feya up` starts PostgreSQL and a persistent Temporal dev server, applies the migration, builds the React console, then starts the API, bounded reasoning process, execution gateway, and workflow worker. All host ports bind to loopback. `.env`, process IDs, logs and runtime data are ignored by Git. No external business-provider credentials are required. Default model: deterministic offline fixture parser.

```sh
uv run feya down       # stops application processes; preserves all data
uv run feya up         # resumes existing cases and workflows
uv run feya pack validate packs
```

If Docker Desktop's credential helper stalls while pulling public images, unlock or repair its keychain configuration. `feya up --skip-infra` starts the application when PostgreSQL and Temporal are already running at the configured addresses. Inspect `.local/*.log` when `feya doctor` reports a failure.

`feya down` leaves infrastructure running. To stop it without deleting data, run `docker compose -f deploy/compose.yaml stop`. After changing frontend code, run `npm --prefix apps/console run build`; startup reuses an existing build. The quickstart uses host processes and Unix utilities; Windows users should use a Linux environment such as WSL2.

## Operate from the terminal

Run `uv run feya` in an interactive terminal to open the pixel-wordmark command shell. Existing one-shot commands remain available; `uv run feya --help` lists them. Tab completes slash commands, `NO_COLOR=1` disables color, and the interface has no animations or saved command history.

```text
/setup                 Configure your company (alias: /onboard)
/up                    Start local services
/demo                  Create a synthetic case using the company pack
/cases                 Find the case ID and current status
/case CASE_ID          Inspect the case and its evidence
/reply CASE_ID         Simulate the customer's missing information
/approve CASE_ID       Review the exact offer, then confirm and explain
/case CASE_ID          Check the verified outcome
/exit                  Leave the shell; services keep running
```

Use `/down` before `/setup` if the app is already running. Setup asks for a company name, one of the two workflow templates, currency, tax fraction and service prices. It previews the settings before saving. The file `.local/company.yaml` is private to the local user and ignored by Git; it contains no credentials. The browser shows the company name and offers its pack when creating an enquiry. `/demo` defaults to this pack.

Re-running setup edits the same company pack; changed rules invalidate its pending proposals. Start all services again with `/up`. Built-in demo packs and existing cases remain available. This configures one existing local workspace, not separate production tenants. Template facts and service names currently come from the selected pack; model-account selection remains in `.env` as described below.

The shell also supports `/reject CASE_ID`, `/recheck ACTION_ID`, `/status`, and `/help`. Every approval uses the same exact-action digest and server validation as the browser. An accepted decision is not a claim of successful execution; inspect the case for provider verification. Type ordinary text to chat or delegate an assignment. The shell waits briefly for the reply, then returns control; `/messages` retrieves later replies and `/work` shows background tasks.

## Talk to Feya and delegate work

The browser opens in **Conversation**. Add source material, then ask, “Compare these supplier proposals and recommend one.” Feya can answer directly or create an independent background task with an objective and deliverable. Keep chatting while it runs. Delegation records concrete acceptance criteria. A candidate report is saved, then reviewed in a separate model call and checked by code before it becomes **Draft prepared**. Task details show the criteria, checks, remaining work budget, missing input and saved results; use **Update task**, **Cancel task**, or **Resume** for paused or failed work. Replies and draft previews render headings, lists, tables and code. Source citations display readable titles and open their source material. Completed results download as Markdown. Cancellation is terminal; delegate a new task to start again.

The same work is available from the terminal:

```text
/new Supplier comparison
/source ./supplier-notes.txt
Compare the supplied proposals and prepare a recommendation with sources.
/messages
/work
/task TASK_ID
/steer TASK_ID "Prioritize delivery time over price."
/resume TASK_ID                    # retry a saved draft review after a temporary failure
/resume TASK_ID "Use the source I just added."
/cancel TASK_ID
/conversations
/use CONVERSATION_ID
```

One-shot chat: `uv run feya ask "What can you help with?"`. `/source` reads only the text file you explicitly name. The selected conversation and pending message ID are stored under ignored `.local`; PostgreSQL stores the conversation itself. Closing a browser or terminal does not cancel work. Restarting the worker resumes committed assignments.

This version has two read-only case tools and operator-supplied text sources. It cannot browse the web, inspect arbitrary files, send messages or execute provider actions from chat. Sources and history are context, never authority. Source IDs, quoted excerpts and reported arithmetic are checked. A separate model review checks the acceptance criteria and unsupported claims. This can still miss errors or reject valid analysis; generated drafts need your review and never imply an external action was performed. Substantive review failures are sent back to the authoring agent for revision and another review when two calls remain in the current budget. Exact excerpt matching is advisory, so a paraphrase or formatting mismatch alone does not block a useful draft; review notes stay visible. Unresolved failures preserve the candidate. Business actions still require the existing case/gateway path. Each task generation has at most four reasoning requests. Across steering and resumption, a task retains a lifetime limit of 12 calls, 420,000 reserved tokens and 1,080 reserved active seconds; review uses the same budget. Interrupted requests retain their reservation and may show unknown usage. The supported API adapters disable SDK HTTP retries so the durable worker owns backoff. These remain application-level work limits, not an account spending cap: provider authentication refresh and Claude CLI internals are outside that guarantee. A conversation accepts at most eight text sources totalling 14,000 UTF-8 bytes including metadata; individual sources are capped at 12,000 characters. Context limits are explicit, and work that cannot fit asks for shorter input. There is no automatic billing fallback.

Rate limits, timeouts and temporary outages retry with persisted backoff while budget remains. Authentication, malformed output and context failures pause or fail with a specific recovery message. Cancellation actively interrupts the local model request; already incurred provider usage may still count. `/resume TASK_ID` without new instructions can retry an interrupted review or let the agent repair a rejected candidate using its saved feedback; new instructions revise the task.

The offline fixture demonstrates delegation and recovery but returns labelled source excerpts rather than authored analysis. Select a live model below for substantive conversations and deliverables. This is the first conversation/delegation slice of the [product development map](docs/research/03_PRODUCT_DEVELOPMENT_MAP.md), not the entire roadmap.

## Try the complete journey

1. Open a case, or choose **New enquiry → Use the example message**.
2. Feya identifies missing facts and saves a verified reply draft in the email simulator.
3. Open the case and click **Simulate the customer's reply**. The same case resumes.
4. Inspect the calculated offer, exact customer, required facts and sources.
5. Choose **Approve draft**. The gateway consumes one exact, expiring approval; the accounting simulator creates an undispatched offer; the verifier reads it back.
6. For the failure path, choose **Try a simulated provider failure → Create offer, then lose the response** before approving. The case becomes **Needs verification**. **Recheck provider** finds the existing object, verifies it, and completes without writing a duplicate.

There is no send/dispatch/payment API. Manual completion remains explicitly labelled; it does not claim a provider effect was verified. The two packs (service enquiries and consulting proposals) run the same core.

## Model accounts and subscriptions

Configure `.env`, then restart the application. Never put keys in packs, source files or the browser. No runner silently switches to a different billing provider.

### ChatGPT / Codex subscription

```sh
codex login
```

```dotenv
FEYA_RUNNER=pydantic-ai
FEYA_MODEL=openai-codex:gpt-5.6-luna
```

PydanticAI's Codex provider uses the installed account owner's Codex login. A synthetic live smoke test succeeded on this machine. Select another model only if your account supports it. The provider reads the CLI auth store; no credentials are copied into this repository. If login expires, re-authenticate with the account owner's CLI. Do not treat a personal login as a pooled, multi-company backend.

Sources checked 11 October 2026: [OpenAI authentication](https://learn.chatgpt.com/docs/auth), [PydanticAI Codex provider](https://pydantic.dev/docs/ai/models/openai-codex/).

### Claude subscription

```sh
claude    # sign in with your own eligible account
```

```dotenv
FEYA_RUNNER=claude-subscription
FEYA_MODEL=haiku
```

Uses the official `claude -p` interface with no built-in tools or MCP servers, no saved conversation, a temporary working directory, a bounded deadline, structured output, and a sanitized environment. API keys and gateway/database credentials are not inherited. The local CLI was installed but **not logged in**, so a live Claude inference was not verified. The adapter fails closed rather than changing billing.

[Anthropic's current account guidance](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan) describes subscription usage for the SDK/CLI; availability and terms are account-specific. Customer-owned credentials are required for any future customer deployment.

### Provider API or offline mode

```dotenv
FEYA_RUNNER=pydantic-ai
FEYA_MODEL=anthropic:YOUR_MODEL
ANTHROPIC_API_KEY=YOUR_KEY
```

Alternatively use `openai:YOUR_MODEL` and `OPENAI_API_KEY`. These are separate API billing options, explicitly selected. API-key inference was not exercised in this build.

```dotenv
FEYA_RUNNER=fixture
```

The fixture runner extracts explicit `key: value` lines only. It is labelled as an offline parser, not a language model. Live model output must cite source text; missing, unsupported or malformed facts stay missing. Money calculations, policy and read-back never depend on model arithmetic.

## Verify

Start the infrastructure and apply migrations first (`feya up` does both).

```sh
uv run ruff check src tests scripts
uv run mypy src/feya
uv run pytest -q
uv run python scripts/evaluate_conversation.py
npm --prefix apps/console run build
uv run playwright install chromium
uv run python scripts/browser_check.py
uv run python scripts/recovery_check.py
uv run python scripts/conversation_browser_check.py
uv run python scripts/work_recovery_check.py
```

The case browser and recovery scripts create **synthetic demo cases** in the local workspace. The conversation browser check uses route fixtures. The work recovery check requires `FEYA_RUNNER=fixture` and creates a synthetic conversation, stops only this checkout’s worker, resumes a task while it is stopped, and verifies replay after restart. The recovery script deliberately kills only this checkout's worker, approves while it is stopped, restarts it, and re-delivers outbox events. Core tests use unique test tenants and never delete the demo's data. `FEYA_TEST_DATABASE_URL` can select a separate test PostgreSQL database after applying the migration there.

The offline evaluation calibrates 24 scenario contracts and counterexamples; it is **not a model-quality score**. To test the configured model explicitly, run `uv run python scripts/evaluate_conversation.py --live --scenario supplier_arithmetic --scenario injected_send --scenario unavailable_web`. This consumes account allowance or API budget, stays within an explicit request cap, and writes model/prompt hashes, latency, usage and failures to ignored `.local/evals/`. It does not execute real tools or certify factual accuracy.

Coverage includes completion checks, persistent retry/cancellation and lifetime budgets, plus concurrent duplicate ingestion/commits, exact approval binding, expiry, stale evidence, tenant references, prompt-injection proposals, wrong recipients/rates, manual handling, read-back differences, lost responses and second-pack portability. See [`docs/BUILD_STATUS.md`](docs/BUILD_STATUS.md) for observed results and limits.

## Layout

- `src/feya/domain.py`, `packs.py`, `policy.py`: contracts, state transitions, deterministic business rules.
- `service.py`, `db.py`, `migrations/`: business state, evidence, append-only audit, transactional outbox.
- `workflows.py`, `worker.py`: outer Temporal workflow and activities; reasoning is not doubly wrapped in a second durable runtime.
- `agents.py`, `conversation_agent.py`: bounded reasoning and explicit provider adapters; tool requests are structured proposals.
- `work.py`, `work_db.py`, `conversation_models.py`: saved conversations, standalone tasks, bounded read-only tools and Markdown results.
- `gateway.py`: exact action authorization, attempt journal, simulated providers and independent read-back.
- `api.py`, `apps/console/`: local operator workspace.
- `packs/`: independent synthetic service and consulting packs.
- `deploy/compose.yaml`: isolated local PostgreSQL and persistent Temporal dev server.

## Boundaries and next work

This is an intentionally **single-workspace, loopback-only, synthetic prototype**. The local operator identity is explicit development identity, not production authentication. The database role is a local development role; process separation is not a hardened container/IAM boundary. Real Gmail/Billit/Calendar connectors, OIDC, production DB grants/egress isolation, PDF/office attachments, web research, long-term memory, policy rollout, draft editing/versioning, full competitor bake-off, and release packaging remain pending.

Do not expose this API publicly or attach customer credentials to the fake providers. Publishing the source does not establish production readiness. Application services, credentials and runtime data remain local.

## Contributing, security and licensing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development checks and [SECURITY.md](SECURITY.md) for limitations and private vulnerability reporting.

No open-source license has been granted yet. Apache-2.0 is proposed in the research and awaits the owner's decision. Public visibility alone does not grant permission to redistribute or modify the source. Dependencies retain their own licenses.
