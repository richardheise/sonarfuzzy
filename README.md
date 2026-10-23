# SonarFuzzy

SonarFuzzy prepares reproducible experiments that ask whether REST API behavior can corroborate findings from SonarQube. It exports issues, maps them to reviewed OpenAPI operations, and writes comparable RESTler settings for a deterministic baseline and an optional LLM ranking. It does **not** run RESTler or declare SonarQube issues confirmed automatically.

The first version is a small Python 3.10+ CLI with no required third-party packages. YAML OpenAPI files need the optional `PyYAML` package; JSON files work with the standard library.

## Try it without a service

From the repository root:

```sh
python3 -m sonarfuzzy plan \
  --openapi fixtures/openapi.json \
  --issues fixtures/sonar-issues.json \
  --links fixtures/links.csv \
  --output results/demo --top-k 1 --budget-minutes 5

python3 -B -m unittest discover -s tests -v
```

The fixtures are synthetic. `results/demo/plan.json` records input hashes, selection, budget and seed. The two `restler-*.json` files contain RESTler `include_requests`; `review.csv` is for manual evidence. Generated results and credentials are ignored by Git.

## Use it with an isolated API

1. Obtain a SonarQube analysis and an OpenAPI document from the **same application revision**. Consult the [Web API page of your SonarQube version](https://docs.sonarsource.com/sonarqube-server/extension-guide/web-api). Export the project's issues:

   ```sh
   export SONAR_TOKEN='local-token'
   python3 -m sonarfuzzy export-sonar \
     --url http://localhost:9000 --project-key example \
     --output results/issues.json
   ```

2. List the operations with `python3 -m sonarfuzzy list-openapi --openapi openapi.json --output results/operations.csv`. Create a `links.csv` using the header in `fixtures/links.csv`: `issue_key,method,path,approved,evidence`. Approve a link only after checking that the operation can reach the code described by the issue. Unapproved links are ignored.
3. Run `plan` with your three inputs. The baseline sorts approved operations by linked issue count. An optional OpenAI-compatible Chat Completions endpoint can reorder at most 50 approved candidates via `--llm-url` and `--llm-model`; set `LLM_API_KEY` for a remote endpoint. The LLM receives issue messages and operation descriptions. It cannot add operations or prove defects.
4. Compile the OpenAPI with RESTler, run its `test` mode, then run each plan against **separate resets of an isolated test instance**. Keep the same grammar, dictionary, auth, budget and seed, and alternate arm order across repetitions. RESTler may execute prerequisite operations beyond `include_requests`. See its [quick start](https://github.com/microsoft/restler-fuzzer/blob/main/docs/user-guide/QuickStart.md) and [settings reference](https://github.com/microsoft/restler-fuzzer/blob/main/docs/user-guide/SettingsFile.md).
5. Review bug buckets and replay traces. Fill `review.csv`, then run `python3 -m sonarfuzzy report --review results/demo/review.csv --output results/demo/report.json`. A `confirmed` verdict requires a runtime oracle, bug bucket, replay file, evidence and human confirmation of the same root cause. An HTTP 500 alone does not establish that connection.

Do not fuzz production or shared services. RESTler can mutate persistent state; use disposable data and bounded time. More detail and limitations are in [the experiment protocol](docs/experiment.md).

The [glossary](GLOSSARY.md) distinguishes a static finding, a reviewed link, a runtime finding and a confirmed correspondence.

## Status

This is an experiment-planning prototype, not a validated vulnerability detector. Its current tests use only synthetic data and mocked HTTP responses. No SonarQube, RESTler or LLM service is started by the test suite. The MECRED pilot will use a separate, disposable local test target; no MECRED credentials or internal data belong in this repository.

The prototype originated in a broader fuzzing literature repository. Its [implementation log](docs/implementation-log.md) records the initial work. Design interviews and ADRs are still pending; the intended [`grill-with-docs` workflow](https://github.com/mattpocock/skills/blob/main/skills/engineering/grill-with-docs/SKILL.md) has not yet been run.
