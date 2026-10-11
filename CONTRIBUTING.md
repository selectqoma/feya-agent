# Local development

Read the README and `docs/BUILD_STATUS.md`. Install with `uv sync --locked --python 3.12`. Keep all fixtures synthetic and run lint, type checks, tests and the console build for relevant changes.

Preserve the gateway boundary: models propose, application code validates, humans approve exact actions where required, and only provider read-back proves an effect. Do not introduce a direct provider-write tool, automatic billing fallback, or alternate durability engine.

The current migration is a prototype baseline. Freeze its SQL independently of current Python metadata before a distributed release; add forward migrations thereafter. Never reset production/customer state in a migration.

Open an issue for reproducible bugs or a scoped change proposal; use synthetic examples. Report security issues privately as described in `SECURITY.md`. Describe the behavior changed and checks run in pull requests. Never include `.env`, account auth stores, customer correspondence or runtime databases.

There is no approved open-source license or contribution license agreement yet. Discuss substantive code contributions with the maintainer before submitting them. Do not copy third-party implementation code without reviewing its rights and license. Apache-2.0 remains a proposal until the owner grants it.
