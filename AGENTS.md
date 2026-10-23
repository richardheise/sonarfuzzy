# Agent guidance

Read `README.md` and `docs/experiment.md` before changing the experiment. Keep generated results, secrets, target dumps and private API descriptions out of Git. Fixtures are synthetic.

The CLI creates plans; it does not prove a vulnerability or launch RESTler. Preserve this distinction in code, tests and prose. A SonarQube issue-to-OpenAPI link requires human evidence; a runtime finding needs replay and same-root-cause review. Do not fuzz production or shared MECRED environments.

Prefer small, isolated tests (`python3 -B -m unittest discover -s tests -q`). Do not start SonarQube, RESTler, Bun, PostgreSQL or an LLM just to check a documentation or CLI change. Use a disposable test target and bounded resources for any later live run. Record changes and outstanding decisions in `docs/implementation-log.md`.
