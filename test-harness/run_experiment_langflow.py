"""10x-репетиционен стабилност harness за Langflow.

ВАЖНО ОГРАНИЧУВАЊЕ (експлицитна одлука по консултација - dev_notes.md
Наод #45): за разлика од LangGraph/n8n harness-ите, овој НЕ го тестира
целиот 10-чекорен pipeline со варирачки test intent. Причина: во Langflow,
чекори 1-6 (intent_parser...dry_run) постојат како ОДДЕЛНИ изолирани
тест-синџири на canvas-от (секој независно верифициран - Наод #37-40),
не се меѓусебно поврзани. Само чекори 7-10 (HumanInput -> apply -> verify
-> conditional rollback) се реално поврзани во еден pipeline (Наод
#42/43). Целосно поврзување на чекори 1-6 со 7-10 би барало ~6
нетривијални работни блока (intent-JSON reformat за секој LLM prompt,
policy/verify wrap-query rebuild преку jq string-builder, HumanInput
prompt rebuild) - надвор од рамки на TELFOR рокот (4 октомври).

Затоа овој harness ја мери САМО инфраструктурната стабилност на чекори
7-10 (human-in-the-loop pause/resume преку /api/v2/workflows + real
apply/verify/rollback ефекти) - НЕ LLM/guardrail стабилноста низ целиот
pipeline (тоа веќе е мерено за LangGraph/n8n). Chapters 7-10 немаат LLM
повик воопшто (HumanInput promptот е статичен текст, apply/verify/
rollback се чисто структурни HTTP повици + детерминистичка
check_verifier.py guardrail проверка) - значи нема очекувана model-
стохастичност овде; целта е да се потврди дека Langflow-овата
suspend/resume инфраструктура (v2 API) е доследно стабилна низ
повторувања, не да се мери LLM halucinacija-стапка.

Секое повторување: старт преку /api/v2/workflows (start_component_id=
HumanInput-approve7, без stop_component_id - Наод #42 Под-наод Б), потврда
на suspended статус, resume со decision=approve (истиот "auto-approve"
принцип како LangGraph-овиот `approve_callback=lambda: True` и n8n-овиот
decision=approve default), потврда на финален резултат преку build events
(ConditionalRouter-apply7/verify9/rollback10 True/False резултати) плус
независна потврда преку mock_firewall.log (број на нови /rules/apply,
GET /rules/{id}, DELETE /rules/{id} повици).
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

from run_experiment import N_RUNS, OUTPUT_PATH, CSV_FIELDS  # noqa: E402


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
LANGFLOW_HEADERS = {"x-api-key": ENV["LANGFLOW_API_KEY"]}

PLATFORM = "langflow"
MODEL_NAME = "n/a (chapters 7-10 have no LLM call)"
FLOW_ID = "d043123e-3822-4101-a9c1-704df35e2269"
LANGFLOW_BASE_URL = ENV.get("LANGFLOW_BASE_URL", "http://127.0.0.1:7860")
HUMAN_INPUT_NODE = "HumanInput-approve7"
INTENT_LABEL = "human_approval_gate_static"  # see module docstring: not varied per test intent
POLL_INTERVAL_SEC = 3
POLL_TIMEOUT_SEC = 300


def _post_v2_run() -> str:
    r = requests.post(
        f"{LANGFLOW_BASE_URL}/api/v2/workflows",
        headers=LANGFLOW_HEADERS,
        json={
            "flow_id": FLOW_ID,
            "mode": "background",
            "start_component_id": HUMAN_INPUT_NODE,
        },
    )
    r.raise_for_status()
    return r.json()["job_id"]


def _poll_status(job_id: str, timeout=POLL_TIMEOUT_SEC) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{LANGFLOW_BASE_URL}/api/v2/workflows", headers=LANGFLOW_HEADERS, params={"job_id": job_id})
        r.raise_for_status()
        body = r.json()
        if body["status"] != "in_progress" and body["status"] != "queued":
            return body
        time.sleep(POLL_INTERVAL_SEC)
    raise TimeoutError(f"Langflow job {job_id} did not settle within {timeout}s")


def _get_pending_request_id(job_id: str) -> str:
    r = requests.get(f"{LANGFLOW_BASE_URL}/api/v2/workflows/pending", headers=LANGFLOW_HEADERS, params={"flow_id": FLOW_ID})
    r.raise_for_status()
    for row in r.json():
        if row["job_id"] == job_id:
            return row["request_id"]
    raise RuntimeError(f"No pending HITL request found for job {job_id}")


def _resume(job_id: str, request_id: str, action_id: str = "approve"):
    r = requests.post(
        f"{LANGFLOW_BASE_URL}/api/v2/workflows/{job_id}/resume",
        headers=LANGFLOW_HEADERS,
        json={"request_id": request_id, "decision": {"action_id": action_id}},
    )
    r.raise_for_status()
    return r.json()


MOCK_FIREWALL_LOG = os.path.join(os.environ.get("TEMP", "/tmp"), "mock_firewall.log")


def _tail_new_lines(log_path: str, before_count: int) -> list:
    if not os.path.exists(log_path):
        return []
    with io.open(log_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return lines[before_count:]


def _count_log_lines(log_path: str) -> int:
    if not os.path.exists(log_path):
        return 0
    with io.open(log_path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def _outcome_from_final_body(body: dict, new_log_lines: list) -> dict:
    if body["status"] == "failed" or body.get("errors"):
        return {
            "outcome": "error",
            "failed_at_step": f"langflow_errors: {body.get('errors')}",
            "guardrail_catches": 0,
        }

    # Наод #46: outputs dict keys are unreliable (grouped/terminal-node listing
    # doesn't consistently include every vertex that actually ran this pass -
    # already observed for approve/reject tests in Наод #42). The mock firewall's
    # own access log is the reliable, independent ground truth for which real
    # HTTP calls fired this run.
    has_apply = any("POST /rules/apply" in ln for ln in new_log_lines)
    has_get = any(" \"GET /rules/" in ln for ln in new_log_lines)
    has_delete = any("DELETE /rules/" in ln for ln in new_log_lines)

    if not has_apply:
        return {"outcome": "rejected_at_human_approval", "failed_at_step": "human_approval", "guardrail_catches": 0}
    if has_apply and has_get and has_delete:
        return {
            "outcome": "verification_failed_rolled_back",
            "failed_at_step": "verify",
            "guardrail_catches": 1,
        }
    if has_apply and has_get and not has_delete:
        return {"outcome": "ok", "failed_at_step": "none", "guardrail_catches": 0}

    return {
        "outcome": "unknown",
        "failed_at_step": f"log_lines_seen: {new_log_lines}",
        "guardrail_catches": 0,
    }


def run_once(run_number: int) -> dict:
    start = time.perf_counter()
    try:
        log_before = _count_log_lines(MOCK_FIREWALL_LOG)
        job_id = _post_v2_run()
        body = _poll_status(job_id)

        if body["status"] == "suspended":
            request_id = _get_pending_request_id(job_id)
            _resume(job_id, request_id, action_id="approve")
            body = _poll_status(job_id)

        new_log_lines = _tail_new_lines(MOCK_FIREWALL_LOG, log_before)
        analysis = _outcome_from_final_body(body, new_log_lines)
        duration = time.perf_counter() - start
        return {
            "platform": PLATFORM,
            "intent_id": INTENT_LABEL,
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
            "intent_id": INTENT_LABEL,
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
        for run_number in range(1, N_RUNS + 1):
            row = run_once(run_number)
            writer.writerow(row)
            f.flush()
            print(f"[langflow {INTENT_LABEL} run {run_number}/{N_RUNS}] "
                  f"outcome={row['outcome']} failed_at={row['failed_at_step']} "
                  f"catches={row['guardrail_catches']} dur={row['duration_sec']}s")
    print(f"\nЗачувано во {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
