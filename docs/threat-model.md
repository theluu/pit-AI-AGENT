# Threat model

## Trust boundaries

User descriptions, HTTP responses, logs, labels, and tool output are untrusted. Pydantic validates API input; the tool registry accepts only logical sandbox identifiers; output is recursively redacted before audit/display. No model or browser input can add a tool to the whitelist.

## Principal threats and controls

| Threat | Control |
|---|---|
| Prompt injection in logs | Output marked untrusted; deterministic policy ignores instructions; adversarial regression test |
| Arbitrary code execution | No shell tool; deny-by-default registry |
| SSRF | Fixed logical service registry, no caller-provided URL |
| Secret disclosure | Recursive key/value, email, and connection-string redaction |
| Approval replay | Pending state, expiry, single-use timestamp, incident/action/arguments binding |
| Excessive privilege | R0–R4 policy; R2/R3 approval; R3 explicit confirmation |
| Docker host compromise | No Docker socket mount; fixtures only |
| Destructive changes | Delete, database, volume, firewall, and migration operations absent and R4 |

## Residual risk

The demo has no login/RBAC or rate limiter. SQLite is not tamper-evident and process-local mutation is not horizontally safe. Before real deployment, add an identity provider, role checks, database constraints/transactions, immutable audit export, rate limits, signed tool-service requests, network policies, and a separately isolated sandbox VM.

