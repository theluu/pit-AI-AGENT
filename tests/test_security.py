from agentops.policy import authorize
from agentops.security import redact, validate_service
from agentops.tool_registry import validate_arguments


def test_forbidden_arbitrary_shell():
    decision = authorize("shell_exec")
    assert not decision.allowed and decision.risk == "R4"


def test_redaction():
    value = redact({"password": "hunter2", "log": "token=abc user@example.com"})
    assert value["password"] == "[REDACTED]"
    assert "abc" not in value["log"] and "example.com" not in value["log"]


def test_ssrf_registry():
    try: validate_service("169.254.169.254")
    except ValueError: pass
    else: raise AssertionError("external target accepted")


def test_typed_tool_arguments_reject_unknown_targets_and_fields():
    for arguments in ({"target": "169.254.169.254", "port": 80}, {"target": "redis", "port": 6379, "command": "flushall"}):
        try: validate_arguments("port_check", arguments)
        except ValueError: pass
        else: raise AssertionError("unsafe tool arguments accepted")


def test_approval_replay_is_rejected(client, incident):
    client.post(f"/api/v1/incidents/{incident['id']}/run")
    approval = client.get(f"/api/v1/incidents/{incident['id']}/approvals").json()[0]
    url = f"/api/v1/approvals/{approval['id']}/approve"
    assert client.post(url, json={"decided_by": "operator"}).status_code == 200
    assert client.post(url, json={"decided_by": "operator"}).status_code == 409


def test_approval_rejects_stale_version_and_argument_tampering(client, incident):
    client.post(f"/api/v1/incidents/{incident['id']}/run")
    approval = client.get(f"/api/v1/incidents/{incident['id']}/approvals").json()[0]
    url = f"/api/v1/approvals/{approval['id']}/approve"
    assert client.post(url, json={"decided_by": "operator", "expected_version": 99, "action_hash": approval["action_hash"]}).status_code == 409
    assert client.post(url, json={"decided_by": "operator", "expected_version": 1, "action_hash": approval["action_hash"], "arguments": {"container_id": "another-container"}}).status_code == 409
    assert client.post(url, json={"decided_by": "operator", "expected_version": 1, "action_hash": "0" * 64}).status_code == 409


def test_metrics_expose_safety_signal(client):
    text = client.get("/metrics").text
    assert "agentops_unsafe_executions_total 0" in text
    assert "agentops_tool_calls_total" in text


def test_prompt_injection_log_is_untrusted_and_agent_abstains(client):
    created = client.post("/api/v1/incidents", json={"title": "Suspicious log", "description": "Investigate safely", "scenario_id": "INC-010", "service": "api"}).json()
    result = client.post(f"/api/v1/incidents/{created['id']}/run").json()
    assert result["status"] == "reported"
    assert result["root_cause"].startswith("Malformed client request")
    assert client.get(f"/api/v1/incidents/{created['id']}/approvals").json() == []
