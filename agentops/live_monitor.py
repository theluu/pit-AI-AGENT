from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import settings

# Fixed registry: API callers cannot supply commands, hosts, services, ports, or paths.
SERVICE_REGISTRY = {
    "agent-api": "agent-api.service",
    "nginx": "nginx.service",
    "postgresql": "postgresql@14-main.service",
    "redis": "redis-server.service",
}
PORT_REGISTRY = {"agent-api": 8002, "nginx-http": 80, "nginx-https": 443}


def _memory() -> dict[str, float]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError):
        return {"total_gb": 0, "available_gb": 0, "used_percent": 0}
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    used = ((total - available) / total * 100) if total else 0
    return {
        "total_gb": round(total / 1024**3, 2),
        "available_gb": round(available / 1024**3, 2),
        "used_percent": round(used, 1),
    }


def _service_status(unit: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit], capture_output=True, text=True, timeout=2, check=False
        )
        status = result.stdout.strip()
        return status if status in {"active", "inactive", "failed", "activating"} else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def _port_status(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def snapshot() -> dict[str, Any]:
    if not settings.live_monitoring:
        return {"enabled": False, "environment_id": settings.environment_id}
    disk = shutil.disk_usage("/")
    try:
        load_1m, load_5m, load_15m = (round(x, 2) for x in os.getloadavg())
    except OSError:
        load_1m = load_5m = load_15m = 0
    try:
        uptime_seconds = int(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        uptime_seconds = 0
    services = {name: _service_status(unit) for name, unit in SERVICE_REGISTRY.items()}
    ports = {name: _port_status(port) for name, port in PORT_REGISTRY.items()}
    healthy = all(value == "active" for value in services.values()) and all(ports.values())
    return {
        "enabled": True,
        "read_only": True,
        "environment_id": settings.environment_id,
        "environment_name": settings.environment_name,
        "host": settings.environment_host,
        "collected_at": int(time.time()),
        "healthy": healthy,
        "uptime_seconds": uptime_seconds,
        "load_average": {"1m": load_1m, "5m": load_5m, "15m": load_15m},
        "memory": _memory(),
        "disk": {
            "total_gb": round(disk.total / 1024**3, 2),
            "free_gb": round(disk.free / 1024**3, 2),
            "used_percent": round(disk.used / disk.total * 100, 1),
        },
        "services": services,
        "ports": ports,
    }
