from agentops.engine import AgentEngine
from agentops.llm import DiagnosisOutput, Hypothesis, InvestigationPlan, ModelResult
from agentops.store import Store


class FakeGateway:
    def plan(self, incident):
        value = InvestigationPlan(
            normalized_summary="API is returning gateway errors",
            hypotheses=[Hypothesis(label="API workload stopped", probability=0.8, rationale="Gateway cannot reach API")],
            selected_tools=["http_health_check", "docker_list_containers"],
            reasoning_summary="Correlate synthetic health with runtime state.",
        )
        return ModelResult(value, "test-planner", "resp_plan", 100, 30, 10)

    def diagnose(self, incident, evidence):
        value = DiagnosisOutput(
            root_cause="API workload stopped",
            confidence=0.91,
            hypotheses=[Hypothesis(label="API workload stopped", probability=0.91, rationale="Health and runtime agree")],
            reasoning_summary="Two independent observations agree.",
            should_abstain=False,
        )
        return ModelResult(value, "test-planner", "resp_diagnose", 120, 40, 12)


def test_llm_mode_is_structured_audited_and_policy_constrained(tmp_path):
    store = Store(str(tmp_path / "agentops.db"))
    engine = AgentEngine(store, gateway=FakeGateway())
    incident = {"id": "inc_llm", "title": "Gateway errors", "description": "API returns 502", "service": "api", "severity": "SEV-2", "scenario_id": "INC-001", "runtime_mode": "llm", "status": "created"}
    store.put("incidents", incident["id"], incident)
    result = engine.run(incident["id"])
    assert result["root_cause"] == "API workload stopped"
    assert result["confidence"] == 0.91
    assert len(store.list("model_calls", incident["id"])) == 2
    run = store.list("runs", incident["id"])[0]
    assert run["runtime_mode_used"] == "llm"
    assert run["tool_calls_used"] == 2


def test_auto_mode_records_visible_fallback(tmp_path):
    store = Store(str(tmp_path / "agentops.db"))
    engine = AgentEngine(store)
    incident = {"id": "inc_auto", "title": "Gateway errors", "description": "API returns 502", "service": "api", "severity": "SEV-2", "scenario_id": "INC-001", "runtime_mode": "auto", "status": "created"}
    store.put("incidents", incident["id"], incident)
    engine.run(incident["id"])
    events = store.events(incident["id"])
    assert any(event["type"] == "runtime_fallback" for event in events)
