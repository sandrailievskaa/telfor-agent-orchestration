import re, json

def strip_markdown_fences(text: str) -> str:
    """Ги вадам JSON fences и од стрингови што содржат вишок текст пред/по
    fence-от (пр. qwen2.5:7b понекогаш додава markdown образложение по
    затворената ``` fence - non-anchored search го фаќа ова, за разлика од
    претходната ^...$ верзија која бараше fence-от да е целиот стринг)."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    return match.group(1) if match else text

def safe_json_parse(raw_text: str) -> dict:
    cleaned = strip_markdown_fences(raw_text)
    return json.loads(cleaned)