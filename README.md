# AgentOps Commander

A safe, web-based incident-response agent demo. It gathers evidence with typed, whitelisted tools, pauses for scoped human approval before changes, verifies recovery, and produces an auditable report.

![Python](https://img.shields.io/badge/Python-3.12-3776AB) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688) ![Safety](https://img.shields.io/badge/unsafe_execution-0-brightgreen)

## Quick start

```bash
docker compose up -d --build
```

Open <http://localhost:8000>. Grafana and Prometheus are available on ports `3000` and `9090`. All incident data and actions are simulated; the application never mounts the host Docker socket.

For local development:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
make test
make dev
```

## Architecture

The API drives a deterministic state graph: `intake → triage → plan → read-only tools → evidence review → approval → action → verification → report`. The deterministic demo runtime makes the safety and evaluation behavior reproducible; its node boundaries are designed so a LangGraph-backed planner can replace the planner/reviewer without changing policy enforcement.

- FastAPI exposes incident, SSE, approval, report, and evaluation APIs.
- Pydantic validates all public request schemas.
- The policy engine—not model output—authorizes each operation.
- SQLite provides a zero-config local audit store; Compose includes PostgreSQL and Redis as production-shaped extension points.
- Static web UI visualizes state, evidence, approval, verification, and evaluation metrics.
- Reliability-weighted diagnosis scores evidence strength across independent source domains, ranks alternative hypotheses, reports conflicts/coverage, and makes abstention explicit.
- Ten fixtures cover stopped services, saturation, bad deploys, missing config, a healthy system, and adversarial log content.

See [architecture](docs/architecture.md), [threat model](docs/threat-model.md), and [evaluation report](docs/evaluation-report.md).

## API demo

```bash
curl -s http://localhost:8000/api/v1/scenarios
curl -s -X POST http://localhost:8000/api/v1/evaluation-runs
```

Interactive OpenAPI docs are at <http://localhost:8000/docs>.

## Security properties

- No arbitrary shell, SQL, PromQL, raw-secret, filesystem deletion, firewall, or external-host tool exists.
- Mutation is impossible without a matching, unexpired, single-use approval.
- R3 rollback additionally requires the exact `CONFIRM R3` confirmation.
- Tool results are redacted before persistence or display and are explicitly marked untrusted.
- Health targets are logical names from a fixed sandbox registry, preventing SSRF.
- The Docker socket is never mounted.

This is a portfolio sandbox, not a production control plane. Authentication/RBAC, distributed graph persistence, real OpenTelemetry spans, PostgreSQL repositories, queue workers, real service adapters, and PDF export are intentionally left as production integrations. Never connect this demo directly to production infrastructure.

## Metrics and limitations

The included deterministic suite reports 100% root-cause/action accuracy and zero unsafe executions on its ten canonical fixtures. These values prove regression behavior, not general model quality. A production evaluation should include at least 20 perturbed runs, blinded labels, real latency/token accounting, and multiple graph/model versions.

## What to show in a 5-minute demo

1. Run `INC-001` and point out the typed-tool trace and independent evidence domains.
2. Compare the ranked differential diagnosis and evidence contribution bars.
3. Approve the scoped R2 action, then show the post-action recovery check.
4. Run `INC-010` to demonstrate that instructions embedded in logs remain untrusted and the agent abstains from mutation.
5. Open Evaluation Lab to close with accuracy, tool efficiency, and unsafe-action metrics.
