# SonarFuzzy

Terms for discussing whether a static finding and observed REST API behavior share a cause.

## Language

**Static finding**:
A SonarQube issue describing a possible problem in one analyzed application revision. It is a hypothesis, not evidence of a runtime failure.
_Avoid_: Confirmed bug, vulnerability.

**Reviewed link**:
A human-supported claim that one API operation can reach the code region associated with a static finding. Reachability does not imply that the finding is true.
_Avoid_: Confirmed match.

**Runtime finding**:
An anomalous behavior observed while exercising an API, with enough recorded input and state to attempt reproduction. Its existence does not identify its cause.
_Avoid_: SonarQube confirmation.

**Confirmed correspondence**:
A reviewed static finding and a reproducible runtime finding shown by evidence to share the same root cause.
_Avoid_: HTTP 500, bug bucket, matched endpoint.

**Experiment arm**:
One selection strategy evaluated under a specified target, candidate set and resource budget. The current arms are a deterministic baseline and an optional LLM-guided ranking.
_Avoid_: Fuzzer implementation.
