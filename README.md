# TELFOR Agent Orchestration

Comparative study implementing the same guardrail-checked LLM pipeline for
network firewall change automation across three agent orchestration
platforms (LangGraph, n8n, Langflow), written up as a TELFOR 2026 working
paper.

## Tech stack
* Python 3.12
* LangGraph 1.2.10 — state-graph orchestration for the reference implementation
* ollama 0.6.2 (Python client) — talks to a local Ollama server running `qwen2.5:7b`
* FastAPI 0.141.1 + uvicorn 0.52.0 — mock firewall API and the shared guardrail HTTP wrapper
* jsonschema 4.26.0 — validates LLM output against `contracts/*.schema.json`
* requests — HTTP calls from the LangGraph nodes to the mock firewall
* n8n 2.33.4 (installed globally via `npm install -g n8n`) — second orchestration platform under comparison

No `requirements.txt` exists yet; versions above are what's currently installed in `venv/`, not pinned.

## What it does
* Turns a natural-language network change request into a provisioned firewall rule through a 10-step pipeline: parse intent → validate syntax → query NetBox (mocked) → policy check → propose change/rollback plan → dry-run → human approval → apply → verify → rollback
* Implements the identical pipeline and prompts across 3 orchestration platforms — LangGraph (complete), n8n (partial), Langflow (not started) — to compare how the orchestration layer affects reliability of the same LLM and the same guardrail logic
* Checks every LLM output with a guardrail before letting the graph continue: JSON-schema structural validation for all 6 LLM-facing steps, plus an independent semantic recomputation of the ground truth (CIDR prefix width, sensitive-port membership) for the policy-check step that overrides the model's own stated reasoning
* Gates the actual firewall change behind a human-approval step, and rolls back automatically if post-apply verification fails
* Includes a 10x-repetition test harness per scenario to measure success rate, failure point, and guardrail-catch rate statistically instead of anecdotally

## Highlights
* `guardrails/` is the shared core: LangGraph imports the `check_*.py` functions directly in-process, while n8n (and later Langflow) call the exact same functions over HTTP through `mock-services/guardrail_api.py` — no guardrail logic is reimplemented per platform
* Conditional routing is mandatory, not optional: every LangGraph edge after a guardrail node uses `add_conditional_edges`, so a rejected step stops the graph instead of continuing on to the planner/apply steps "by inertia"
* Semantic guardrails don't trust the LLM's own justification for a fact it could get wrong: `check_policy.py` independently recomputes CIDR prefix width and sensitive-port membership, and overrides any model claim that disagrees with the ground truth
* `guardrails/llm_client.py` centralizes model/provider selection (`LLM_MODEL`, `LLM_PROVIDER` env vars) behind one `call_llm()` function, so the planned multi-model comparison won't require touching every prompt call site
* `mock-services/mock_firewall.py` is a throwaway FastAPI stand-in for a real firewall API (dry-run/apply/verify/rollback endpoints, in-memory store), so the pipeline can be exercised end-to-end without production network infrastructure

## Useful commands
* `python langgraph-poc/graph_v1.py` — run the LangGraph pipeline once, interactively (prompts for the human-approval step on the CLI)
* `uvicorn mock-services.mock_firewall:app --port 9000` — start the mock firewall API
* `uvicorn mock-services.guardrail_api:app --port 9100` — start the shared guardrail HTTP wrapper (used by n8n)
* `python test-harness/run_experiment.py` — run the 10x-repetition stability harness across all test intents, appending results to `results/experiment_results.csv`
* `python test-harness/test_guardrails.py` — manual smoke check of `check_intent_parser` against one valid and one invalid example (prints results; not a pytest suite)
* `n8n start` — start the n8n editor/runtime at `http://127.0.0.1:5678`; use `127.0.0.1`, not `localhost`, in any n8n node that calls a local service (see `results/dev_notes.md`, Наод #15)

## Setup
1. Create and activate a virtualenv: `python -m venv venv`, then `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Linux/macOS)
2. Install the Python dependencies: `pip install langgraph ollama fastapi uvicorn jsonschema requests`
3. Install [Ollama](https://ollama.com) and pull the model the pipeline uses: `ollama pull qwen2.5:7b`
4. Install n8n globally: `npm install -g n8n`
5. Start the three local services, each in its own terminal: mock firewall (`:9000`), guardrail API (`:9100`), n8n (`:5678`) — see the commands above, or `.claude/launch.json` if you're using Claude Code's browser-preview tooling
6. Run the LangGraph pipeline: `python langgraph-poc/graph_v1.py`

## Project status
* **LangGraph** — complete. All 10 pipeline steps implemented and exercised end-to-end, including the human-approval gate and conditional rollback (`langgraph-poc/graph_v1.py`).
* **n8n** — complete. All 10 pipeline steps implemented and individually verified in workflow `CwrkhftDrYNgl08c`, including the Wait/Form human-approval gate (step 7) and conditional rollback (step 10, both the success and rollback branches confirmed against the real mock firewall state).
* **Langflow** — not started (`langflow-poc/` exists as an empty placeholder directory).

## Reports
`results/dev_notes.md` is the primary source of empirical findings — a chronological, numbered log ("Наод" entries) of every bug, root cause, fix, and paper-relevant implication found during implementation. It's written for the paper's Discussion/Results sections, not as a changelog. Raw per-run data from the stability harness lives in `results/experiment_results.csv` (gitignored, local only), and `n8n-poc/screenshots/README.md` indexes the verified screenshots documenting the n8n implementation.
