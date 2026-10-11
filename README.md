# Feya Agent

<img src="apps/console/src/feya-wordmark.svg" width="208" height="72" alt="Feya pixel wordmark"/>

[![Checks](https://github.com/selectqoma/feya-agent/actions/workflows/check.yml/badge.svg)](https://github.com/selectqoma/feya-agent/actions/workflows/check.yml)

A local workspace for business conversations, background assignments and customer cases. You can add text sources, ask for reports or drafts, and review the results in a browser or terminal.

The enquiry-to-quote demo collects missing facts, calculates a price and asks for approval before creating a simulated offer. Email and accounting providers are simulators; real sending, invoicing and payments are not implemented.

## Start locally

Requires Python 3.12+, `uv`, Node.js 20+ and Docker Compose. Use a Unix environment or WSL2.

```sh
uv sync --locked --python 3.12
uv run feya init --demo
uv run feya up
uv run feya doctor
uv run feya demo
```

Open http://127.0.0.1:8010. Startup launches PostgreSQL, Temporal and the application processes, applies migrations and builds the console if needed. The default runner is an offline fixture parser; no model credentials are required for the demo.

Run `uv run feya` for the interactive terminal or `uv run feya --help` for commands. In the terminal, `/setup` configures a company, `/source ./notes.txt` adds source text, and `/work` lists background assignments. In the browser, start with **Conversation** or open the demo case to try the approval flow.

## Use a model

Edit `.env` and restart the application. For an API-backed model:

```dotenv
FEYA_RUNNER=pydantic-ai
FEYA_MODEL=anthropic:YOUR_MODEL
ANTHROPIC_API_KEY=YOUR_KEY
```

The adapter also accepts `openai:YOUR_MODEL` with `OPENAI_API_KEY`, or `openai-codex:YOUR_MODEL` with the local account owner's Codex login. The Claude CLI adapter uses `FEYA_RUNNER=claude-subscription` and `FEYA_MODEL=haiku` with an authenticated `claude` CLI. Account access and model availability determine which options work. There is no automatic billing fallback.

Chat tools are read-only and use supplied text and case data. They cannot browse, inspect arbitrary files or perform external actions. Background tasks have persisted work limits, retry handling and cancellation; those limits are not an account spending cap. Review generated drafts before using them.

## Stop and develop

```sh
uv run feya down
# Stop infrastructure too, preserving data:
docker compose -f deploy/compose.yaml stop
```

`feya down` stops application processes but leaves PostgreSQL and Temporal running. After frontend changes, rebuild with `npm --prefix apps/console run build`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for checks, [architecture](docs/ARCHITECTURE.md) for the design, and [build status](docs/BUILD_STATUS.md) for implemented features and known gaps. Runtime data and credentials stay in ignored local files.

This is a single-workspace prototype with development authentication. Keep it on loopback; do not expose the API publicly or attach customer credentials to the simulators. See [SECURITY.md](SECURITY.md).

No open-source license has been granted. Public visibility alone does not grant permission to redistribute or modify the source.
