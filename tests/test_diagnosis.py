from agentops.diagnosis import analyze
from agentops.scenarios import SCENARIOS, tool_result


def evidence_for(scenario_id: str):
    scenario = SCENARIOS[scenario_id]
    return [{"tool": tool, "result": tool_result(scenario_id, tool)} for tool in scenario["tools"]]


def test_diagnosis_has_explainable_ranked_output():
    scenario = SCENARIOS["INC-001"]
    result = analyze(scenario, evidence_for("INC-001"))
    assert result["confidence"] > 0.9
    assert result["coverage"] == 1.0
    assert result["source_diversity"] >= 3
    assert result["hypotheses"][0]["label"] == scenario["root_cause"]
    assert all("contribution" in row and "reliability" in row for row in result["contributions"])


def test_false_alarm_explicitly_abstains():
    scenario = SCENARIOS["INC-009"]
    result = analyze(scenario, evidence_for("INC-009"))
    assert result["decision"] == "abstain"
    assert result["confidence"] > 0.85


def test_log_evidence_is_never_treated_as_verified_source():
    scenario = SCENARIOS["INC-010"]
    result = analyze(scenario, evidence_for("INC-010"))
    log = next(row for row in result["contributions"] if row["tool"] == "docker_read_logs")
    assert log["trust"] == "untrusted"
    assert log["reliability"] < 0.7
