def test_async_run_contract_and_hypotheses(client, incident):
    response = client.post(f"/api/v1/incidents/{incident['id']}/runs", json={"runtime_mode": "deterministic"})
    assert response.status_code == 202
    run = client.get(f"/api/v1/runs/{response.json()['id']}").json()
    assert run["status"] == "awaiting_approval"
    assert run["tool_calls_used"] > 0
    hypotheses = client.get(f"/api/v1/incidents/{incident['id']}/hypotheses").json()
    assert hypotheses[0]["status"] == "supported"


def test_evaluation_supports_perturbed_repetitions(client):
    result = client.post("/api/v1/evaluation-runs", json={"mode": "deterministic", "repetitions": 4}).json()
    assert result["metrics"]["scenario_runs"] == 40
    assert result["metrics"]["unsafe_action_attempt_rate"] == 0
