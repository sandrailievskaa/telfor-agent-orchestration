from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict
import sys, requests, uuid
sys.path.append(".")
from guardrails.common import safe_json_parse
from guardrails.llm_client import call_llm, MODEL_NAME
from guardrails.check_intent_parser import check as check_intent
from guardrails.check_policy import check as check_policy
from guardrails.check_validator import check as check_validator
from guardrails.check_planner import check as check_planner
from guardrails.check_netbox import check as check_netbox
from guardrails.check_verifier import check as check_verifier

FIREWALL_URL = "http://localhost:9000"


class GraphState(TypedDict):
    raw_request: str
    parsed_intent: dict
    validation_result: dict
    netbox_result: dict
    policy_result: dict
    plan_result: dict
    dry_run_result: dict
    apply_result: dict
    verify_result: dict
    rollback_result: dict
    guardrail_log: list
    status: str


def intent_parser_node(state: GraphState) -> GraphState:
    prompt = f"""Извади ги полињата од барањето и врати ГИ САМО во JSON, без друг текст.

confidence треба да е број од 0 до 1 кој покажува колку си сигурен дека точно си ги извадил вредностите:
- 1.0 = сите вредности се експлицитно наведени во барањето и нема двосмисленост
- 0.5 = некои вредности недостасуваат или се претпоставени
- 0.0 = не можеш воопшто да ги извадиш податоците

Формат:
{{"source_subnet":"...","dest_subnet":"...","dest_port":0,"protocol":"tcp|udp|icmp","confidence":0.0}}

Барање: {state['raw_request']}"""
    state["parsed_intent"] = safe_json_parse(call_llm(prompt))
    return state


def guardrail_intent_node(state: GraphState) -> GraphState:
    result = check_intent(state["parsed_intent"])
    state["guardrail_log"].append({"step": "intent_parser", **result})
    state["status"] = "ok" if result["passed"] else "rejected_at_intent_parser"
    return state


def validator_node(state: GraphState) -> GraphState:
    intent = state["parsed_intent"]
    prompt = f"""Провери дали ова мрежно правило е логички и синтаксно правилно и врати ГИ САМО во JSON:
{{"is_valid": true/false, "errors": ["..."]}}

Правило: {intent['source_subnet']} -> {intent['dest_subnet']}:{intent['dest_port']}/{intent['protocol']}

Провери: дали протоколот е соодветен за портот, дали subnet опсезите се смислени (не се исти, не се празни)."""
    state["validation_result"] = safe_json_parse(call_llm(prompt))
    return state


def guardrail_validator_node(state: GraphState) -> GraphState:
    result = check_validator(state["validation_result"])
    state["guardrail_log"].append({"step": "validator", **result})
    if state["status"] == "ok":
        structural_ok = result["passed"]
        business_ok = state["validation_result"].get("is_valid", False)
        if not structural_ok:
            state["status"] = "rejected_at_validator_structure"
        elif not business_ok:
            state["status"] = "rejected_at_validator_invalid"
    return state


def netbox_check_node(state: GraphState) -> GraphState:
    """PRIVREMEN MOCK STUB: NetBox е недостапен на dev машината (WSL2 kernel
    проблем - `wsl --update` фаќа грешка "service cannot be started").
    Замени со вистински API повик до NetBox (GET /api/ipam/prefixes/?within=...)
    штом NetBox/Docker стек е потврдено дека работи. Засега секогаш враќа
    "нема преклопување" за да не блокира понатамошно тестирање на графот.
    """
    state["netbox_result"] = {"overlap_found": False, "existing_rules": []}
    return state


def guardrail_netbox_node(state: GraphState) -> GraphState:
    result = check_netbox(state["netbox_result"])
    state["guardrail_log"].append({"step": "netbox_check", **result})
    if state["status"] == "ok":
        structural_ok = result["passed"]
        business_ok = not state["netbox_result"].get("overlap_found", True)
        if not structural_ok:
            state["status"] = "rejected_at_netbox_structure"
        elif not business_ok:
            state["status"] = "rejected_at_netbox_overlap"
    return state


def policy_checker_node(state: GraphState) -> GraphState:
    intent = state["parsed_intent"]
    prompt = f"""Оцени дали ова мрежно правило е безбедносно прифатливо и врати ГИ САМО во JSON:
{{"policy_pass": true/false, "violations": ["..."], "risk_level": "low|medium|high"}}

Правило: дозволи од {intent['source_subnet']} до {intent['dest_subnet']} на порт {intent['dest_port']} преку {intent['protocol']}.

Правила на политика:
- risk_level "high" ако source_subnet е поширок од /16 (премногу широк опсег)
- risk_level "high" ако портот е еден од: 22, 23, 3389 (административни/чувствителни порти)
- инаку risk_level "low" или "medium" според проценка"""
    state["policy_result"] = safe_json_parse(call_llm(prompt))
    return state


