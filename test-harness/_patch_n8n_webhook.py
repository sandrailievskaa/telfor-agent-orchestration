"""ЕДНОКРАТЕН скрипт - додава Webhook trigger node паралелно на постоечкиот
Manual Trigger во n8n workflow CwrkhftDrYNgl08c, за да овозможи програмско
активирање (POST со {"raw_request": "..."}), без да го допира постоечкото
интерактивно Manual Trigger однесување.

Не менува ништо друго во workflow-от - само:
1. Додава нов n8n-nodes-base.webhook нод (POST /webhook/telfor-test-run,
   responseMode: onReceived - веднаш одговара, не чека workflow да заврши,
   бидејќи workflow-от содржи Wait node за human approval).
2. Го врзува новиот Webhook нод кон "Basic LLM Chain" (истиот target како
   постојниот Manual Trigger - паралелен влез).
3. Го менува "Basic LLM Chain"-овото 'text' поле од статичен string во
   n8n expression (леден "=" префикс) кое го користи $json.body.raw_request
   од webhook повикот ако постои, инаку паѓа назад на истиот хардкодиран
   текст (за да не се скрши постојното Manual Trigger рачно тестирање).

Стартувај само еднаш: python test-harness/_patch_n8n_webhook.py
"""
import io
import json
import os
import uuid

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env():
    env = {}
    path = os.path.join(BASE_DIR, ".env")
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


ENV = load_env()
N8N_BASE_URL = ENV["N8N_BASE_URL"]
N8N_API_KEY = ENV["N8N_API_KEY"]
WORKFLOW_ID = "CwrkhftDrYNgl08c"
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

STATIC_PREAMBLE = (
    "Извади ги полињата од барањето и врати ГИ САМО во JSON, без друг текст.\n\n"
    "confidence треба да е број од 0 до 1 кој покажува колку си сигурен дека точно "
    "си ги извадил вредностите:\n"
    "- 1.0 = сите вредности се експлицитно наведени во барањето и нема двосмисленост\n"
    "- 0.5 = некои вредности недостасуваат или се претпоставени\n"
    "- 0.0 = не можеш воопшто да ги извадиш податоците\n\n"
    "Формат:\n"
    '{"source_subnet":"...","dest_subnet":"...","dest_port":0,"protocol":"tcp|udp|icmp","confidence":0.0}\n\n'
    "Барање: "
)
DEFAULT_TAIL = "Дозволи пристап од 10.0.5.0/24 до 10.0.10.15 на порт 443 преку TCP."


def main():
    r = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=HEADERS)
    r.raise_for_status()
    wf = r.json()

    # 0. sanity: confirm the exact static text we expect is present before touching it
    chain_node = next(n for n in wf["nodes"] if n["name"] == "Basic LLM Chain")
    current_text = chain_node["parameters"]["text"]
    expected_full = STATIC_PREAMBLE + DEFAULT_TAIL
    if current_text != expected_full:
        raise SystemExit(
            "ABORT: 'Basic LLM Chain' text field does not match the expected hardcoded "
            "value - refusing to patch blind. Inspect manually first."
        )

    # 1. add the Webhook node (parallel entry point)
    webhook_id = str(uuid.uuid4())
    webhook_node = {
        "parameters": {
            "httpMethod": "POST",
            "path": "telfor-test-run",
            "responseMode": "onReceived",
            "options": {},
        },
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [0, -96],
        "id": webhook_id,
        "name": "TELFOR Test Webhook",
    }
    wf["nodes"].append(webhook_node)

    # 2. wire it to "Basic LLM Chain" (parallel to the Manual Trigger's own connection)
    wf["connections"]["TELFOR Test Webhook"] = {
        "main": [[{"node": "Basic LLM Chain", "type": "main", "index": 0}]]
    }

    # 3. make the prompt text an expression: use webhook body raw_request if present,
    #    else fall back to the exact original hardcoded value (keeps Manual Trigger intact)
    preamble_json = json.dumps(STATIC_PREAMBLE)  # JS string literal, safely escaped
    default_tail_json = json.dumps(DEFAULT_TAIL)
    expression = (
        "=" + preamble_json + " + "
        "($json.body && $json.body.raw_request ? $json.body.raw_request : " + default_tail_json + ")"
    )
    chain_node["parameters"]["text"] = expression

    # PUT the updated workflow back. n8n's update endpoint only accepts a subset of
    # fields - send name/nodes/connections/settings, matching what GET returned minus
    # read-only metadata.
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
    }
    r2 = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=HEADERS, json=payload)
    if not r2.ok:
        print("PUT failed:", r2.status_code, r2.text[:1000])
        r2.raise_for_status()

    print("Patched OK. Webhook node id:", webhook_id)

    # 4. activate so the production webhook path actually listens without UI "Listen" click
    r3 = requests.post(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}/activate", headers=HEADERS)
    print("Activate status:", r3.status_code, r3.text[:300])


if __name__ == "__main__":
    main()
