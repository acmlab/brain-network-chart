# Brain Network Chart A2A Server

A multi-agent system (MAS) for brain network / fMRI analysis using [pydantic-ai](https://ai.pydantic.dev/) and the [A2A (Agent-to-Agent) protocol](https://google.github.io/A2A/).

---

## How A2A Works in This MAS

**The A2A server is not a single server for all agents.** Each agent is its own A2A server.

- **Each agent** is wrapped with an A2A SDK (e.g. Pydantic AI’s `agent.to_a2a()`) and exposed over HTTP. So we have one A2A server per agent (Planner, Executor, Researcher, Validator).
- **The Planner** (or an orchestrator) uses **A2A clients** to call those agent A2A servers: it sends the plan’s tasks to the right agent endpoints (Executor, Researcher, Validator) via the A2A protocol.
- **The frontend** uses an **A2A client for the Planner agent**: it talks to the Planner’s A2A server over HTTP. The frontend does not call all agents directly; it goes through the Planner (or a thin gateway that forwards to the Planner).

So the flow is (4 agents in order: Planner → Executor → Researcher → Validator):

```
Frontend  --(A2A client)-->  Planner (A2A)  -->  Executor (A2A)  -->  Researcher (A2A)  -->  Validator (A2A)
                                     |
                                     | (orchestrator dispatches tasks by agent)
                                     v
              Tasks go to the right agent (executor / researcher / validator) per plan.
```

Agent designers: implement your agent in any framework, then **wrap it with an A2A SDK and expose it as an HTTP A2A server**. The Planner (and thus the frontend) will call you via A2A clients.

---

## Agents

There are **4 agents in total**, in pipeline order:

**Planner → Executor → Researcher → Validator**

| Agent        | Order | Role |
|-------------|-------|------|
| **Planner**   | 1 | Understands the user query, creates an execution plan, assigns tasks to the other agents. |
| **Executor**  | 2 | Uses MCP tools for input-to-trait analysis, data processing. |
| **Researcher**| 3 | Statistical analysis, database/literature search. |
| **Validator** | 4 | Validates results and confirms the query is resolved. |

---

## Current Implementation Status

- **Planner**: Implemented with Pydantic AI; can run as an A2A server (`python a2a_agents.py planner 8011`). Outputs a structured `ExecutionPlan` (query summary + task list per agent).
- **Executor**: Separate agent that runs **right after** the Planner. Receives tasks assigned to “executor” (description + `input_payload` with `tool` and MCP params) and returns an `ExecutorResult`. Run as its own A2A server: `python a2a_agents.py executor 8012`. MCP tool calls can be wired here (stub for now).
- **a2a_client.py**: For **testing only** — runs the Planner in-process (no HTTP). Production flow will use an A2A client to call the Planner’s A2A server, then call the Executor (and others) per plan.
- **Researcher / Validator**: Not yet implemented. When added, each will be exposed as its own A2A server; the orchestrator will use A2A clients to call them according to the plan.

So: **one A2A server per agent**; pipeline order is **Planner → Executor → Researcher → Validator**; frontend uses an A2A client to the Planner; the orchestrator uses A2A clients to call Executor, Researcher, and Validator per task.

---

## Deployment and wiring

For a full **deploy-on-your-server** and **wire-up-the-A2A-client** guide, see **[DEPLOY.md](DEPLOY.md)**. It covers:

- Running the Planner (MedGemma) as an A2A server on port 8011
- Using the example A2A client over HTTP to call the Planner and see how to dispatch to other agents
- Optional systemd and multi-agent wiring

---

## Quick Start

### Option 1: Local execution (testing)

Run the Planner in-process (no HTTP):

```bash
python a2a_client.py
python a2a_client.py "Your analysis query here"
```

### Option 2: Planner as A2A server

Run the Planner as an HTTP A2A server, then call it with any A2A client:

```bash
python a2a_agents.py planner 8011
# In another terminal / from frontend: use an A2A client to POST to http://localhost:8011
```

### Option 3: Planner + Executor (two agents)

Run the Planner and the Executor as separate A2A servers. The Executor is the next agent after the Planner:

```bash
# Terminal 1: Planner
python a2a_agents.py planner 8011

# Terminal 2: Executor (separate agent, receives tasks from the plan)
python a2a_agents.py executor 8012
# Orchestrator: A2A client → Planner at 8011; then for each executor task → Executor at 8012
```

### Option 4: Full MAS (when all agents exist)

```bash
# Terminal 1–4
python a2a_agents.py planner 8011
python a2a_agents.py executor 8012
python a2a_agents.py researcher 8013
python a2a_agents.py validator 8014
# Frontend / orchestrator: A2A client → Planner at 8011; then A2A clients → 8012, 8013, 8014 per task
```

---

## Files

- **a2a_agents.py** — CLI to run an agent as an A2A server (`python a2a_agents.py <agent> <port>`). Agents: `planner`, `executor`.
- **planner_agent.py** — Planner agent: produces `ExecutionPlan` with tasks per agent.
- **executor_agent.py** — Executor agent (separate, right after Planner): accepts a task and returns `ExecutorResult`; will call MCP tools.
- **a2a_client.py** — Test client (local in-process call to Planner).
- **a2a_client_http.py** — Example A2A client that calls the Planner over HTTP (e.g. `http://localhost:8011`), then shows how to dispatch tasks to Executor / Researcher / Validator. Use after deploying the Planner (see [DEPLOY.md](DEPLOY.md)).

---

## Backend: Brain Network MCP Server

The **Executor** (and optionally **Validator**) agents call a Brain Network Analysis MCP server that provides signal processing and graph-based analysis tools. That server is documented in the **validator-agent** branch (e.g. `validator-agent-and-stats-tools`).

| Item | Value |
|------|--------|
| **Base URL** | `http://yukon.acm.unc.edu:8010` |
| **Schema** | `GET /api/schema` for live JSON schema of all endpoints |
| **Health** | `GET /health` |

**Main tools (POST endpoints):**

- **run_cfc_wavelet_analysis** — Cross-frequency coupling (CFC) wavelet analysis on BOLD connectivity (data_path, window_size, step_size, padding, ratio, wavelets_num, beta, gamma, max_iter, node_select).
- **run_hub_detection** — Hub detection in single or multiple networks (data_path, window_size, step_size, padding, ratio, k, hub_num, use_group).
- **get_growth_curve** — Developmental trajectory / growth curve (phenotype, e.g. "Global mean of FC").
- **run_normative_analysis** — Normative analysis with overlay CSV (x_phenotype, y_path, age_col, val_col).
- **upload** — Multipart file upload (field `file`); then use returned filename as `data_path` or `y_path`.

The Planner produces execution plans whose **executor** tasks can include an `input_payload` with `tool` and the above parameters so the Executor can call this MCP server. For full API details, request payloads, and data formats, see the README on the validator-agent branch.

---

## Configuration

**Planner (default: MedGemma via Ollama)** — Edit `planner_agent.py`:

```python
MODEL_NAME = "MedAIBase/MedGemma1.5:4b"
OLLAMA_HOST = "yukon.acm.unc.edu:11434"
```

To use OpenAI instead, set `OPENAI_API_KEY` in `.env` and set `MODEL_NAME = "openai:gpt-4o-mini"` in `planner_agent.py`.

---

## Dependencies

```bash
pip install -r requirements.txt
# or
pip install 'pydantic-ai[a2a]' uvicorn httpx openai
```

---

## References

- [A2A protocol](https://google.github.io/A2A/)
- [Pydantic AI – A2A](https://ai.pydantic.dev/a2a/)
- [FastA2A](https://github.com/pydantic/fasta2a) (framework-agnostic A2A in Python)
