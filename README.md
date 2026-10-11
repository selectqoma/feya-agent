# Feya Agent

[![Checks](https://github.com/selectqoma/feya-agent/actions/workflows/check.yml/badge.svg)](https://github.com/selectqoma/feya-agent/actions/workflows/check.yml)

A local business workspace that turns customer enquiries into evidence-linked cases, prepares replies and offers, and verifies provider outcomes before calling the work complete.

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
npm --prefix apps/console run build
uv run playwright install chromium
uv run python scripts/browser_check.py
uv run python scripts/recovery_check.py
```

The last two scripts create **synthetic demo cases** in the local workspace. The recovery script deliberately kills only this checkout's worker, approves while it is stopped, restarts it, and re-delivers outbox events. Core tests use unique test tenants and never delete the demo's data. `FEYA_TEST_DATABASE_URL` can select a separate test PostgreSQL database after applying the migration there.

Coverage includes concurrent duplicate ingestion/commits, exact approval binding, expiry, stale evidence, tenant references, prompt-injection proposals, wrong recipients/rates, manual handling, read-back differences, lost responses and second-pack portability. See [`docs/BUILD_STATUS.md`](docs/BUILD_STATUS.md) for observed results and limits.

## Layout

- `src/feya/domain.py`, `packs.py`, `policy.py`: contracts, state transitions, deterministic business rules.
- `service.py`, `db.py`, `migrations/`: business state, evidence, append-only audit, transactional outbox.
- `workflows.py`, `worker.py`: outer Temporal workflow and activities; reasoning is not doubly wrapped in a second durable runtime.
- `agents.py`: bounded, tool-free reasoning process and explicit provider adapters.
- `gateway.py`: exact action authorization, attempt journal, simulated providers and independent read-back.
- `api.py`, `apps/console/`: local operator workspace.
- `packs/`: independent synthetic service and consulting packs.
- `deploy/compose.yaml`: isolated local PostgreSQL and persistent Temporal dev server.

## Boundaries and next work

This is an intentionally **single-workspace, loopback-only, synthetic prototype**. The local operator identity is explicit development identity, not production authentication. The database role is a local development role; process separation is not a hardened container/IAM boundary. Real Gmail/Billit/Calendar connectors, OIDC, production DB grants/egress isolation, attachments, policy rollout, generalist chat, draft editing/versioning, full competitor bake-off, and release packaging remain pending.

Do not expose this API publicly or attach customer credentials to the fake providers. Publishing the source does not establish production readiness. Application services, credentials and runtime data remain local.

## Contributing, security and licensing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development checks and [SECURITY.md](SECURITY.md) for limitations and private vulnerability reporting.

No open-source license has been granted yet. Apache-2.0 is proposed in the research and awaits the owner's decision. Public visibility alone does not grant permission to redistribute or modify the source. Dependencies retain their own licenses.
