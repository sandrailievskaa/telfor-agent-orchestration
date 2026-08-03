import json, ipaddress
from pathlib import Path
import jsonschema

SCHEMA = json.loads(Path("contracts/intent_parser.schema.json").read_text())

def check(llm_output: dict) -> dict:
    errors = []
    try:
        jsonschema.validate(llm_output, SCHEMA)
    except jsonschema.ValidationError as e:
        return {"passed": False, "errors": [f"schema_error: {e.message}"]}

    try:
        src = ipaddress.ip_network(llm_output["source_subnet"], strict=False)
        ipaddress.ip_network(llm_output["dest_subnet"], strict=False)
        if src.prefixlen == 0:
            errors.append("source_subnet_too_broad")
    except ValueError as e:
        errors.append(f"invalid_cidr: {e}")

    if llm_output.get("confidence", 0) < 0.6:
        errors.append("low_confidence_flag_for_human_review")

    return {"passed": len(errors) == 0, "errors": errors}