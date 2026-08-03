import json, ipaddress
from pathlib import Path
import jsonschema

SCHEMA = json.loads(Path("contracts/policy_checker.schema.json").read_text())

WIDE_SUBNET_PREFIXLEN_THRESHOLD = 16  # prefixlen < 16 = "поширок од /16"
SENSITIVE_PORTS = {22, 23, 3389}


def _ground_truth(source_subnet: str, dest_port: int) -> dict:
    """Независна, детерминистичка пресметка на фактите - НЕ се потпира на LLM тврдења."""
    truth = {"is_wide_subnet": None, "is_sensitive_port": None, "cidr_error": None}
    try:
        net = ipaddress.ip_network(source_subnet, strict=False)
        truth["is_wide_subnet"] = net.prefixlen < WIDE_SUBNET_PREFIXLEN_THRESHOLD
    except ValueError as e:
        truth["cidr_error"] = str(e)
    truth["is_sensitive_port"] = dest_port in SENSITIVE_PORTS
    return truth


def check(llm_output: dict, source_subnet: str = None, dest_port: int = None) -> dict:
    errors = []
    try:
        jsonschema.validate(llm_output, SCHEMA)
    except jsonschema.ValidationError as e:
        return {"passed": False, "errors": [f"schema_error: {e.message}"]}

    if llm_output.get("risk_level") == "high" and llm_output.get("policy_pass") is True:
        errors.append("inconsistent_high_risk_but_passed")

    # Semantic check: независна пресметка наспроти LLM тврдење (не потпирај се на LLM за CIDR/port факти).
    # Промптот дефинира ТОЧНО два услови за risk_level=="high" - затоа ground truth е
    # авторитативна дури и кога моделот наведува (можеби халуцинирани) violations како причина.
    if source_subnet is not None and dest_port is not None:
        truth = _ground_truth(source_subnet, dest_port)
        risk_level = llm_output.get("risk_level")
        violations = llm_output.get("violations", [])

        if truth["cidr_error"]:
            errors.append(f"invalid_source_subnet: {truth['cidr_error']}")

        should_be_high = bool(truth["is_wide_subnet"]) or bool(truth["is_sensitive_port"])

        if should_be_high and risk_level != "high":
            reasons = []
            if truth["is_wide_subnet"]:
                reasons.append(f"source_subnet wider than /{WIDE_SUBNET_PREFIXLEN_THRESHOLD}")
            if truth["is_sensitive_port"]:
                reasons.append(f"dest_port {dest_port} is in sensitive port list {sorted(SENSITIVE_PORTS)}")
            errors.append(
                "risk_level_understated: model said '" + str(risk_level) +
                "' but ground truth requires 'high' (" + "; ".join(reasons) + ")"
            )

        if not should_be_high and risk_level == "high":
            errors.append(
                "risk_level_overstated_hallucinated: model flagged 'high' risk with violations="
                f"{violations!r}, but ground truth shows source_subnet is NOT wider than "
                f"/{WIDE_SUBNET_PREFIXLEN_THRESHOLD} and dest_port {dest_port} is NOT in the "
                f"sensitive list {sorted(SENSITIVE_PORTS)} - the prompt defines no other 'high' "
                "condition, so this claim is unsupported"
            )

    return {"passed": len(errors) == 0, "errors": errors}
