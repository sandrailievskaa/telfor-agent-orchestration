from fastapi import FastAPI
from pydantic import BaseModel
import uuid

app = FastAPI()
RULES_DB = {}

class Rule(BaseModel):
    source_subnet: str
    dest_subnet: str
    dest_port: int
    protocol: str

@app.post("/rules/dry-run")
def dry_run(rule: Rule):
    return {"simulation_ok": True, "would_create": rule.dict()}

@app.post("/rules/apply")
def apply_rule(rule: Rule):
    rule_id = str(uuid.uuid4())
    RULES_DB[rule_id] = rule.dict()
    return {"applied": True, "rule_id": rule_id}

@app.get("/rules/{rule_id}")
def verify(rule_id: str):
    return {"exists": rule_id in RULES_DB, "rule": RULES_DB.get(rule_id)}

@app.delete("/rules/{rule_id}")
def rollback(rule_id: str):
    existed = RULES_DB.pop(rule_id, None) is not None
    return {"rolled_back": existed}