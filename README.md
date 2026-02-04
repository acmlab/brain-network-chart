# Brain Network Chart A2A Server

A multi-agent system (MAS) for brain network / fMRI analysis using [pydantic-ai](https://ai.pydantic.dev/) and the [A2A (Agent-to-Agent) protocol](https://google.github.io/A2A/).

---

## How A2A Works in This MAS

**The A2A server is not a single server for all agents.** Each agent is its own A2A server.

- **Each agent** is wrapped with an A2A SDK (e.g. Pydantic AI’s `agent.to_a2a()`) and exposed over HTTP. So we have one A2A server per agent (Planner, Executor, Researcher, Validator).
- **The Planner** (or an orchestrator) uses **A2A clients** to call those agent A2A servers: it sends the plan’s tasks to the right agent endpoints (Executor, Researcher, Validator) via the A2A protocol.
- **The frontend** uses an **A2A client for the Planner agent**: it talks to the Planner’s A2A server over HTTP. The frontend does not call all agents directly; it goes through the Planner (or a thin gateway that forwards to the Planner).

So the flow is:

```
Frontend  --(A2A client)-->  Planner (A2A server)
                                  |
                                  | (A2A clients)
                                  v
              +-------------------+-------------------+
              |                   |                   |
        Executor (A2A)      Researcher (A2A)    Validator (A2A)
```

Agent designers: implement your agent in any framework, then **wrap it with an A2A SDK and expose it as an HTTP A2A server**. The Planner (and thus the frontend) will call you via A2A clients.

---

## Agents

| Agent      | Role |
|-----------|------|
| **Planner**   | Understands the user query, creates an execution plan, assigns tasks to agents via A2A. |
| **Executor**  | Uses MCP tools for input-to-trait analysis, data processing. |
| **Researcher**| Statistical analysis, database/literature search. |
| **Validator**| Validates results and confirms the query is resolved. |

---

## Current Implementation Status

- **Planner**: Implemented with Pydantic AI; can run as an A2A server (`python a2a_agents.py planner 8011`). Outputs a structured `ExecutionPlan` (query summary + task list per agent).
- **a2a_client.py**: For **testing only** — runs the Planner **in-process** (no HTTP). Production flow will use an A2A client to call the Planner’s A2A server.
- **Executor / Researcher / Validator**: Not yet implemented. When added, each will be exposed as its own A2A server; the orchestrator will use A2A clients to call them according to the plan.

So: **architecture matches the TLDR** (one A2A server per agent; Planner/orchestrator uses A2A clients; frontend uses A2A client to Planner). The code is aligned with that; the client script is currently a local test harness.

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

### Option 3: Full MAS (when all agents exist)

Run each agent as its own A2A server, then run a client that uses A2A to talk to the Planner (and the Planner/orchestrator uses A2A to call the others):

```bash
# Terminal 1–4
python a2a_agents.py planner 8011
python a2a_agents.py executor 8012
python a2a_agents.py researcher 8013
python a2a_agents.py validator 8014
# Frontend / orchestrator: A2A client → Planner at 8011; Planner uses A2A clients → 8012, 8013, 8014
```

---

## Files

- **a2a_agents.py** — Agent definitions (Planner implemented). Each agent can be run as an A2A server (`python a2a_agents.py <agent> <port>`).
- **a2a_client.py** — Test client (local in-process call to Planner). Will be extended or replaced by an A2A client that calls the Planner over HTTP.

---

## Configuration

Edit in `a2a_agents.py`:

```python
OLLAMA_HOST = "yukon.acm.unc.edu:11434"
MODEL_NAME = "MedAIBase/MedGemma1.5:4b"
```

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
