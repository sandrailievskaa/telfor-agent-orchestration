import json
from pathlib import Path
import jsonschema

SCHEMA = json.loads(Path("contracts/netbox_check.schema.json").read_text())


def check(netbox_output: dict) -> dict:
    """Structural проверка на netbox_check резултатот.

    Semantic проверка (дали overlap_found навистина одговара на постоечките
    subnet-и во NetBox) не е применлива додека netbox_check_node е mock stub -
    види коментар во langgraph-poc/graph_v1.py.
    """
    errors = []
    try:
        jsonschema.validate(netbox_output, SCHEMA)
    except jsonschema.ValidationError as e:
        return {"passed": False, "errors": [f"schema_error: {e.message}"]}
    return {"passed": len(errors) == 0, "errors": errors}
