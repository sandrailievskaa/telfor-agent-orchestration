"""FastAPI wrapper околу guardrails/*.py check() функциите.

Овозможува n8n (и подоцна Langflow), кои комуницираат преку HTTP наместо
директен Python import, да ја користат ИСТАТА guardrail логика како
LangGraph - фер споредба меѓу платформите (иста shared логика, различен
orchestration слој). Не преизмислува guardrail логика - секој endpoint само
повикува постоечка check() функција од guardrails/.

Стартувај со: uvicorn mock-services.guardrail_api:app --port 9100
(одделен port од mock_firewall.py кој е на 9000).
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from guardrails.check_intent_parser import check as check_intent
from guardrails.check_validator import check as check_validator
from guardrails.check_netbox import check as check_netbox
from guardrails.check_policy import check as check_policy
from guardrails.check_planner import check as check_planner
from guardrails.check_verifier import check as check_verifier

app = FastAPI(title="Guardrail API", description="HTTP wrapper за guardrails/*.py (n8n/Langflow)")


@app.post("/check/intent_parser")
def check_intent_parser_endpoint(payload: dict):
    return check_intent(payload)


@app.post("/check/validator")
def check_validator_endpoint(payload: dict):
    return check_validator(payload)


@app.post("/check/netbox")
def check_netbox_endpoint(payload: dict):
    return check_netbox(payload)


class PolicyCheckRequest(BaseModel):
    policy_result: dict
    source_subnet: Optional[str] = None
    dest_port: Optional[int] = None


@app.post("/check/policy")
def check_policy_endpoint(req: PolicyCheckRequest):
    return check_policy(req.policy_result, source_subnet=req.source_subnet, dest_port=req.dest_port)


@app.post("/check/planner")
def check_planner_endpoint(payload: dict):
    return check_planner(payload)


class VerifierCheckRequest(BaseModel):
    verify_result: dict
    expected_rule: Optional[dict] = None


@app.post("/check/verifier")
def check_verifier_endpoint(req: VerifierCheckRequest):
    return check_verifier(req.verify_result, expected_rule=req.expected_rule)
