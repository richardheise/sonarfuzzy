# Implementation log

## 2026-10-23 — extraction into its own repository

- Source: the SonarQube/OpenAPI/RESTler prototype from the fuzzing literature workspace. Moved the CLI, five isolated tests and synthetic fixtures into a Python package with `python -m sonarfuzzy` and a console entry point.
- Current flow: paginated SonarQube issue export; explicit, reviewed issue-to-operation mapping; deterministic baseline; optional constrained LLM ranking; RESTler settings and a manual review table. Generated settings use documented `include_requests`, `time_budget` (hours), `random_seed` and `generate_random_seed` fields.
- Safety boundary: no live SonarQube, RESTler, LLM or target API was started during extraction. No real issue was confirmed. Runtime anomalies still require replay and human same-root-cause review.
- The MECRED backend was located locally for a later pilot. Its OpenAPI document is served by the application, but running it safely will require a disposable database and synthetic integration configuration. No MECRED source, secret, schema or runtime result was copied here.
- The requested `grill-with-docs` skill exists upstream but is not installed in this Codex environment; its dispatcher requires `grilling` and `domain-modeling` skills. No interview or ADR was claimed as complete.
- The upstream `grilling` and `domain-modeling` instructions were read directly. A small `GLOSSARY.md` records terms already settled by the prototype; unresolved pilot decisions still need the user's interview answers. No ADR was invented before those trade-offs are settled.
- Validation: `python3 -B -m unittest discover -s tests -q` and a fixture CLI smoke run are required before publishing the first commit.
