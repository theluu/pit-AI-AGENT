import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with tempfile.NamedTemporaryFile(suffix=".db") as handle:
        os.environ["AGENTOPS_DB_PATH"] = handle.name
        import agentops.api as module
        from agentops.engine import AgentEngine
        from agentops.store import Store

        module.store = Store(handle.name)
        module.engine = AgentEngine(module.store)
        with TestClient(module.app) as value:
            yield value


@pytest.fixture()
def incident(client):
    body = {"title": "Production 502", "description": "Investigate the API outage", "scenario_id": "INC-001", "service": "api"}
    return client.post("/api/v1/incidents", json=body).json()
