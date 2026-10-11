# Local development

Read the README and `docs/BUILD_STATUS.md`. Install with `uv sync --locked --python 3.12`. Keep all fixtures synthetic and run lint, type checks, tests and the console build for relevant changes.

Preserve the gateway boundary: models propose, application code validates, humans approve exact actions where required, and only provider read-back proves an effect. Do not introduce a direct provider-write tool, automatic billing fallback, or alternate durability engine.

The current migration is a prototype baseline. Freeze its SQL independently of current Python metadata before a distributed release; add forward migrations thereafter. Never reset production/customer state in a migration.

There is no approved open-source license yet. Do not publish or copy third-party implementation code until contributor rights and dependency licenses have been reviewed.
