from types import SimpleNamespace

from agentops import live_monitor


def test_live_status_endpoint_is_disabled_by_default(client):
    response = client.get("/api/v1/environments/current/status")
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "environment_id": "demo-sandbox"}


def test_snapshot_uses_only_fixed_registries(monkeypatch):
    monkeypatch.setattr(live_monitor, "settings", SimpleNamespace(
        live_monitoring=True,
        environment_id="production-vps-01",
        environment_name="Production VPS",
        environment_host="example.invalid",
    ))
    monkeypatch.setattr(live_monitor, "_service_status", lambda unit: "active")
    monkeypatch.setattr(live_monitor, "_port_status", lambda port: True)
    value = live_monitor.snapshot()
    assert value["read_only"] is True
    assert value["healthy"] is True
    assert set(value["services"]) == {"agent-api", "nginx", "postgresql", "redis"}
    assert set(value["ports"]) == {"agent-api", "nginx-http", "nginx-https"}
