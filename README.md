# Brain Network Chart A2A Server

Multi-agent system (MAS) for brain network / fMRI analysis. Each agent is an **A2A server** on its own port; the frontend (or orchestrator) calls the Planner first, then other agents per plan.

---

## Agents and ports

| Agent     | Port | Role |
|-----------|------|------|
| **Planner**   | 8011 | Understands query → plan with tasks for executor / researcher / validator |
| **Executor**  | 8012 | MCP tools (CFC, hub detection, growth curve, normative) |
| **Researcher**| 8013 | Literature, PubMed, stats |
| **Validator** | 8014 | Validates results, confirms query resolved |

**Flow:** Frontend → **Planner (8011)** → get `ExecutionPlan` → orchestrator calls **Executor (8012)** / **Researcher (8013)** / **Validator (8014)** per task.

---

## Quick start

```bash
pip install -r requirements.txt
# Optional: .env with OPENAI_API_KEY (default); or set PLANNER_MODEL=MedAIBase/MedGemma1.5:4b for Ollama
```

**Run Planner only (A2A server):**  
`python a2a_agents.py planner 8011`  
→ A2A server on `http://localhost:8011`

**Test Planner over HTTP (A2A):**  
Run the Planner on port 8011 as above, then from another shell:  
`python test.py` (uses default `http://localhost:8011`)  
or override: `python test.py --url http://localhost:8012`


## Wiring with other agents

1. **Start agents** (each on its port):  
   `python a2a_agents.py planner 8011`   
   (executor 8012, researcher 8013, validator 8014 when implemented)

2. **Orchestrator:**  
   - POST to Planner (8011) with user query → A2A `message/send`, then `tasks/get` for task id and result.  
   - Read plan from `result.artifacts[0].parts[0].data.result` (`query_summary`, `tasks`).  
   - For each `task`: POST to the URL for `task.agent` (8012=executor, 8013=researcher, 8014=validator) with `task.description` and `task.input_payload`; poll `tasks/get` until done.

3. **Env (optional):**  
   `PLANNER_A2A_URL`, `EXECUTOR_A2A_URL`, `RESEARCHER_A2A_URL`, `VALIDATOR_A2A_URL` (e.g. `http://host:8011`).

---

## Files

| File | Purpose |
|------|---------|
| **planner_agent.py** | Planner agent + `ExecutionPlan`; used by a2a_agents for planner. |
| **a2a_agents.py** | Run any agent as A2A server: `python a2a_agents.py <planner\|executor\|researcher\|validator> <port>`. |
| **a2a_client.py** | Example A2A client (simple A2A call to Planner). |
| **test.py** | Mock user queries against Planner **over HTTP A2A** (hits `http://localhost:8011` by default). |

---

## Config

- **planner_agent.py:** `MODEL_NAME` (default `MedAIBase/MedGemma1.5:4b`), `OLLAMA_HOST` for Ollama. For OpenAI: `PLANNER_MODEL=openai:gpt-4o-mini` and `.env` with `OPENAI_API_KEY`.

---

## Refs

- [A2A protocol](https://google.github.io/A2A/) · [Pydantic AI A2A](https://ai.pydantic.dev/a2a/) · [FastA2A](https://github.com/pydantic/fasta2a)
