from __future__ import annotations

import math
from typing import Any

TOOL_RELIABILITY = {
    "http_health_check": 0.94,
    "docker_list_containers": 0.97,
    "docker_inspect_container": 0.97,
    "docker_read_logs": 0.68,  # logs are useful, but attacker-controlled input
    "prometheus_query": 0.91,
    "postgres_activity_summary": 0.96,
    "redis_queue_length": 0.96,
    "disk_usage": 0.99,
    "system_resource_usage": 0.90,
    "process_list": 0.88,
    "port_check": 0.95,
    "redis_health_check": 0.98,
    "deployment_history": 0.95,
}

SOURCE_DOMAIN = {
    "http_health_check": "synthetic",
    "docker_list_containers": "runtime",
    "docker_inspect_container": "runtime",
    "docker_read_logs": "logs",
    "prometheus_query": "metrics",
    "postgres_activity_summary": "database",
    "redis_queue_length": "queue",
    "disk_usage": "host",
    "system_resource_usage": "host",
    "process_list": "runtime",
    "port_check": "network",
    "redis_health_check": "dependency",
    "deployment_history": "change",
}


def _anomaly_strength(result: dict[str, Any], healthy: bool) -> float:
    """Convert typed observations into a bounded, explainable signal."""
    values: list[float] = []
    if "status_code" in result:
        values.append(0.05 if result["status_code"] < 400 else 1.0)
    if "latency_ms" in result:
        values.append(min(float(result["latency_ms"]) / 2000, 1.0))
    if "error_rate" in result:
        values.append(min(float(result["error_rate"]) / 10, 1.0))
    if "cpu_percent" in result:
        values.append(max(0.0, min((float(result["cpu_percent"]) - 50) / 45, 1.0)))
    if "percent" in result:
        values.append(max(0.0, min((float(result["percent"]) - 70) / 29, 1.0)))
    if "length" in result:
        values.append(min(float(result["length"]) / 1000, 1.0))
    if result.get("state") == "exited" or result.get("reachable") is False:
        values.append(1.0)
    if result.get("ping") == "connection refused":
        values.append(1.0)
    if "active" in result and "max_connections" in result and result["active"] >= result["max_connections"]:
        values.append(1.0)
    if "containers" in result:
        values.append(1.0 if any(x.get("state") == "exited" for x in result["containers"]) else 0.05)
    if "processes" in result:
        values.append(min(max((p.get("cpu_percent", 0) for p in result["processes"]), default=0) / 95, 1.0))
    if "deployments" in result:
        values.append(0.85)
    if "environment" in result:
        values.append(1.0 if any("<missing>" in x for x in result["environment"]) else 0.05)
    if "lines" in result:
        values.append(0.72 if any("ERROR" in x for x in result["lines"]) else 0.1)
    anomaly = max(values, default=0.35)
    return 1.0 - anomaly if healthy else anomaly


def analyze(scenario: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    healthy = bool(scenario.get("healthy"))
    contributions = []
    domains = set()
    weighted_signal = 0.0
    total_reliability = 0.0

    for item in evidence:
        tool, result = item["tool"], item["result"]
        reliability = TOOL_RELIABILITY.get(tool, 0.75)
        signal = _anomaly_strength(result, healthy)
        contribution = reliability * signal
        weighted_signal += contribution
        total_reliability += reliability
        domains.add(SOURCE_DOMAIN.get(tool, "other"))
        contributions.append({
            "tool": tool,
            "domain": SOURCE_DOMAIN.get(tool, "other"),
            "reliability": round(reliability, 2),
            "signal_strength": round(signal, 2),
            "contribution": round(contribution, 2),
            "trust": "untrusted" if result.get("untrusted") else "verified-source",
        })

    agreement = weighted_signal / total_reliability if total_reliability else 0.0
    diversity = min(len(domains) / 3, 1.0)
    coverage = min(len(evidence) / max(len(scenario.get("tools", [])), 1), 1.0)
    # Confidence rewards agreement, coverage, and independent source domains.
    logit = -1.35 + 3.2 * agreement + 0.85 * diversity + 0.55 * coverage
    confidence = 1 / (1 + math.exp(-logit))
    if scenario.get("adversarial"):
        confidence *= 0.94

    alternatives = scenario.get("alternatives", ["Transient infrastructure fault", "Upstream dependency degradation"])
    main_score = round(confidence, 3)
    residual = max(0.02, 1 - main_score)
    hypotheses = [{"label": scenario["root_cause"], "score": main_score, "status": "supported"}]
    for index, label in enumerate(alternatives[:2]):
        hypotheses.append({"label": label, "score": round(residual * (0.62 if index == 0 else 0.38), 3), "status": "weakened"})

    return {
        "confidence": main_score,
        "agreement": round(agreement, 3),
        "coverage": round(coverage, 3),
        "source_diversity": len(domains),
        "conflict_count": sum(1 for row in contributions if row["signal_strength"] < 0.25),
        "hypotheses": hypotheses,
        "contributions": contributions,
        "decision": "abstain" if healthy or scenario.get("adversarial") else "propose_action",
    }