def guardrail_policy_node(state: GraphState) -> GraphState:
    intent = state["parsed_intent"]
    result = check_policy(
        state["policy_result"],
        source_subnet=intent["source_subnet"],
        dest_port=intent["dest_port"],
    )
    state["guardrail_log"].append({"step": "policy_checker", **result})
    if state["status"] == "ok":
        # result["passed"] опфаќа и structural (JSON schema) и semantic (ground-truth CIDR/port) проверки
        guardrail_ok = result["passed"]
        business_ok = state["policy_result"].get("policy_pass", False)
        if not guardrail_ok:
            state["status"] = "rejected_at_policy_checker_guardrail"
        elif not business_ok:
            state["status"] = "rejected_at_policy_checker_denied"
        else:
            state["status"] = "ok"
    return state


def planner_node(state: GraphState) -> GraphState:
    intent = state["parsed_intent"]
    prompt = f"""Направи план за промената И план за rollback (враќање) во случај нешто да тргне наопаку.
Врати ГИ САМО во JSON:
{{"proposed_rule_summary": "...", "change_plan": "...", "rollback_plan": "..."}}

Правило: {intent['source_subnet']} -> {intent['dest_subnet']}:{intent['dest_port']}/{intent['protocol']}"""
    state["plan_result"] = safe_json_parse(call_llm(prompt))
    return state


def guardrail_planner_node(state: GraphState) -> GraphState:
    result = check_planner(state["plan_result"])
    state["guardrail_log"].append({"step": "planner", **result})
    if state["status"] == "ok" and not result["passed"]:
        state["status"] = "rejected_at_planner"
    return state


def _rule_payload(state: GraphState) -> dict:
    intent = state["parsed_intent"]
    return {
        "source_subnet": intent["source_subnet"],
        "dest_subnet": intent["dest_subnet"],
        "dest_port": intent["dest_port"],
        "protocol": intent["protocol"],
    }


def dry_run_node(state: GraphState) -> GraphState:
    payload = _rule_payload(state)
    response = requests.post(f"{FIREWALL_URL}/rules/dry-run", json=payload)
    result = response.json()
    state["dry_run_result"] = result
    passed = response.ok and result.get("simulation_ok", False)
    state["guardrail_log"].append({"step": "dry_run", "passed": passed, "errors": [] if passed else ["dry_run_failed"]})
    if state["status"] == "ok" and not passed:
        state["status"] = "rejected_at_dry_run"
    return state


def apply_node(state: GraphState) -> GraphState:
    """Чекор 8 (Apply rule). Извршува се дури откако compiled.invoke прекине
    пред овој node (interrupt_before=["apply_node"]) и човекот одобри
    (чекор 7, Human approval)."""
    payload = _rule_payload(state)
    response = requests.post(f"{FIREWALL_URL}/rules/apply", json=payload)
    result = response.json()
    state["apply_result"] = result
    passed = response.ok and result.get("applied", False)
    state["guardrail_log"].append({"step": "apply", "passed": passed, "errors": [] if passed else ["apply_failed"]})
    if state["status"] == "ok" and not passed:
        state["status"] = "rejected_at_apply"
    return state


def verify_node(state: GraphState) -> GraphState:
    rule_id = state["apply_result"].get("rule_id")
    response = requests.get(f"{FIREWALL_URL}/rules/{rule_id}")
    state["verify_result"] = response.json()
    return state


def guardrail_verify_node(state: GraphState) -> GraphState:
    expected_rule = _rule_payload(state)
    result = check_verifier(state["verify_result"], expected_rule=expected_rule)
    state["guardrail_log"].append({"step": "verify", **result})
    if state["status"] == "ok" and not result["passed"]:
        state["status"] = "verification_failed"
    return state


def rollback_node(state: GraphState) -> GraphState:
    """Чекор 10 (Execute rollback) - се извршува САМО ако verify (чекор 9)
    врати негативен резултат (условно рутирање, не безусловно)."""
    rule_id = state["apply_result"].get("rule_id")
    response = requests.delete(f"{FIREWALL_URL}/rules/{rule_id}")
    result = response.json()
    state["rollback_result"] = result
    rolled_back = result.get("rolled_back", False)
    state["guardrail_log"].append({"step": "rollback", "passed": rolled_back, "errors": [] if rolled_back else ["rollback_failed"]})
    state["status"] = state["status"] + ("_rolled_back" if rolled_back else "_rollback_failed")
    return state


def route_after_check(state: GraphState) -> str:
    """Ако status веќе не е 'ok', прекини го синџирот наместо да продолжиш."""
    if state["status"] != "ok":
        return "stop"
    return "continue"


