# Deploying the Planner Agent and Wiring the A2A Client

This guide walks you through deploying the **Planner agent (MedGemma)** on your server, then **running the full orchestrator** and wiring A2A clients to call the Planner and other agents (Executor, Researcher, Validator).

---

## Task checklist (Planner agent)

| Task | Status |
|------|--------|
| Planner agent (MedGemma) | ✅ Default model is `MedAIBase/MedGemma1.5:4b` via Ollama |
| Deploy A2A client to call other agents | ✅ Orchestrator (or `a2a_client.py` / HTTP client) calls Planner over HTTP; same pattern for Executor/Researcher/Validator |
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

From the same machine or another machine with network access to the server you can call the Planner over HTTP using the A2A protocol.

**Option A – Local in-process (no HTTP):** use `a2a_client.py` to run the Planner in the same process and print the plan (good for quick tests).

```bash
python a2a_client.py "Run hub detection on my fMRI data and validate the results."
```

**Option B – HTTP A2A client:** use any A2A client (e.g. your own script or the official A2A SDK) to send a `message/send` request to the Planner URL, then poll `tasks/get` until the task is completed. The plan is in `result.artifacts[0].parts[0].data.result` (see README for curl examples).

Set the Planner URL via env when calling a remote server:

- Windows: `set PLANNER_A2A_URL=http://your-server:8011`
- Linux/Mac: `export PLANNER_A2A_URL=http://your-server:8011`

---

## 5. Run the full orchestrator and wire up other agents

The **full orchestrator** is the process that (1) calls the Planner to get an `ExecutionPlan`, then (2) calls the Executor, Researcher, and Validator A2A servers for each task in the plan. Each agent runs as its own A2A server; the orchestrator is the A2A client that ties them together.

### 5.1 Start all agent servers

Run each agent on its own port (four terminals or background processes):

```bash
# Terminal 1 – Planner (must be first; produces the plan)
python a2a_agents.py planner 8011

# Terminal 2 – Executor (MCP tools, analysis)
python a2a_agents.py executor 8012

# Terminal 3 – Researcher (databases, stats)
python a2a_agents.py researcher 8013

# Terminal 4 – Validator (validates results)
python a2a_agents.py validator 8014
```

Default host is `localhost`; to bind all interfaces use `--host 0.0.0.0` (and adjust firewall/URLs).

**Port map:**

| Agent     | Default port | Role                          |
|----------|--------------|-------------------------------|
| Planner  | 8011         | Understand query, plan tasks, assign to other agents |
| Executor | 8012         | Run MCP tools (e.g. CFC, hub detection, growth curve) |
| Researcher | 8013       | Statistical / literature search |
| Validator | 8014        | Validate outputs and confirm query resolved |

### 5.2 Orchestrator flow (high level)

1. **Get the plan**
   - Send the user query to the **Planner** A2A server (e.g. `http://localhost:8011`).
   - Use A2A `message/send` with the query text in `params.message.parts` (e.g. `kind: "message"`, `role: "user"`, `parts: [{ "kind": "text", "text": "..." }]`).
   - Poll `tasks/get` with the returned task `id` until `status.state` is `"completed"`.
   - Read the **ExecutionPlan** from `result.artifacts[0].parts[0].data.result` (contains `query_summary` and `tasks`).

2. **Run tasks in order**
   - For each `task` in `plan.tasks` (already ordered by `task.order`):
     - Choose the A2A server by `task.agent`:
       - `executor` → e.g. `http://localhost:8012`
       - `researcher` → e.g. `http://localhost:8013`
       - `validator` → e.g. `http://localhost:8014`
     - Send an A2A `message/send` to that server with input derived from `task.description` and `task.input_payload` (e.g. for Executor, `input_payload` may include `tool` and MCP parameters).
     - Poll `tasks/get` until that task completes.
     - Optionally pass the result (or a summary) into the next task or into the Validator.

3. **Aggregate and return**
   - After all tasks complete, the orchestrator returns (or forwards) the combined result to the frontend or caller.

### 5.3 Environment variables for the orchestrator

So the orchestrator can point at different hosts/ports, use env vars (or config) for each agent base URL:

| Variable (example)   | Default / meaning        |
|----------------------|--------------------------|
| `PLANNER_A2A_URL`    | `http://localhost:8011`  |
| `EXECUTOR_A2A_URL`   | `http://localhost:8012`  |
| `RESEARCHER_A2A_URL` | `http://localhost:8013`  |
| `VALIDATOR_A2A_URL`  | `http://localhost:8014`  |

The orchestrator script (or frontend gateway) should read these and call the corresponding URL for each `task.agent`.

### 5.4 Executor task input

For tasks assigned to **executor**, the Planner fills `input_payload` with a `tool` name and tool-specific parameters (see `planner_agent.MCP_TOOL_NAMES` and the Planner instructions). The orchestrator sends this (e.g. as the user message or in a structured part) to the Executor A2A server; the Executor agent then calls the MCP backend and returns results (e.g. for the Researcher or Validator to consume).

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
   - Test (in-process): `python a2a_client.py "What analyses can you run?"`
   - Or call over HTTP with an A2A client; you should see a plan with `query_summary` and `tasks` (executor / researcher / validator).

2. **Full orchestrator (all four agents)**
   - Start all four: `planner 8011`, `executor 8012`, `researcher 8013`, `validator 8014`.
   - Run your orchestrator script with the user query; it should get the plan from the Planner, then send each task to the right agent URL and collect results.

---

## Summary

- **Planner (MedGemma)** is the first agent; it understands the query, plans tasks, and assigns them to executor / researcher / validator.
- **Deploy:** Install deps, run `python a2a_agents.py planner 8011` (optionally under systemd). For the full pipeline, run all four agents on 8011–8014.
- **Full orchestrator:** Call the Planner A2A server to get an `ExecutionPlan`, then for each task call the corresponding agent (Executor / Researcher / Validator) via its A2A URL using `message/send` and `tasks/get`. Use `PLANNER_A2A_URL`, `EXECUTOR_A2A_URL`, etc. to configure base URLs.
