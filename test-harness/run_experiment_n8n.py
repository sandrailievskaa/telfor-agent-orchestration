"""10x-репетиционен стабилност harness за n8n (аналоген на run_experiment.py) -
го активира n8n workflow CwrkhftDrYNgl08c преку неговиот Webhook trigger
('TELFOR Test Webhook', POST /webhook/telfor-test-run), не преку browser
automation, користејќи ги истите TEST_INTENTS како LangGraph harness-от.

Human approval гејтот (чекор 7, Wait node) се auto-одобрува во сите
повторувања (decision=approve), аналогно на LangGraph-овиот
`approve_callback=lambda: True` - истата методолошка причина: се мери
стабилноста на LLM-агентите и guardrails-ите низ чекори 1-6 и 8-9, не
самата (детерминистичка) одлука.

Механизам (потврден рачно пред градба на овој скрипт - dev_notes.md Наод
#44): workflow-от се активира преку /webhook/telfor-test-run со
{"raw_request": "..."}, execution-от се следи преку n8n Public API
(GET /api/v1/executions/{id}), а Wait нодот (Resume: On Form Submitted)
се resume-ира преку POST до неговиот resumeFormUrl
(metadata.resumeFormUrl во execution run data) со multipart/form-data
поле "field-0" (внатрешниот submission key на формата - НЕ "decision",
кое е само display label).
"""
import csv
import io
import os
import sys
import time

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "test-harness"))

from run_experiment import TEST_INTENTS, N_RUNS, OUTPUT_PATH, CSV_FIELDS  # noqa: E402

PLATFORM = "n8n"
MODEL_NAME = "qwen2.5:7b"
WORKFLOW_ID = "CwrkhftDrYNgl08c"
WEBHOOK_URL = "http://127.0.0.1:5678/webhook/telfor-test-run"
RESUME_FIELD_KEY = "field-0"
POLL_INTERVAL_SEC = 5
POLL_TIMEOUT_SEC = 600


