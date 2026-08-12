"""ПРИВРЕМЕН контролиран експеримент - НЕ дел од production pipeline.

Тестира дали експлицитно "default to policy_pass:true кога нема high-risk
услов" во policy_checker промптот го решава Наод 9/12 (results/dev_notes.md:
0/20 success rate на намерно-безбедни intents со оригиналниот промпт).

langgraph-poc/graph_v1.py НЕ е менуван - овој фајл повторно ги користи
неговите останати nodes/guardrails (интактни) и само ја заменува
policy_checker_node со policy_checker_node_v2 (изменет промпт). Избриши го
овој фајл штом контролираниот експеримент заврши и наодот е документиран.
"""
import sys, uuid
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from guardrails.common import safe_json_parse
from guardrails.llm_client import call_llm
from guardrails.check_policy import check as check_policy

import graph_v1 as v1


def policy_checker_node_v2(state: v1.GraphState) -> v1.GraphState:
    intent = state["parsed_intent"]
    prompt = f"""Оцени дали ова мрежно правило е безбедносно прифатливо и врати ГИ САМО во JSON:
{{"policy_pass": true/false, "violations": ["..."], "risk_level": "low|medium|high"}}

Правило: дозволи од {intent['source_subnet']} до {intent['dest_subnet']} на порт {intent['dest_port']} преку {intent['protocol']}.

Правила на политика:
- risk_level "high" ако source_subnet е поширок од /16 (премногу широк опсег)
- risk_level "high" ако портот е еден од: 22, 23, 3389 (административни/чувствителни порти)
- Ако правилото НЕ го исполнува ниту еден од двата дефинирани high-risk услови, задолжително policy_pass: true и risk_level: "low".
- инаку risk_level "low" или "medium" според проценка"""
    state["policy_result"] = safe_json_parse(call_llm(prompt))
    return state


def guardrail_policy_node_v2(state: v1.GraphState) -> v1.GraphState:
    """Иста guardrail логика како v1.guardrail_policy_node (check_policy.py не е менуван)."""
    intent = state["parsed_intent"]
    result = check_policy(
        state["policy_result"],
        source_subnet=intent["source_subnet"],
        dest_port=intent["dest_port"],
    )
    state["guardrail_log"].append({"step": "policy_checker", **result})
    if state["status"] == "ok":
        guardrail_ok = result["passed"]
        business_ok = state["policy_result"].get("policy_pass", False)
        if not guardrail_ok:
            state["status"] = "rejected_at_policy_checker_guardrail"
        elif not business_ok:
            state["status"] = "rejected_at_policy_checker_denied"
        else:
            state["status"] = "ok"
    return state


graph = StateGraph(v1.GraphState)
graph.add_node("intent_parser", v1.intent_parser_node)
graph.add_node("guardrail_intent", v1.guardrail_intent_node)
graph.add_node("validator", v1.validator_node)
graph.add_node("guardrail_validator", v1.guardrail_validator_node)
graph.add_node("netbox_check", v1.netbox_check_node)
graph.add_node("guardrail_netbox", v1.guardrail_netbox_node)
graph.add_node("policy_checker", policy_checker_node_v2)
graph.add_node("guardrail_policy", guardrail_policy_node_v2)
graph.add_node("planner", v1.planner_node)
graph.add_node("guardrail_planner", v1.guardrail_planner_node)
graph.add_node("dry_run", v1.dry_run_node)
graph.add_node("apply_node", v1.apply_node)
graph.add_node("verify_node", v1.verify_node)
graph.add_node("guardrail_verify", v1.guardrail_verify_node)
graph.add_node("rollback_node", v1.rollback_node)

graph.set_entry_point("intent_parser")
graph.add_edge("intent_parser", "guardrail_intent")
graph.add_conditional_edges("guardrail_intent", v1.route_after_check, {"continue": "validator", "stop": END})
graph.add_edge("validator", "guardrail_validator")
graph.add_conditional_edges("guardrail_validator", v1.route_after_check, {"continue": "netbox_check", "stop": END})
graph.add_edge("netbox_check", "guardrail_netbox")
graph.add_conditional_edges("guardrail_netbox", v1.route_after_check, {"continue": "policy_checker", "stop": END})
graph.add_edge("policy_checker", "guardrail_policy")
graph.add_conditional_edges("guardrail_policy", v1.route_after_check, {"continue": "planner", "stop": END})
graph.add_edge("planner", "guardrail_planner")
graph.add_conditional_edges("guardrail_planner", v1.route_after_check, {"continue": "dry_run", "stop": END})
graph.add_conditional_edges("dry_run", v1.route_after_check, {"continue": "apply_node", "stop": END})
graph.add_conditional_edges("apply_node", v1.route_after_check, {"continue": "verify_node", "stop": END})
graph.add_edge("verify_node", "guardrail_verify")
graph.add_conditional_edges("guardrail_verify", v1.route_after_verify, {"rollback": "rollback_node", "success": END})
graph.add_edge("rollback_node", END)

checkpointer = MemorySaver()
compiled = graph.compile(checkpointer=checkpointer, interrupt_before=["apply_node"])


def run_pipeline_v2(raw_request: str, approve_callback=None) -> dict:
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    state = compiled.invoke({
        "raw_request": raw_request,
        "guardrail_log": [],
        "status": "ok",
    }, config=config)

    pending = compiled.get_state(config)
    if pending.next and "apply_node" in pending.next:
        approved = approve_callback() if approve_callback else v1._cli_approve(state)
        state["guardrail_log"].append({"step": "human_approval", "passed": approved, "errors": [] if approved else ["rejected_by_human"]})
        if approved:
            state = compiled.invoke(None, config=config)
        else:
            state["status"] = "rejected_at_human_approval"
            compiled.update_state(config, {"status": "rejected_at_human_approval", "guardrail_log": state["guardrail_log"]})

    return state
