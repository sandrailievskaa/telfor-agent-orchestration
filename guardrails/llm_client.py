"""Централна LLM конфигурација - MODEL_NAME и провајдер (Ollama наспроти
надворешен OpenAI-compatible API) на едно место, за да не треба да се менува
секој prompt повик поединечно при премин на нов модел/провајдер.

Подготовка за идна multi-model споредба (Llama3.3, Qwen, DeepSeek, GLM,
gpt-oss преку надворешен API) - види results/dev_notes.md.
"""
import os

MODEL_NAME = os.environ.get("LLM_MODEL", "qwen2.5:7b")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")


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
    raise NotImplementedError(
        "LLM_PROVIDER=external сеуште не е имплементиран - чека точен "
        "OpenAI-compatible API endpoint/token од менторката (пристап до "
        "Llama3.3/Qwen/DeepSeek/GLM/gpt-oss преку надворешен API, идна "
        "работа). Постави LLM_PROVIDER=ollama (default) за локално тестирање."
    )
