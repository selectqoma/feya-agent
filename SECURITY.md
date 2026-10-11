# Security posture

This checkout is a local synthetic prototype. It must bind to loopback. It is not ready for public deployment, real customer data or production provider credentials.

The model returns structured extraction or conversation steps; it has no shell, MCP, filesystem or provider tools in the PydanticAI runner. The trusted conversation worker accepts only read-only case-list and case-detail tool requests within its tenant. Imported source instructions cannot grant tool permissions. Conversation output is displayed as text, and artifacts download as Markdown; model HTML is not executed. The optional Claude CLI runner disables built-in tools and MCP and receives an allowlisted environment. The worker validates citations and required fields; the gateway separately validates exact recipients, prices, source revision, pack digest and approval. Send, dispatch, delete and payment operations are not implemented. Independent completion review has no tools and cannot grant execution authority. Source quote and arithmetic checks catch some failures; they do not prove that all claims are true or that source material itself is trustworthy.

Local human identity is a fixed development operator. Requests require an exact loopback Host, same-origin browser context and custom write header. This prevents basic cross-site browser requests; it does not authenticate malicious software running on the same machine. Production OIDC, role membership/revocation, authorization-grade DB grants, network egress policies and independent security review are pending.

Audit rows reject UPDATE/DELETE through a PostgreSQL trigger. The development database owner can still change database schema or disable that trigger; this is not a tamper-proof production audit store. Case and evidence references have composite tenant foreign keys, and all service queries are scoped.

Company setup writes `.local/company.yaml` with owner-only permissions and atomic replacement. It requires app processes to be stopped before changing rules; restart all services to load the same pack. This file contains configuration, not credentials, and is excluded from Git. The terminal escapes control characters in displayed source data and uses the same exact-action approval endpoint as the browser.

Reasoning cancellation requires the private service token. Persistent task generation fences reject stale results even if a remote provider continues processing a cancelled request. Lifetime work reservations survive retries and resumption; they are not a provider billing guarantee. Errors expose only typed recovery messages, never remote error bodies.

Model credentials stay outside source control. `.env` is local and mode 0600. No provider error bodies, credentials or message content are written to the run audit. Conversation messages, pasted sources, task results and case evidence are stored in the local PostgreSQL database; encryption, retention/export/deletion beyond case JSON export are not production-ready.

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/selectqoma/feya-agent/security/advisories/new). Include affected commit, reproduction steps with synthetic data, expected and observed behavior, and impact. Do not post vulnerabilities, credentials or customer data in public issues. There is no guaranteed response-time commitment for this experimental project.

Only the current `main` prototype is maintained; there are no supported production releases. Public source availability does not mean the production security gates in the specification have been completed.
