"""Централна LLM конфигурација - MODEL_NAME и провајдер (Ollama наспроти
надворешен OpenAI-compatible API) на едно место, за да не треба да се менува
секој prompt повик поединечно при премин на нов модел/провајдер.

Подготовка за идна multi-model споредба (Llama3.3, Qwen, DeepSeek, GLM,
gpt-oss преку надворешен API) - види results/dev_notes.md.
"""
import os
import requests

MODEL_NAME = os.environ.get("LLM_MODEL", "qwen2.5:7b")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")

# PCSS AI HUB (https://llm.hpc.pcss.pl/) - LiteLLM/OpenAI-compatible endpoint,
# пристап обезбеден од Roman Lapacz (PCSS) за multi-model споредба (results/
# dev_notes.md). Токенот се чита од .env (PCSS_API_KEY), никогаш hardcoded.
PCSS_BASE_URL = os.environ.get("PCSS_BASE_URL", "https://llm.hpc.psnc.pl")
PCSS_API_KEY = os.environ.get("PCSS_API_KEY")


def call_llm(prompt: str) -> str:
    """Испраќа prompt до конфигурираниот LLM (JSON output mode) и го враќа
    суровиот текстуален одговор - НЕ е parsed, повикувачот треба да користи
    safe_json_parse() од guardrails/common.py."""
    if LLM_PROVIDER == "ollama":
        return _call_ollama(prompt)
    if LLM_PROVIDER == "external":
        return _call_external(prompt)
    raise ValueError(f"Непознат LLM_PROVIDER={LLM_PROVIDER!r} (очекувано 'ollama' или 'external')")


def _call_ollama(prompt: str) -> str:
    import ollama
    response = ollama.chat(model=MODEL_NAME, messages=[{"role": "user", "content": prompt}], format="json")
    return response["message"]["content"]


def _call_external(prompt: str) -> str:
    """LLM_PROVIDER=external - PCSS AI HUB, OpenAI-compatible /v1/chat/completions.

    MODEL_NAME (LLM_MODEL env var) мора да биде точен PCSS model id, пр.
    "GLM-5.1", "Qwen2.5:72b", "DeepSeek-V3.1" (потврдени преку GET /v1/models
    со истиот токен - results/dev_notes.md). Наменски е избрана "една верзија
    постара" од largest/newest варијантата за секое семејство (GLM-5.1 наместо
    5.2, DeepSeek-V3.1 наместо V4-Flash) - менторско упатство дека
    најголемите/најновите модели се почесто преоптоварени.
    """
    if not PCSS_API_KEY:
        raise RuntimeError(
            "PCSS_API_KEY не е поставен во .env - потребен за LLM_PROVIDER=external"
        )
    response = requests.post(
        f"{PCSS_BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {PCSS_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
