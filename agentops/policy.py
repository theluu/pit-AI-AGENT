from dataclasses import dataclass

READ_ONLY = {"http_health_check", "docker_list_containers", "docker_inspect_container", "docker_read_logs", "system_resource_usage", "disk_usage", "process_list", "port_check", "prometheus_query", "postgres_health_check", "postgres_activity_summary", "redis_health_check", "redis_queue_length", "deployment_history"}
MUTATING = {"docker_restart_container": "R2", "docker_scale_service": "R2", "reload_nginx": "R2", "restart_worker": "R2", "rollback_deployment": "R3", "rotate_demo_logs": "R2"}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    risk: str
    approval_required: bool
    reason: str


def authorize(tool: str) -> Decision:
    if tool in READ_ONLY: return Decision(True, "R1" if tool == "docker_read_logs" else "R0", False, "whitelisted read-only operation")
    if tool in MUTATING: return Decision(True, MUTATING[tool], True, "scoped approval required")
    return Decision(False, "R4", False, "operation is not in the whitelist")
