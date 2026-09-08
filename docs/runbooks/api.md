# API Service Runbook

## HTTP 502 and unavailable API

Confirm the external health status, then correlate it with workload state and recent logs. A 502 alone does not prove the API container is stopped. Check the upstream port and runtime state before proposing a restart.

## Latency and database saturation

Compare request latency and error rate with PostgreSQL active connections. If active connections equal the configured maximum and idle capacity is zero, treat pool exhaustion as the leading hypothesis. Prefer traffic reduction or a controlled service restart only after approval.

## High CPU

Correlate service CPU with process-level CPU and request metrics. Scaling can mitigate impact but does not remove an expensive endpoint; create a follow-up to profile and rate-limit the path.
