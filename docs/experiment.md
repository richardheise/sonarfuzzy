# Experiment protocol and limitations

## Research question

Under a short, fixed runtime budget, does prioritizing REST operations using reviewed static-analysis findings improve the number of **reproducible issues with a confirmed common cause** over a deterministic issue-count baseline?

The unit of selection is an OpenAPI method and path. A SonarQube issue maps to an operation only through a reviewed link with a written reason. `plan.json` preserves hashes of the spec, issue export and mapping file; record application revision, SonarQube version/ruleset, RESTler version, grammar, dictionary, auth method and LLM model/version alongside it.

## Controlled comparison

- Use the same candidate links, number of selected operations, RESTler mode, grammar, dictionary, target configuration, random seed and `time_budget` for both arms. The setting's budget is in hours.
- Reset the application and disposable database between arms. Repeat runs with alternating arm order. Keep compilation and RESTler `test` time separate from fuzzing time.
- Measure valid requests, covered operations, unique reproducible bug buckets, confirmed issue/root-cause pairs, false associations, wall time and LLM cost/latency. A selected endpoint's prerequisites may also be exercised by RESTler; report that as exposure outside the selected set.
- Compare with more than one baseline before claiming scientific benefit. The current baseline counts linked issues and breaks ties lexically; it is deliberately simple.

## Interpretation

An HTTP 500 or RESTler bug bucket is an observed runtime anomaly. It may be unrelated to the SonarQube issue. A `confirmed` result needs a replay and human inspection showing the same root cause; record the oracle and evidence in `review.csv`. Lack of a bug does not refute an issue without demonstrating adequate reachability, input validity and coverage. Authorization and injection bugs may require specialized oracles and may return HTTP 200.

The CLI currently prepares settings and review files. It does not launch RESTler, build payloads from SonarQube messages, interpret bug buckets automatically, or inspect source code. `include_requests` is a RESTler filter, not a guarantee that only those requests run. The OpenAPI reader lists methods and paths but does not resolve external references. LLM ranking is bounded to approved candidates and sends issue messages and operation descriptions to its configured endpoint; use local models if those messages must remain local.

## Prior work to read before a novelty claim

RESTler's [official documentation](https://github.com/microsoft/restler-fuzzer) and Microsoft's archived [RAFT](https://github.com/microsoft/rest-api-fuzz-testing) show that RESTler itself and CI integration are prior art. Related abstracts include [RESTLess](https://ieeexplore.ieee.org/document/10740182/), [RESTler plus LLM parameter generation](https://www.mdpi.com/2673-4591/120/1/42), [APIGFUZZ](https://ieeexplore.ieee.org/abstract/document/11685825/) and [static warning validation by fuzzing in C](https://arxiv.org/abs/2106.04735). These references need full-text review before positioning a paper; titles and abstracts alone do not establish novelty.
