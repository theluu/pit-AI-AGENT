from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .models import Status, new_id, now_iso
from .policy import authorize
from .scenarios import SCENARIOS, tool_result
from .security import redact
from .store import Store


class AgentEngine:
    """Deterministic state graph used by the safe demo/evaluation harness."""

    def __init__(self, store: Store): self.store = store

    def emit(self, incident_id: str, node: str, message: str, data: dict[str, Any] | None = None):
        return self.store.event(incident_id, node, message, redact(data or {}))

    def run(self, incident_id: str) -> dict[str, Any]:
        incident = self._incident(incident_id)
        if incident["status"] not in (Status.CREATED, Status.RUNNING): return incident
        scenario = SCENARIOS[incident["scenario_id"]]
        incident["status"] = Status.RUNNING
        incident["started_at"] = incident.get("started_at") or now_iso()
        self.store.put("incidents", incident_id, incident)
        self.emit(incident_id, "intake", "Incident context normalized", {"service": incident["service"], "severity": incident["severity"]})
        self.emit(incident_id, "triage", f"Selected playbook: {scenario['name']}")
        self.emit(incident_id, "plan", "Investigation plan created", {"steps": scenario["tools"], "max_tool_calls": 12})
        evidence = []
        for step, tool in enumerate(scenario["tools"], 1):
            decision = authorize(tool)
            if not decision.allowed: continue
            result = redact(tool_result(incident["scenario_id"], tool))
            call = {"id": new_id("call"), "incident_id": incident_id, "agent_step_id": step, "tool_name": tool, "sanitized_arguments": {"service": incident["service"]}, "sanitized_result": result, "risk_level": decision.risk, "status": "succeeded", "latency_ms": 5, "error": None, "created_at": now_iso()}
            self.store.put("tool_calls", call["id"], call)
            evidence.append({"tool": tool, "result": result})
            self.emit(incident_id, "tool_call", f"{tool} completed", {"tool_call_id": call["id"], "risk": decision.risk})
        confidence = 0.99 if len(evidence) >= 2 else 0.65
        self.emit(incident_id, "review_evidence", "Evidence supports a root cause", {"root_cause": scenario["root_cause"], "confidence": confidence, "evidence_count": len(evidence), "untrusted_outputs_ignored": True})
        incident["root_cause"] = scenario["root_cause"]
        incident["confidence"] = confidence
        incident["evidence"] = evidence
        if scenario.get("action"):
            tool, arguments = scenario["action"]
            decision = authorize(tool)
            approval = {"id": new_id("apr"), "incident_id": incident_id, "tool_call_id": new_id("pending"), "requested_action": tool, "sanitized_arguments": arguments, "risk_level": decision.risk, "impact": f"Changes demo {incident['service']} service state", "rollback_plan": "Restore the previous demo state", "decision": "pending", "decided_by": None, "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(), "used_at": None}
            self.store.put("approvals", approval["id"], approval)
            incident["status"] = Status.AWAITING_APPROVAL
            incident["approval_id"] = approval["id"]
            self.emit(incident_id, "await_approval", "A scoped action requires approval", approval)
        else:
            incident["status"] = Status.REPORTED
            incident["resolved_at"] = now_iso()
            self.emit(incident_id, "report", "Report ready; no system change recommended", {"abstained": True})
        self.store.put("incidents", incident_id, incident)
        return incident

    def decide(self, approval_id: str, approved: bool, actor: str, arguments: dict[str, Any] | None = None, confirmation: str | None = None):
        approval = self.store.get("approvals", approval_id)
        if not approval: raise KeyError("approval not found")
        if approval["decision"] != "pending" or approval.get("used_at"): raise ValueError("approval already decided; replay rejected")
        if datetime.fromisoformat(approval["expires_at"]) <= datetime.now(UTC): raise ValueError("approval expired")
        if approval["risk_level"] == "R3" and approved and confirmation != "CONFIRM R3": raise ValueError("R3 action requires confirmation: CONFIRM R3")
        if arguments is not None: approval["sanitized_arguments"] = redact(arguments)
        approval.update({"decision": "approved" if approved else "rejected", "decided_by": actor, "used_at": now_iso()})
        self.store.put("approvals", approval_id, approval)
        incident = self._incident(approval["incident_id"])
        self.emit(incident["id"], "approval", f"Action {approval['decision']}", {"approval_id": approval_id, "decided_by": actor})
        if not approved:
            incident["status"] = Status.REPORTED; incident["resolved_at"] = now_iso()
            self.emit(incident["id"], "report", "Report ready; proposed action was rejected")
        else:
            decision = authorize(approval["requested_action"])
            if not decision.allowed or not decision.approval_required: raise ValueError("policy rejected action")
            self.emit(incident["id"], "execute_action", f"Executed {approval['requested_action']}", {"arguments": approval["sanitized_arguments"]})
            scenario = SCENARIOS[incident["scenario_id"]]
            after = tool_result(incident["scenario_id"], scenario["tools"][0], after=True)
            incident["verification"] = {"check_name": scenario["verify"], "before_value": incident["evidence"][0]["result"], "after_value": after, "expected_condition": scenario["verify"], "passed": True}
            incident["status"] = Status.RESOLVED; incident["resolved_at"] = now_iso()
            self.emit(incident["id"], "verify", "Post-action verification passed", incident["verification"])
            self.emit(incident["id"], "report", "Incident resolved and report ready")
        self.store.put("incidents", incident["id"], incident)
        return incident

    def _incident(self, incident_id: str):
        value = self.store.get("incidents", incident_id)
        if not value: raise KeyError("incident not found")
        return value

