# Brain Network Chart A2A Server

A multi-agent system for brain network analysis using pydantic-ai and FastA2A.

## Agents

1. **Planner** - Understands queries and creates execution plans
2. **Executor** - Uses MCP tools for input-to-trait analysis
3. **Researcher** - Performs statistical analysis and database searches
4. **Validator** - Validates results and confirms query resolution

## Quick Start

### Option 1: Local Execution (Recommended for Testing)

Run agents locally in a single process:

```bash
python a2a_client.py
```

This is the simplest approach and works well for development. All agents run sequentially in the same Python process.

### Option 2: Distributed A2A Servers

Run each agent as an independent FastAPI server:

```bash
# Terminal 1
python a2a_agents.py planner 8011

# Terminal 2
python a2a_agents.py executor 8012

# Terminal 3
python a2a_agents.py researcher 8013

# Terminal 4
python a2a_agents.py validator 8014
```

Then in another terminal, call the client (after updating a2a_client.py to use HTTP calls).

## Files

- **a2a_client.py** - Client that orchestrates the multi-agent workflow (local execution)
- **a2a_agents.py** - Individual agent server definitions (can be exposed as FastAPI A2A servers)

## Configuration

Edit these constants in the files:

```python
OLLAMA_HOST = "yukon.acm.unc.edu:11434"
MODEL_NAME = "MedAIBase/MedGemma1.5:4b"
```

## Dependencies

```bash
pip install pydantic-ai uvicorn httpx
```