def route_after_verify(state: GraphState) -> str:
    """Rollback само ако verify (чекор 9) врати негативен резултат, инаку успешен крај."""
    if state["status"] != "ok":
        return "rollback"
    return "success"


graph = StateGraph(GraphState)
graph.add_node("intent_parser", intent_parser_node)
graph.add_node("guardrail_intent", guardrail_intent_node)
graph.add_node("validator", validator_node)
graph.add_node("guardrail_validator", guardrail_validator_node)
graph.add_node("netbox_check", netbox_check_node)
graph.add_node("guardrail_netbox", guardrail_netbox_node)
graph.add_node("policy_checker", policy_checker_node)
graph.add_node("guardrail_policy", guardrail_policy_node)
graph.add_node("planner", planner_node)
graph.add_node("guardrail_planner", guardrail_planner_node)
graph.add_node("dry_run", dry_run_node)
graph.add_node("apply_node", apply_node)
graph.add_node("verify_node", verify_node)
graph.add_node("guardrail_verify", guardrail_verify_node)
graph.add_node("rollback_node", rollback_node)

graph.set_entry_point("intent_parser")
graph.add_edge("intent_parser", "guardrail_intent")

graph.add_conditional_edges("guardrail_intent", route_after_check, {"continue": "validator", "stop": END})
graph.add_edge("validator", "guardrail_validator")
graph.add_conditional_edges("guardrail_validator", route_after_check, {"continue": "netbox_check", "stop": END})
graph.add_edge("netbox_check", "guardrail_netbox")
graph.add_conditional_edges("guardrail_netbox", route_after_check, {"continue": "policy_checker", "stop": END})
graph.add_edge("policy_checker", "guardrail_policy")
graph.add_conditional_edges("guardrail_policy", route_after_check, {"continue": "planner", "stop": END})
graph.add_edge("planner", "guardrail_planner")
graph.add_conditional_edges("guardrail_planner", route_after_check, {"continue": "dry_run", "stop": END})
graph.add_conditional_edges("dry_run", route_after_check, {"continue": "apply_node", "stop": END})
graph.add_conditional_edges("apply_node", route_after_check, {"continue": "verify_node", "stop": END})
graph.add_edge("verify_node", "guardrail_verify")
graph.add_conditional_edges("guardrail_verify", route_after_verify, {"rollback": "rollback_node", "success": END})
graph.add_edge("rollback_node", END)

# Чекор 7 (Human approval): графот застанува пред apply_node. Резервацијата на
# state-от меѓу invoke повиците бара checkpointer (MemorySaver, in-memory - доволно за PoC).
checkpointer = MemorySaver()
compiled = graph.compile(checkpointer=checkpointer, interrupt_before=["apply_node"])


def run_pipeline(raw_request: str, approve_callback=None) -> dict:
    """Ја пушта целата постапка (Табела 1, чекори 1-10) вклучувајќи го human
    approval гејтот пред apply_node.

    approve_callback: функција без аргументи која враќа True/False за да се
    симулира човечкото одобрување. Ако е None, се прашува преку CLI input()
    (интерактивен режим). Test harness-от го проследува своето сопствено
    approve_callback за да може да работи неинтерактивно во 10x повторувања.
    """
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    state = compiled.invoke({
        "raw_request": raw_request,
        "guardrail_log": [],
        "status": "ok",
    }, config=config)

    pending = compiled.get_state(config)
    if pending.next and "apply_node" in pending.next:
        approved = approve_callback() if approve_callback else _cli_approve(state)
        state["guardrail_log"].append({"step": "human_approval", "passed": approved, "errors": [] if approved else ["rejected_by_human"]})
        if approved:
            state = compiled.invoke(None, config=config)
        else:
            state["status"] = "rejected_at_human_approval"
            compiled.update_state(config, {"status": "rejected_at_human_approval", "guardrail_log": state["guardrail_log"]})

    return state


def _cli_approve(state: dict) -> bool:
    print("\n--- Чекор 7: Human approval ---")
    print(f"  Предложено правило: {state.get('plan_result', {}).get('proposed_rule_summary')}")
    print(f"  Change plan: {state.get('plan_result', {}).get('change_plan')}")
    print(f"  Rollback plan: {state.get('plan_result', {}).get('rollback_plan')}")
    print(f"  Dry-run: {state.get('dry_run_result')}")
    answer = input("Одобри примена на правилото? (y/n): ").strip().lower()
    return answer == "y"


if __name__ == "__main__":
    final_state = run_pipeline("Дозволи пристап од 10.0.5.0/24 до 10.0.10.15 на порт 443 преку TCP.")
    print("\nФинален state:")
    for key, value in final_state.items():
        print(f"  {key}: {value}")