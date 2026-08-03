import re, json

def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return match.group(1) if match else text

def safe_json_parse(raw_text: str) -> dict:
    cleaned = strip_markdown_fences(raw_text)
    return json.loads(cleaned)