def load_env():
    env = {}
    with io.open(os.path.join(BASE_DIR, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


ENV = load_env()
N8N_BASE_URL = ENV["N8N_BASE_URL"]
HEADERS = {"X-N8N-API-KEY": ENV["N8N_API_KEY"]}

# Правилен редослед на guardrail-checked If nodes низ pipeline-от (Наод #44) -
# секој со свое парче од graph_v1.py-овиот статус-вокабулар, за directна
# споредливост со LangGraph/n8n резултатите во истиот CSV.
GUARDRAIL_IF_NODES = [
    ("If", "intent_parser", "rejected_at_intent_parser"),
    ("If1", "validator", "rejected_at_validator"),
    ("If2", "netbox", "rejected_at_netbox"),
    ("If3", "policy_checker", "rejected_at_policy_checker"),
    ("If4", "planner", "rejected_at_planner"),
    ("If5", "dry_run", "rejected_at_dry_run"),
    ("If7", "apply", "rejected_at_apply"),
    ("If8", "verify", "verification_failed"),
]


def _get_max_execution_id():
    r = requests.get(
        f"{N8N_BASE_URL}/api/v1/executions",
        headers=HEADERS,
        params={"workflowId": WORKFLOW_ID, "limit": 1},
    )
    r.raise_for_status()
    data = r.json()["data"]
    return int(data[0]["id"]) if data else 0


def _find_new_execution(after_id: int, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for status in ("running", "waiting", "success", "error"):
            r = requests.get(
                f"{N8N_BASE_URL}/api/v1/executions",
                headers=HEADERS,
                params={"workflowId": WORKFLOW_ID, "status": status, "limit": 5},
            )
            r.raise_for_status()
            for row in r.json()["data"]:
                if int(row["id"]) > after_id:
                    return int(row["id"])
        time.sleep(1)
    raise TimeoutError("New n8n execution did not appear in time")


def _poll_until_settled(execution_id: int, timeout=POLL_TIMEOUT_SEC):
    """Полира додека статусот не стане различен од 'running' (т.е. 'waiting',
    'success' или 'error')."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{N8N_BASE_URL}/api/v1/executions/{execution_id}", headers=HEADERS)
        r.raise_for_status()
        status = r.json()["status"]
        if status != "running":
            return status
        time.sleep(POLL_INTERVAL_SEC)
    raise TimeoutError(f"Execution {execution_id} did not settle within {timeout}s")


def _get_resume_url(execution_id: int) -> str:
    r = requests.get(
        f"{N8N_BASE_URL}/api/v1/executions/{execution_id}",
        headers=HEADERS,
        params={"includeData": "true"},
    )
    r.raise_for_status()
    run_data = r.json()["data"]["resultData"]["runData"]
    return run_data["Wait"][0]["metadata"]["resumeFormUrl"]


def _resume(execution_id: int, decision: str = "approve"):
    url = _get_resume_url(execution_id)
    r = requests.post(url, files={RESUME_FIELD_KEY: (None, decision)})
    r.raise_for_status()
    return r.json()


def _analyze(execution_id: int) -> dict:
    r = requests.get(
        f"{N8N_BASE_URL}/api/v1/executions/{execution_id}",
        headers=HEADERS,
        params={"includeData": "true"},
    )
    r.raise_for_status()
    body = r.json()
    result_data = body["data"]["resultData"]
    run_data = result_data["runData"]

    if body["status"] == "error":
        err = result_data.get("error", {})
        node_name = (err.get("node") or {}).get("name", result_data.get("lastNodeExecuted", "?"))
        return {
            "outcome": "error",
            "failed_at_step": f"exception: {node_name}: {err.get('message', '')}",
            "guardrail_catches": 0,
        }

    guardrail_catches = 0
    for node_name, step_name, rejected_status in GUARDRAIL_IF_NODES:
        run = run_data.get(node_name)
        if not run:
            continue
        branches = run[0].get("data", {}).get("main", [[], []])
        false_branch = branches[1] if len(branches) > 1 else []
        true_branch = branches[0] if len(branches) > 0 else []
        if false_branch:
            guardrail_catches += 1
            if step_name != "verify":
                return {
                    "outcome": rejected_status,
                    "failed_at_step": step_name,
                    "guardrail_catches": guardrail_catches,
                }
            # verify failed -> conditional rollback (If9) decides the final suffix
            if9 = run_data.get("If9")
            if if9:
                if9_branches = if9[0].get("data", {}).get("main", [[], []])
                rolled_back = bool(if9_branches[0]) if len(if9_branches) > 0 else False
                suffix = "_rolled_back" if rolled_back else "_rollback_failed"
            else:
                suffix = "_rollback_unknown"
            return {
                "outcome": rejected_status + suffix,
                "failed_at_step": step_name,
                "guardrail_catches": guardrail_catches,
            }

    if "Pipeline Success" in run_data:
        return {"outcome": "ok", "failed_at_step": "none", "guardrail_catches": guardrail_catches}

    # settled (not "error") but never reached a known guardrail If node nor
    # Pipeline Success - most likely stuck at/rejected during human_approval
    if "Wait" in run_data and "If6" in run_data:
        if6 = run_data["If6"][0].get("data", {}).get("main", [[], []])
        if len(if6) > 1 and if6[1]:
            return {
                "outcome": "rejected_at_human_approval",
                "failed_at_step": "human_approval",
                "guardrail_catches": guardrail_catches,
            }

    return {
        "outcome": "unknown",
        "failed_at_step": f"last_node: {result_data.get('lastNodeExecuted', '?')}",
        "guardrail_catches": guardrail_catches,
    }


def run_once(intent_id: str, raw_request: str, run_number: int) -> dict:
    start = time.perf_counter()
    try:
        before_id = _get_max_execution_id()
        resp = requests.post(WEBHOOK_URL, json={"raw_request": raw_request})
        resp.raise_for_status()

        execution_id = _find_new_execution(before_id)
        status = _poll_until_settled(execution_id)

        if status == "waiting":
            _resume(execution_id, decision="approve")
            status = _poll_until_settled(execution_id)

        analysis = _analyze(execution_id)
        duration = time.perf_counter() - start
        return {
            "platform": PLATFORM,
            "intent_id": intent_id,
            "run": run_number,
            "outcome": analysis["outcome"],
            "failed_at_step": analysis["failed_at_step"],
            "guardrail_catches": analysis["guardrail_catches"],
            "duration_sec": round(duration, 2),
            "model": MODEL_NAME,
        }
    except Exception as e:
        duration = time.perf_counter() - start
        return {
            "platform": PLATFORM,
            "intent_id": intent_id,
            "run": run_number,
            "outcome": "error",
            "failed_at_step": f"harness_exception: {type(e).__name__}: {e}",
            "guardrail_catches": 0,
            "duration_sec": round(duration, 2),
            "model": MODEL_NAME,
        }


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not OUTPUT_PATH.exists()
    with io.open(OUTPUT_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        for intent in TEST_INTENTS:
            for run_number in range(1, N_RUNS + 1):
                row = run_once(intent["intent_id"], intent["raw_request"], run_number)
                writer.writerow(row)
                f.flush()
                print(f"[n8n {intent['intent_id']} run {run_number}/{N_RUNS}] "
                      f"outcome={row['outcome']} failed_at={row['failed_at_step']} "
                      f"catches={row['guardrail_catches']} dur={row['duration_sec']}s")
    print(f"\nЗачувано во {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
