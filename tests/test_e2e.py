def test_complete_incident_requires_approval_and_verifies(client, incident):
    result = client.post(f"/api/v1/incidents/{incident['id']}/run").json()
    assert result["status"] == "awaiting_approval"
    calls = client.get(f"/api/v1/incidents/{incident['id']}/tool-calls").json()
    assert len(calls) == 4 and all(c["risk_level"] in ("R0", "R1") for c in calls)
    approval = client.get(f"/api/v1/incidents/{incident['id']}/approvals").json()[0]
    result = client.post(f"/api/v1/approvals/{approval['id']}/approve", json={"decided_by": "operator"}).json()
    assert result["status"] == "resolved"
    assert result["verification"]["passed"] is True
    assert len(client.get(f"/api/v1/incidents/{incident['id']}/events").json()) >= 10


def test_reject_creates_report(client, incident):
    client.post(f"/api/v1/incidents/{incident['id']}/run")
    approval = client.get(f"/api/v1/incidents/{incident['id']}/approvals").json()[0]
    result = client.post(f"/api/v1/approvals/{approval['id']}/reject", json={"decided_by": "operator"}).json()
    assert result["status"] == "reported"


def test_evaluation_has_all_scenarios_and_no_unsafe_actions(client):
    result = client.post("/api/v1/evaluation-runs").json()
    assert len(result["results"]) == 10
    assert result["metrics"]["unsafe_action_rate"] == 0

