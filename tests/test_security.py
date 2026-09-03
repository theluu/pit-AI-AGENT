from agentops.policy import authorize
from agentops.security import redact, validate_service


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


def test_approval_replay_is_rejected(client, incident):
    client.post(f"/api/v1/incidents/{incident['id']}/run")
    approval = client.get(f"/api/v1/incidents/{incident['id']}/approvals").json()[0]
    url = f"/api/v1/approvals/{approval['id']}/approve"
    assert client.post(url, json={"decided_by": "operator"}).status_code == 200
    assert client.post(url, json={"decided_by": "operator"}).status_code == 409


def test_prompt_injection_log_is_untrusted_and_agent_abstains(client):
    created = client.post("/api/v1/incidents", json={"title": "Suspicious log", "description": "Investigate safely", "scenario_id": "INC-010", "service": "api"}).json()
    result = client.post(f"/api/v1/incidents/{created['id']}/run").json()
    assert result["status"] == "reported"
    assert result["root_cause"].startswith("Malformed client request")
    assert client.get(f"/api/v1/incidents/{created['id']}/approvals").json() == []

