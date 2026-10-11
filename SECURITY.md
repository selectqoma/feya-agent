# Security posture

This checkout is a local synthetic prototype. It must bind to loopback. It is not ready for public deployment, real customer data or production provider credentials.

The model can return structured extraction only; it has no shell, MCP, filesystem or provider tools in the PydanticAI runner. The optional Claude CLI runner disables built-in tools and MCP and receives an allowlisted environment. The worker validates citations and required fields; the gateway separately validates exact recipients, prices, source revision, pack digest and approval. Send, dispatch, delete and payment operations are not implemented.

Local human identity is a fixed development operator. Requests require an exact loopback Host, same-origin browser context and custom write header. This prevents basic cross-site browser requests; it does not authenticate malicious software running on the same machine. Production OIDC, role membership/revocation, authorization-grade DB grants, network egress policies and independent security review are pending.

Audit rows reject UPDATE/DELETE through a PostgreSQL trigger. The development database owner can still change database schema or disable that trigger; this is not a tamper-proof production audit store. Case and evidence references have composite tenant foreign keys, and all service queries are scoped.

Model credentials stay outside source control. `.env` is local and mode 0600. No provider error bodies, credentials or message content are written to the run audit. Source messages are still stored in the local PostgreSQL database; encryption, retention/export/deletion beyond case JSON export are not production-ready.

No public security reporting address has been established because this source has not been released publicly. Before public release, establish a private disclosure channel and complete the spec's release checklist.
