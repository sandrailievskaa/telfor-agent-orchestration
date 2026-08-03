import json
from pathlib import Path
import jsonschema

SCHEMA = json.loads(Path("contracts/verifier.schema.json").read_text())

FIELDS_TO_MATCH = ["source_subnet", "dest_subnet", "dest_port", "protocol"]


def check(verify_output: dict, expected_rule: dict = None) -> dict:
    errors = []
    try:
        jsonschema.validate(verify_output, SCHEMA)
    except jsonschema.ValidationError as e:
        return {"passed": False, "errors": [f"schema_error: {e.message}"]}

    if expected_rule is not None:
        if not verify_output.get("exists"):
            errors.append("rule_not_found_after_apply")
        else:
            actual_rule = verify_output.get("rule") or {}
            for field in FIELDS_TO_MATCH:
                if actual_rule.get(field) != expected_rule.get(field):
                    errors.append(
                        f"field_mismatch:{field} expected={expected_rule.get(field)!r} "
                        f"actual={actual_rule.get(field)!r}"
                    )

    return {"passed": len(errors) == 0, "errors": errors}
