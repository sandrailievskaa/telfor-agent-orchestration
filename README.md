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
* Langflow (Python-based visual framework, `langflow-poc/venv_langflow/`) — third orchestration platform under comparison, HITL segment only (see Project status)

No `requirements.txt` exists yet; versions above are what's currently installed in `venv/`, not pinned.

## What it does
* Turns a natural-language network change request into a provisioned firewall rule through a 10-step pipeline: parse intent → validate syntax → query NetBox (currently a fixed stub, no live instance — see Project status) → policy check → propose change/rollback plan → dry-run → human approval → apply → verify → conditional rollback
* Implements the identical pipeline and prompts across 3 orchestration platforms — LangGraph and n8n fully wired end-to-end; Langflow's steps 1–6 are independently verified sub-chains, with only steps 7–10 (human approval through rollback) connected into one run — to compare how the orchestration layer affects reliability of the same LLM and the same guardrail logic
* Checks every LLM output with a guardrail before letting the pipeline continue: JSON-schema structural validation for all 4 LLM-facing steps, plus an independent semantic recomputation of the ground truth (CIDR prefix width, sensitive-port membership) for the policy-check step that overrides the model's own stated reasoning
* Gates the actual firewall change behind a human-approval step, and rolls back automatically if post-apply verification fails
* Includes a 10x-repetition test harness per scenario (`test-harness/run_experiment*.py`) to measure success rate, failure point, and guardrail-catch rate statistically instead of anecdotally — 100 runs collected so far across LangGraph, n8n and Langflow with the local model
* `guardrails/llm_client.py` can also call out to PCSS AI HUB (`LLM_PROVIDER=external`, OpenAI-compatible `/v1/chat/completions`) for a planned multi-model comparison round (GLM-5.1, Qwen2.5:72b, DeepSeek-V3.1) — see Project status for what's actually been run

## Highlights
* `guardrails/` is the shared core: LangGraph imports the `check_*.py` functions directly in-process, while n8n and Langflow call the exact same functions over HTTP through `mock-services/guardrail_api.py` — no guardrail logic is reimplemented per platform
* Conditional routing is mandatory, not optional: every LangGraph edge after a guardrail node uses `add_conditional_edges`, so a rejected step stops the graph instead of continuing on to the planner/apply steps "by inertia"
* Semantic guardrails don't trust the LLM's own justification for a fact it could get wrong: `check_policy.py` independently recomputes CIDR prefix width and sensitive-port membership, and overrides any model claim that disagrees with the ground truth
* `guardrails/llm_client.py` centralizes model/provider selection (`LLM_MODEL`, `LLM_PROVIDER` env vars) behind one `call_llm()` function, so the planned multi-model comparison won't require touching every prompt call site
* `mock-services/mock_firewall.py` is a throwaway FastAPI stand-in for a real firewall API (dry-run/apply/verify/rollback endpoints, in-memory store), so the pipeline can be exercised end-to-end without production network infrastructure

## Useful commands
* `python langgraph-poc/graph_v1.py` — run the LangGraph pipeline once, interactively (prompts for the human-approval step on the CLI)
* `uvicorn mock-services.mock_firewall:app --port 9000` — start the mock firewall API
* `uvicorn mock-services.guardrail_api:app --port 9100` — start the shared guardrail HTTP wrapper (used by n8n)
* `python test-harness/run_experiment.py` — run the 10x-repetition stability harness across all test intents on LangGraph, appending results to `results/experiment_results.csv`
* `python test-harness/run_experiment_n8n.py` / `run_experiment_langflow.py` — same harness methodology against the n8n and Langflow implementations (see Project status for each platform's actual scope)
* `LLM_PROVIDER=external LLM_MODEL=GLM-5.1 python test-harness/run_experiment.py` — run the same harness against a PCSS-hosted model instead of local Ollama (requires `PCSS_API_KEY`/`PCSS_BASE_URL` in `.env`); swap `LLM_MODEL` for `Qwen2.5:72b` or `DeepSeek-V3.1` for the other two planned models
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
* **LangGraph** — complete. All 10 pipeline steps implemented and exercised end-to-end, including the human-approval gate and conditional rollback (`langgraph-poc/graph_v1.py`). 10x-repetition harness run across 4 intents (40 runs) with `qwen2.5:7b`.
* **n8n** — complete. All 10 pipeline steps implemented and individually verified in workflow `CwrkhftDrYNgl08c`, including the Wait/Form human-approval gate (step 7) and conditional rollback (step 10, both the success and rollback branches confirmed against the real mock firewall state). Same 4-intent × 10x harness run (`test-harness/run_experiment_n8n.py`, 40 runs).
* **Langflow** — steps 1–6 implemented and individually verified as isolated sub-chains; steps 7–10 (human approval → apply → verify → conditional rollback) are wired into one connected pipeline and were the only segment put through the 10x-repetition harness (`test-harness/run_experiment_langflow.py`, 10 runs, static approval request — this segment has no LLM call, so it measures HITL/suspend-resume infrastructure stability, not guardrail/model stability). Full end-to-end wiring of steps 1–6 remains open work.
* **Known limitation, not a per-platform difference**: step 3 (NetBox overlap check) is a fixed stub (`overlap_found: false`, always) on all three platforms — a local NetBox instance could not be brought up (WSL2/Docker environment fault). Its guardrail currently checks schema validity only, not real inventory data.
* **Multi-model round (PCSS AI HUB)** — `LLM_PROVIDER=external` confirmed working end-to-end. The 40-run LangGraph harness is in progress against GLM-5.1 (reasoning model, ~3-4x slower per run than local `qwen2.5:7b` — observed mean ~130 s vs ~30-40 s on the `simple` intent); a second PCSS model (Qwen2.5:72b or DeepSeek-V3.1) is planned next on the same harness. n8n's LLM calls go through its own native Ollama Chat Model nodes, not `guardrails/llm_client.py`, so extending n8n to PCSS models requires swapping those nodes for OpenAI-compatible ones — deliberately deferred given the already-verified n8n implementation and limited time before the deadline; the multi-model round is reference-implementation-only (LangGraph) for this submission.

## Reports
`results/dev_notes.md` is the primary source of empirical findings — a chronological, numbered log ("Наод" entries, 47 so far) of every bug, root cause, fix, and paper-relevant implication found during implementation. It's written for the paper's Discussion/Results sections, not as a changelog. Raw per-run data from the stability harness lives in `results/experiment_results.csv` (tracked in git — see `.gitignore`'s explicit exception for this one file), and `n8n-poc/screenshots/README.md` indexes the verified screenshots documenting the n8n implementation. The TELFOR 2026 paper draft (LaTeX) is in `paper/telfor_paper.tex`.
