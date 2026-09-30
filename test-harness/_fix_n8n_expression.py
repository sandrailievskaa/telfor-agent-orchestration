"""ЕДНОКРАТНА поправка на бугот од _patch_n8n_webhook.py: 'Basic LLM Chain'-овото
'text' поле беше сменето во ЦЕЛОСЕН JS израз (=... + (тернарен израз) ...),
но n8n LangChain nodes го евалуираат "text" полето со ВГРАДЕНИ {{ }} mustache
изрази во рамки на статичен текст - НЕ целото поле како еден голем JS израз.
Резултат: LLM-от го добил буквалниот JS код како prompt текст (потврдено во
execution #49/#50 - 'inputOverride' покажува дека Ollama го примил буквалниот
'"Барање: " + ($json.body && ...)' стринг, не евалуирана вредност).

Поправка: истиот "=" префикс, но со {{ }} mustache-израз вметнат САМО за
динамичкиот дел, а статичниот preamble текст останува буквален.
"""
import io
import json
import os

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    chain_node = next(n for n in wf["nodes"] if n["name"] == "Basic LLM Chain")

    default_tail_js_literal = json.dumps(DEFAULT_TAIL)  # JS string literal
    mustache_expr = (
        "{{ $json.body && $json.body.raw_request ? $json.body.raw_request : "
        + default_tail_js_literal + " }}"
    )
    new_text = "=" + STATIC_PREAMBLE + mustache_expr
    chain_node["parameters"]["text"] = new_text

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
    print("Fixed OK.")


if __name__ == "__main__":
    main()
