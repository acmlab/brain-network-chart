"""
A2A Agents: Individual agent servers using pydantic-ai
Each agent runs as its own FastAPI A2A server.

To run all agents:
  python a2a_agents.py planner 8011 &
  python a2a_agents.py executor 8012 &
  python a2a_agents.py researcher 8013 &
  python a2a_agents.py validator 8014 &
"""

import sys
import asyncio
import os
from typing import Optional
from pydantic_ai import Agent
import uvicorn

# Ollama Configuration
OLLAMA_HOST = "yukon.acm.unc.edu:11434"
MODEL_NAME = "MedAIBase/MedGemma1.5:4b"
OLLAMA_BASE_URL = f"http://{OLLAMA_HOST}"
a2a_host = 'localhost'
# Set environment variable for Ollama
os.environ["OLLAMA_BASE_URL"] = OLLAMA_BASE_URL


# ============================================================================
# Define Agents
# ============================================================================
# Planner: use dedicated planner_agent module (structured ExecutionPlan, MCP-aware).
from planner_agent import create_planner_agent as _create_planner_agent

def create_planner_agent() -> Agent:
    """Agent 1: Parse query and create structured execution plan (executor/researcher/validator)."""
    return _create_planner_agent()


def create_executor_agent() -> Agent:
    """Agent 2: Use MCP tools for input-to-trait analysis"""
    return Agent(
        f"ollama:{MODEL_NAME}",
        name="executor",
        instructions="""You are an executor agent. You select MCP tools (input-to-trait analysis),
configure parameters, execute analysis, and extract keywords for the researcher.
Format: Tool choice, Config, Results as table, 3-5 keywords."""
    )


def create_researcher_agent() -> Agent:
    """Agent 3: Statistical analysis and database search"""
    return Agent(
        f"ollama:{MODEL_NAME}",
        name="researcher",
        instructions="""You are a researcher agent. You search PubMed and DuckDuckGo databases
for the given keywords, perform statistical analysis, and determine if executor
config needs updating. Respond with: databases used, findings, config update needed (yes/no)."""
    )


def create_validator_agent() -> Agent:
    """Agent 4: Validate all outputs"""
    return Agent(
        f"ollama:{MODEL_NAME}",
        name="validator",
        instructions="""You are a validator agent. Check if the original query was answered
by the executor and researcher results. Provide: is_valid (yes/no), query_answered (yes/no),
confidence (0-100%), issues, and recommendations."""
    )


# ============================================================================
# Agent Servers
# ============================================================================

def create_planner_app():
    """Create planner A2A server"""
    agent = create_planner_agent()
    return agent.to_a2a()


def create_executor_app():
    """Create executor A2A server"""
    agent = create_executor_agent()
    return agent.to_a2a()


def create_researcher_app():
    """Create researcher A2A server"""
    agent = create_researcher_agent()
    return agent.to_a2a()


def create_validator_app():
    """Create validator A2A server"""
    agent = create_validator_agent()
    return agent.to_a2a()


# ============================================================================
# CLI to run individual agents
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("""
Usage: python a2a_agents.py <agent_name> <port>

Agent Names:
  - planner   (creates execution plan)
  - executor  (uses MCP tools)
  - researcher (searches databases)
  - validator (validates results)

Examples:
  python a2a_agents.py planner 8001
  python a2a_agents.py executor 8002
  python a2a_agents.py researcher 8003
  python a2a_agents.py validator 8004
""")
        sys.exit(1)

    agent_name = sys.argv[1].lower()
    port = int(sys.argv[2])

    # Create appropriate app based on agent name
    apps = {
        "planner": create_planner_app,
        "executor": create_executor_app,
        "researcher": create_researcher_app,
        "validator": create_validator_app,
    }

    if agent_name not in apps:
        print(f"Error: Unknown agent '{agent_name}'")
        print(f"Available: {', '.join(apps.keys())}")
        sys.exit(1)

    app = apps[agent_name]()

    print(f"Starting {agent_name} agent on port {port}...")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Host: {OLLAMA_HOST}")
    print(f"  API Docs: http://{a2a_host}:{port}/docs")

    uvicorn.run(app, host=f"{a2a_host}", port=port, log_level="info")