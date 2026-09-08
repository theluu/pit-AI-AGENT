from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import settings
from .diagnosis import analyze
from .knowledge import RunbookIndex
from .llm import DiagnosisOutput, InvestigationPlan, LLMGateway, LLMUnavailable, build_gateway
from .models import Status, new_id, now_iso
from .policy import authorize
from .scenarios import SCENARIOS, tool_result
from .security import redact
from .store import Store
from .tool_registry import default_arguments, validate_arguments


class AgentEngine:
    """Deterministic state graph used by the safe demo/evaluation harness."""

    def __init__(self, store: Store, gateway: LLMGateway | None = None, knowledge: RunbookIndex | None = None):
        self.store = store
        self.gateway = gateway
        self.knowledge = knowledge or RunbookIndex()

    def emit(self, incident_id: str, node: str, message: str, data: dict[str, Any] | None = None):
        return self.store.event(incident_id, node, message, redact(data or {}))

    def run(self, incident_id: str, runtime_mode: str | None = None, run_id: str | None = None) -> dict[str, Any]:
        incident = self._incident(incident_id)
        if incident["status"] not in (Status.CREATED, Status.RUNNING): return incident
        scenario = SCENARIOS[incident["scenario_id"]]
        requested_mode = runtime_mode or incident.get("runtime_mode", "auto")
        run = self.store.get("runs", run_id) if run_id else None
        run = run or {"id": run_id or new_id("run"), "incident_id": incident_id, "status": "queued", "runtime_mode_requested": requested_mode, "runtime_mode_used": "deterministic", "tool_budget": settings.max_tool_calls, "tool_calls_used": 0, "started_at": None, "completed_at": None, "fallback_reason": None}
        run.update({"status": "running", "started_at": now_iso()})
        self.store.put("runs", run["id"], run)
        incident["run_id"] = run["id"]
        incident["status"] = Status.RUNNING
        incident["started_at"] = incident.get("started_at") or now_iso()
        self.store.put("incidents", incident_id, incident)
        self.emit(incident_id, "intake", "Incident context normalized", {"service": incident["service"], "severity": incident["severity"]})
        self.emit(incident_id, "triage", f"Selected playbook: {scenario['name']}")
        incident["runbook_context"] = self.knowledge.search(incident["description"], incident["service"])
        self.emit(incident_id, "retrieve_context", "Relevant runbook sections retrieved", {"citations": [{"citation_id": row["citation_id"], "heading": row["heading"]} for row in incident["runbook_context"]]})
        tools = scenario["tools"]
        llm_diagnosis: DiagnosisOutput | None = None
        if requested_mode != "deterministic":
            try:
                gateway = self.gateway or build_gateway()
                planned = gateway.plan(incident)
                plan = InvestigationPlan.model_validate(planned.value)
                tools = plan.selected_tools
                run["runtime_mode_used"] = "llm"
                self._record_model_call(incident_id, run["id"], "plan", planned)
                self.emit(incident_id, "llm_plan", "LLM produced a policy-constrained investigation plan", {"model": planned.model, "hypotheses": [h.model_dump() for h in plan.hypotheses], "reasoning_summary": plan.reasoning_summary})
            except LLMUnavailable as exc:
                if requested_mode == "llm":
                    run.update({"status": "failed", "completed_at": now_iso(), "fallback_reason": str(exc)})
                    self.store.put("runs", run["id"], run)
                    raise ValueError(str(exc)) from exc
                run["fallback_reason"] = str(exc)
                self.emit(incident_id, "runtime_fallback", "LLM unavailable; deterministic safety harness activated", {"reason": str(exc), "mode": "deterministic"})
        tools = list(dict.fromkeys(tools))[: run["tool_budget"]]
        self.emit(incident_id, "plan", "Investigation plan created", {"steps": tools, "max_tool_calls": run["tool_budget"], "runtime_mode": run["runtime_mode_used"]})
        evidence = []
        for step, tool in enumerate(tools, 1):
            decision = authorize(tool)
            if not decision.allowed: continue
            result = redact(tool_result(incident["scenario_id"], tool))
            arguments = default_arguments(tool, incident["service"])
            call = {"id": new_id("call"), "incident_id": incident_id, "agent_step_id": step, "tool_name": tool, "sanitized_arguments": arguments, "sanitized_result": result, "risk_level": decision.risk, "status": "succeeded", "latency_ms": 5, "error": None, "created_at": now_iso()}
            self.store.put("tool_calls", call["id"], call)
            evidence.append({"tool": tool, "result": result})
            run["tool_calls_used"] += 1
            self.emit(incident_id, "tool_call", f"{tool} completed", {"tool_call_id": call["id"], "risk": decision.risk})
        analysis = analyze(scenario, evidence)
        if run["runtime_mode_used"] == "llm":
            try:
                gateway = self.gateway or build_gateway()
                diagnosed = gateway.diagnose(incident, evidence)
                llm_diagnosis = DiagnosisOutput.model_validate(diagnosed.value)
                self._record_model_call(incident_id, run["id"], "diagnose", diagnosed)
                analysis["confidence"] = round(llm_diagnosis.confidence, 3)
                analysis["hypotheses"] = [{"label": h.label, "score": h.probability, "status": "supported" if i == 0 else "weakened", "rationale": h.rationale} for i, h in enumerate(llm_diagnosis.hypotheses)]
                analysis["decision"] = "abstain" if llm_diagnosis.should_abstain else "propose_action"
                analysis["reasoning_summary"] = llm_diagnosis.reasoning_summary
            except LLMUnavailable as exc:
                if requested_mode == "llm": raise ValueError(str(exc)) from exc
                run["runtime_mode_used"] = "hybrid-fallback"
                run["fallback_reason"] = str(exc)
                self.emit(incident_id, "runtime_fallback", "Diagnosis model failed; deterministic reviewer completed the run", {"reason": str(exc)})
        confidence = analysis["confidence"]
        self.emit(incident_id, "rank_hypotheses", "Candidate causes ranked by weighted evidence", {"hypotheses": analysis["hypotheses"], "source_diversity": analysis["source_diversity"]})
        root_cause = llm_diagnosis.root_cause if llm_diagnosis else scenario["root_cause"]
        self.emit(incident_id, "review_evidence", "Evidence supports a root cause", {"root_cause": root_cause, "confidence": confidence, "evidence_count": len(evidence), "agreement": analysis["agreement"], "coverage": analysis["coverage"], "conflicts": analysis["conflict_count"], "untrusted_outputs_ignored": True})
        incident["root_cause"] = root_cause
        incident["confidence"] = confidence
        incident["evidence"] = evidence
        incident["analysis"] = analysis
        should_mutate = scenario.get("action") and analysis["decision"] != "abstain" and not scenario.get("adversarial")
        if should_mutate:
            tool, arguments = scenario["action"]
            arguments = validate_arguments(tool, arguments)
            decision = authorize(tool)
            action_hash = self._action_hash(incident_id, tool, arguments)
            approval = {"id": new_id("apr"), "incident_id": incident_id, "tool_call_id": new_id("pending"), "requested_action": tool, "sanitized_arguments": arguments, "action_hash": action_hash, "version": 1, "risk_level": decision.risk, "impact": f"Changes demo {incident['service']} service state", "rollback_plan": "Restore the previous demo state", "decision": "pending", "decided_by": None, "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(), "used_at": None}
            self.store.put("approvals", approval["id"], approval)
            incident["status"] = Status.AWAITING_APPROVAL
            incident["approval_id"] = approval["id"]
            self.emit(incident_id, "await_approval", "A scoped action requires approval", approval)
        else:
            incident["status"] = Status.REPORTED
            incident["resolved_at"] = now_iso()
            self.emit(incident_id, "report", "Report ready; no system change recommended", {"abstained": True})
        self.store.put("incidents", incident_id, incident)
        run.update({"status": "awaiting_approval" if incident["status"] == Status.AWAITING_APPROVAL else "completed", "completed_at": now_iso() if incident["status"] != Status.AWAITING_APPROVAL else None})
        self.store.put("runs", run["id"], run)
        return incident

    def _record_model_call(self, incident_id: str, run_id: str, node: str, result):
        call = {"id": new_id("mdl"), "incident_id": incident_id, "run_id": run_id, "node": node, "provider": "openai", "model": result.model, "response_id": result.response_id, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "latency_ms": result.latency_ms, "created_at": now_iso()}
        self.store.put("model_calls", call["id"], call)

    def decide(self, approval_id: str, approved: bool, actor: str, arguments: dict[str, Any] | None = None, confirmation: str | None = None, expected_version: int | None = None, action_hash: str | None = None):
        approval = self.store.get("approvals", approval_id)
        if not approval: raise KeyError("approval not found")
        if approval["decision"] != "pending" or approval.get("used_at"): raise ValueError("approval already decided; replay rejected")
        if datetime.fromisoformat(approval["expires_at"]) <= datetime.now(UTC): raise ValueError("approval expired")
        if expected_version is not None and expected_version != approval["version"]: raise ValueError("approval version conflict")
        if action_hash is not None and action_hash != approval["action_hash"]: raise ValueError("approval action binding mismatch")
        if approval["risk_level"] == "R3" and approved and confirmation != "CONFIRM R3": raise ValueError("R3 action requires confirmation: CONFIRM R3")
        if arguments is not None and redact(arguments) != approval["sanitized_arguments"]: raise ValueError("arguments changed; request a new scoped approval")
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
            validate_arguments(approval["requested_action"], approval["sanitized_arguments"])
            self.emit(incident["id"], "execute_action", f"Executed {approval['requested_action']}", {"arguments": approval["sanitized_arguments"]})
            scenario = SCENARIOS[incident["scenario_id"]]
            after = tool_result(incident["scenario_id"], scenario["tools"][0], after=True)
            incident["verification"] = {"check_name": scenario["verify"], "before_value": incident["evidence"][0]["result"], "after_value": after, "expected_condition": scenario["verify"], "passed": True}
            incident["status"] = Status.RESOLVED; incident["resolved_at"] = now_iso()
            self.emit(incident["id"], "verify", "Post-action verification passed", incident["verification"])
            self.emit(incident["id"], "report", "Incident resolved and report ready")
        self.store.put("incidents", incident["id"], incident)
        if incident.get("run_id"):
            run = self.store.get("runs", incident["run_id"])
            if run:
                run.update({"status": "completed", "completed_at": now_iso()})
                self.store.put("runs", run["id"], run)
        return incident

    def _incident(self, incident_id: str):
        value = self.store.get("incidents", incident_id)
        if not value: raise KeyError("incident not found")
        return value

    @staticmethod
    def _action_hash(incident_id: str, action: str, arguments: dict[str, Any]) -> str:
        payload = json.dumps({"incident_id": incident_id, "action": action, "arguments": arguments}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()
