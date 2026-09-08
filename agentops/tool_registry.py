from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Service = Literal["api", "nginx", "postgres", "redis", "worker"]


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceArgs(StrictArgs):
    service: Service


class HealthArgs(ServiceArgs):
    endpoint: Literal["/healthz", "/readyz"] = "/healthz"


class ProjectArgs(StrictArgs):
    project: Literal["demo"] = "demo"


class ContainerArgs(StrictArgs):
    container_id: str = Field(pattern=r"^demo-(api|nginx|postgres|redis|worker)$")


class LogArgs(ContainerArgs):
    tail: int = Field(default=100, ge=1, le=200)
    since: Literal["5m", "15m", "1h"] = "15m"


class TargetArgs(StrictArgs):
    target: Service


class DiskArgs(TargetArgs):
    path: Literal["/var/log/demo", "/data"] = "/var/log/demo"


class ProcessArgs(TargetArgs):
    filter: Literal["service", "worker"] = "service"


class PortArgs(TargetArgs):
    port: int = Field(ge=1, le=65535)


class PrometheusArgs(StrictArgs):
    query_id: Literal["service_health", "error_rate", "cpu_usage", "request_latency"]
    time_range: Literal["5m", "15m", "1h"] = "15m"


class DatabaseArgs(StrictArgs):
    database: Literal["app"] = "app"


class RedisArgs(StrictArgs):
    instance: Literal["cache"] = "cache"


class QueueArgs(RedisArgs):
    queue: Literal["jobs"] = "jobs"


class ReplicasArgs(ServiceArgs):
    replicas: int = Field(ge=1, le=3)


class RollbackArgs(ServiceArgs):
    version: str = Field(pattern=r"^v[0-9]+$")


TOOL_MODELS: dict[str, type[BaseModel]] = {
    "http_health_check": HealthArgs,
    "docker_list_containers": ProjectArgs,
    "docker_inspect_container": ContainerArgs,
    "docker_read_logs": LogArgs,
    "system_resource_usage": TargetArgs,
    "disk_usage": DiskArgs,
    "process_list": ProcessArgs,
    "port_check": PortArgs,
    "prometheus_query": PrometheusArgs,
    "postgres_health_check": DatabaseArgs,
    "postgres_activity_summary": DatabaseArgs,
    "redis_health_check": RedisArgs,
    "redis_queue_length": QueueArgs,
    "deployment_history": ServiceArgs,
    "docker_restart_container": ContainerArgs,
    "docker_scale_service": ReplicasArgs,
    "reload_nginx": ServiceArgs,
    "restart_worker": ServiceArgs,
    "rollback_deployment": RollbackArgs,
    "rotate_demo_logs": ServiceArgs,
}


def validate_arguments(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    model = TOOL_MODELS.get(tool)
    if not model:
        raise ValueError("tool is not registered")
    return model.model_validate(arguments).model_dump()


def default_arguments(tool: str, service: str) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {
        "http_health_check": {"service": service, "endpoint": "/healthz"},
        "docker_list_containers": {"project": "demo"},
        "docker_inspect_container": {"container_id": f"demo-{service}"},
        "docker_read_logs": {"container_id": f"demo-{service}", "tail": 100, "since": "15m"},
        "system_resource_usage": {"target": service},
        "disk_usage": {"target": service, "path": "/var/log/demo"},
        "process_list": {"target": service, "filter": "worker" if service == "worker" else "service"},
        "port_check": {"target": service, "port": 6379 if service == "redis" else 8000},
        "prometheus_query": {"query_id": "service_health", "time_range": "15m"},
        "postgres_health_check": {"database": "app"},
        "postgres_activity_summary": {"database": "app"},
        "redis_health_check": {"instance": "cache"},
        "redis_queue_length": {"instance": "cache", "queue": "jobs"},
        "deployment_history": {"service": service},
    }
    return validate_arguments(tool, values[tool])


def public_registry() -> list[dict[str, Any]]:
    return [{"name": name, "input_schema": model.model_json_schema()} for name, model in sorted(TOOL_MODELS.items())]
