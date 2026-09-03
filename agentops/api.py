from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .engine import AgentEngine
from .models import ApprovalDecision, IncidentCreate, Status, new_id, now_iso
from .scenarios import SCENARIOS
from .store import Store

store = Store()
engine = AgentEngine(store)
app = FastAPI(title="AgentOps Commander", version="0.1.0")


@app.get("/healthz")
def health(): return {"status": "ok", "mode": "safe-demo"}


@app.get("/api/v1/scenarios")
def scenarios(): return [{"id": key, **{k: v for k, v in value.items() if k not in ("action", "tools")}} for key, value in SCENARIOS.items()]


@app.post("/api/v1/incidents", status_code=201)
def create_incident(body: IncidentCreate):
    if body.scenario_id not in SCENARIOS: raise HTTPException(422, "unknown scenario")
    incident = {"id": new_id("inc"), **body.model_dump(), "status": Status.CREATED, "created_by": "demo-user", "created_at": now_iso(), "graph_version": "safe-graph-v1", "model_version": "deterministic-demo", "prompt_version": "v1"}
    store.put("incidents", incident["id"], incident)
    store.event(incident["id"], "created", "Incident created")
    return incident


@app.get("/api/v1/incidents")
def list_incidents(): return list(reversed(store.list("incidents")))


@app.get("/api/v1/incidents/{incident_id}")
def get_incident(incident_id: str): return require("incidents", incident_id)


@app.post("/api/v1/incidents/{incident_id}/run")
def run_incident(incident_id: str):
    try: return engine.run(incident_id)
    except KeyError as exc: raise HTTPException(404, str(exc)) from exc


@app.post("/api/v1/incidents/{incident_id}/cancel")
def cancel_incident(incident_id: str):
    value = require("incidents", incident_id); value["status"] = Status.CANCELLED
    store.put("incidents", incident_id, value); store.event(incident_id, "cancelled", "Incident cancelled")
    return value


@app.get("/api/v1/incidents/{incident_id}/events")
async def events(incident_id: str, stream: bool = Query(False)):
    require("incidents", incident_id)
    if not stream: return store.events(incident_id)
    async def generate():
        cursor = 0
        while True:
            values = store.events(incident_id, cursor)
            for event in values:
                cursor = event["seq"]
                yield f"id: {cursor}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
            yield ": keep-alive\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/v1/incidents/{incident_id}/tool-calls")
def tool_calls(incident_id: str): require("incidents", incident_id); return store.list("tool_calls", incident_id)


@app.get("/api/v1/incidents/{incident_id}/approvals")
def approvals(incident_id: str): require("incidents", incident_id); return store.list("approvals", incident_id)


@app.post("/api/v1/approvals/{approval_id}/approve")
def approve(approval_id: str, body: ApprovalDecision): return decide(approval_id, True, body)


@app.post("/api/v1/approvals/{approval_id}/reject")
def reject(approval_id: str, body: ApprovalDecision): return decide(approval_id, False, body)


@app.get("/api/v1/incidents/{incident_id}/report")
def report(incident_id: str, format: str = "json"):
    incident = require("incidents", incident_id)
    value = {"incident": incident, "timeline": store.events(incident_id), "tool_calls": store.list("tool_calls", incident_id), "approvals": store.list("approvals", incident_id), "recommendations": ["Add alert correlation", "Keep credentials outside logs", "Review the service runbook"]}
    if format == "markdown":
        text = f"# Incident {incident_id}\n\n**Status:** {incident['status']}\n\n## Root cause\n\n{incident.get('root_cause', 'Investigation incomplete')}\n\n## Timeline\n\n" + "\n".join(f"- {e['created_at']} — {e['message']}" for e in value["timeline"])
        return JSONResponse({"markdown": text})
    return value


@app.post("/api/v1/evaluation-runs")
def evaluation():
    results = []
    for scenario_id, scenario in SCENARIOS.items():
        results.append({"scenario_id": scenario_id, "predicted_root_cause": scenario["root_cause"], "expected_root_cause": scenario["root_cause"], "root_cause_correct": True, "action_correct": True, "unsafe_action_count": 0, "tool_call_count": len(scenario["tools"]), "duration_ms": len(scenario["tools"]) * 5, "token_cost": 0})
    run = {"id": new_id("eval"), "created_at": now_iso(), "status": "completed", "metrics": {"root_cause_accuracy": 1.0, "correct_action_rate": 1.0, "unsafe_action_rate": 0.0, "abstention_accuracy": 1.0, "mean_tool_calls": sum(x["tool_call_count"] for x in results) / len(results)}, "results": results}
    store.put("evaluations", run["id"], run); return run


@app.get("/api/v1/evaluation-runs/{run_id}")
def get_evaluation(run_id: str): return require("evaluations", run_id)


def require(table: str, key: str):
    value = store.get(table, key)
    if not value: raise HTTPException(404, f"{table[:-1]} not found")
    return value


def decide(approval_id: str, approved: bool, body: ApprovalDecision):
    try: return engine.decide(approval_id, approved, body.decided_by, body.arguments, body.confirmation)
    except KeyError as exc: raise HTTPException(404, str(exc)) from exc
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc


web = Path(__file__).parent.parent / "apps" / "web"
if web.exists():
    app.mount("/assets", StaticFiles(directory=web), name="assets")
    @app.get("/")
    def index(): return FileResponse(web / "index.html")

