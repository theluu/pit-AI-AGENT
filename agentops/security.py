import re
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"(?i)(password|token|secret|api[_-]?key)\s*[=:]\s*[^\s,;]+"),
    re.compile(r"(?i)(postgres(?:ql)?|redis)://[^\s]+"),
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
]


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if any(x in k.lower() for x in ("secret", "password", "token", "api_key")) else redact(v)) for k, v in value.items()}
    if isinstance(value, list): return [redact(v) for v in value]
    if isinstance(value, str):
        for pattern in SECRET_PATTERNS: value = pattern.sub("[REDACTED]", value)
    return value


def validate_service(value: str) -> str:
    allowed = {"api", "nginx", "postgres", "redis", "worker"}
    if value not in allowed: raise ValueError("target is outside the sandbox service registry")
    return value
