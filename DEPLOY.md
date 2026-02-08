# Deploying the Planner Agent and Wiring the A2A Client

This guide walks you through deploying the **Planner agent (MedGemma)** on your server and wiring an A2A client to call it and other agents.

---

## Task checklist (Planner agent)

| Task | Status |
|------|--------|
| Planner agent (MedGemma) | ✅ Default model is `MedAIBase/MedGemma1.5:4b` via Ollama |
| Deploy A2A client to call other agents: example | ✅ `a2a_client_http.py` calls Planner over HTTP and shows how to dispatch to Executor/Researcher/Validator |
| Understand query | ✅ Planner produces `query_summary` in `ExecutionPlan` |
| Plan tasks | ✅ Planner produces ordered `tasks` in `ExecutionPlan` |
| Assign tasks to agents | ✅ Each task has `agent` (executor / researcher / validator) and optional `input_payload` |
| Expose as A2A server: localhost:8011 | ✅ `python a2a_agents.py planner 8011` |

---

## 1. Prerequisites on the server

- **Python 3.11+**
- **Ollama** running with MedGemma (or another model). For remote Ollama, use the same host as in the Brain Network MCP docs (e.g. `yukon.acm.unc.edu:11434`).
- If you use **OpenAI** instead of MedGemma: set `OPENAI_API_KEY` and in `planner_agent.py` set `MODEL_NAME = "openai:gpt-4o-mini"` (or use env).

---

## 2. Install and configure

On the server (or in a venv):

```bash
cd brain-network-chart
python -m venv .venv
# Windows:   .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate

pip install -r requirements.txt
```

Optional: use **MedGemma via Ollama** (default in code):

- Ensure Ollama is reachable at `OLLAMA_HOST` (in `planner_agent.py`, default `yukon.acm.unc.edu:11434`).
- Default model is `MedAIBase/MedGemma1.5:4b`. Change `MODEL_NAME` / `OLLAMA_HOST` in `planner_agent.py` if your setup differs.

Optional: use **OpenAI**:

- Create `.env` with `OPENAI_API_KEY=sk-...`.
- In `planner_agent.py` set `MODEL_NAME = "openai:gpt-4o-mini"` (and leave `load_dotenv()` as is).

---

## 3. Run the Planner as an A2A server

Bind to all interfaces so the server is reachable from other machines (e.g. your laptop running the client):

```bash
python a2a_agents.py planner 8011
# Listens on http://0.0.0.0:8011
```

To listen only on localhost:

```bash
python a2a_agents.py planner 8011 --host 127.0.0.1
```

Keep this process running (or run it under systemd/supervisor; see below).

---

## 4. Call the Planner from an A2A client

From the same machine or another machine with network access to the server:

```bash
# Planner on same machine
python a2a_client_http.py "Run hub detection on my fMRI data and validate the results."

# Planner on a remote server
set PLANNER_A2A_URL=http://your-server:8011
python a2a_client_http.py "Run hub detection on my fMRI data and validate the results."
```

Linux/Mac:

```bash
export PLANNER_A2A_URL=http://your-server:8011
python a2a_client_http.py "Run hub detection on my fMRI data and validate the results."
```

The script will:

1. Send the query to the Planner A2A server (HTTP, A2A protocol).
2. Poll until the task completes.
3. Print the execution plan (query summary + tasks per agent).
4. Print how to call the other agents (Executor, Researcher, Validator) using the same A2A protocol.

---

## 5. Wire up other agents (Executor, Researcher, Validator)

When you run the Executor (and later Researcher, Validator) as separate A2A servers:

1. **Start each agent on its own port**, e.g.:
   - Planner: `8011`
   - Executor: `8012`
   - Researcher: `8013`
   - Validator: `8014`

2. **Orchestrator flow:**
   - Call the Planner (e.g. with `a2a_client_http.py` or your own A2A client) to get an `ExecutionPlan`.
   - For each task in `plan.tasks`, check `task.agent` and POST to the corresponding agent’s A2A URL using the same A2A protocol (`message/send`, then `tasks/get` until completed).
   - Use `task.description` and `task.input_payload` as the input for that agent (e.g. Executor uses `input_payload.tool` and params to call the MCP server).

3. **Example:** For an `executor` task, your orchestrator would send a message to the Executor A2A server at `http://localhost:8012` with a body that includes the task’s description and `input_payload`; the Executor agent then runs the MCP tool and returns an `ExecutorResult`.

---

## 6. Run the Planner under a process manager (optional)

### systemd (Linux)

Create `/etc/systemd/system/brain-planner.service`:

```ini
[Unit]
Description=Brain Network Planner A2A Agent
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/brain-network-chart
Environment=PATH=/path/to/brain-network-chart/.venv/bin
ExecStart=/path/to/brain-network-chart/.venv/bin/python a2a_agents.py planner 8011
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable brain-planner
sudo systemctl start brain-planner
sudo systemctl status brain-planner
```

### Windows (run in background)

Use `pythonw` or run in a separate terminal, or wrap with NSSM / Task Scheduler.

---

## 7. Quick verification

1. **Planner only**
   - Start: `python a2a_agents.py planner 8011`
   - Test: `python a2a_client_http.py "What analyses can you run?"`
   - You should see a plan with tasks and agent assignments.

2. **With Executor (when implemented)**
   - Terminal 1: `python a2a_agents.py planner 8011`
   - Terminal 2: `python a2a_agents.py executor 8012`
   - Use the HTTP client to get a plan, then have your orchestrator send executor tasks to `http://localhost:8012`.

---

## Summary

- **Planner (MedGemma)** is the first agent; it understands the query, plans tasks, and assigns them to executor / researcher / validator.
- **Deploy:** Install deps, run `python a2a_agents.py planner 8011` (optionally under systemd).
- **Wire client:** Use `a2a_client_http.py` with `PLANNER_A2A_URL` pointing at your server; extend the same pattern to call Executor, Researcher, and Validator by their URLs.
