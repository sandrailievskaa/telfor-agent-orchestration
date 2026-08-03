import json
from pathlib import Path
import jsonschema

SCHEMA = json.loads(Path("contracts/validator.schema.json").read_text())

def check(llm_output: dict) -> dict:
    errors = []
    try:
        jsonschema.validate(llm_output, SCHEMA)
    except jsonschema.ValidationError as e:
        return {"passed": False, "errors": [f"schema_error: {e.message}"]}
    return {"passed": len(errors) == 0, "errors": errors}