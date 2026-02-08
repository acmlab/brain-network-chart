"""
Planner agent definition for the Brain Network MAS.

This module is intentionally independent so it can be reused from:
- A2A servers (e.g. small wrappers that expose the agent over HTTP)
- Local clients / orchestrators
- Other branches that define additional agents (executor, researcher, validator)
"""

from __future__ import annotations

from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

# -----------------------------------------------------------------------------
# Configuration (edit these for your environment)
# -----------------------------------------------------------------------------
# For quick testing with OpenAI (set OPENAI_API_KEY in env):
MODEL_NAME = "openai:gpt-4o-mini"
# For Ollama (local or remote):
# MODEL_NAME = "MedAIBase/MedGemma1.5:4b"
# OLLAMA_HOST = "yukon.acm.unc.edu:11434"
OLLAMA_HOST = "yukon.acm.unc.edu:11434"


# -----------------------------------------------------------------------------
# Planner: structured output types
# -----------------------------------------------------------------------------

AgentName = Literal["executor", "researcher", "validator"]


class TaskAssignment(BaseModel):
    """A single task assigned to one agent."""

    agent: AgentName = Field(description="Which agent should perform this task")
    description: str = Field(description="Clear description of what the agent should do")
    order: int = Field(ge=1, description="Execution order (1-based)")
    input_payload: dict | None = Field(
        default=None,
        description="Optional structured input for the agent (e.g. query, filters)",
    )


class ExecutionPlan(BaseModel):
    """Plan produced by the Planner: understood query and tasks per agent."""

    query_summary: str = Field(
        description="Short summary showing understanding of the user's query"
    )
    tasks: list[TaskAssignment] = Field(
        description="Ordered list of tasks to assign to executor, researcher, or validator"
    )


# -----------------------------------------------------------------------------
# Model and Planner agent
# -----------------------------------------------------------------------------

def _get_planner_model():
    """Use OpenAI API if MODEL_NAME starts with 'openai:', else Ollama."""
    if MODEL_NAME.startswith("openai:"):
        return MODEL_NAME  # pydantic-ai uses OPENAI_API_KEY from env
    base_url = f"http://{OLLAMA_HOST}/v1"
    client = AsyncOpenAI(base_url=base_url, api_key="ollama")
    return OpenAIChatModel(
        MODEL_NAME,
        provider=OpenAIProvider(openai_client=client),
    )


PLANNER_INSTRUCTIONS = """
You are the Planner agent in a brain network / fMRI analysis multi-agent system.

Your role:
1. Understand the user's query (analysis requests, visualization, data questions).
2. Create an execution plan: a sequence of tasks.
3. Assign each task to exactly one of these agents:
   - executor: Runs MCP tools, input-to-trait analysis, data processing pipelines.
   - researcher: Statistical analysis, literature/database searches, evidence lookup.
   - validator: Validates results, checks consistency, confirms the query is resolved.

Output a structured ExecutionPlan with:
- query_summary: your understanding of what the user wants.
- tasks: list of TaskAssignment, each with agent, description, order (1, 2, 3...), and optional input_payload.

Keep tasks focused and ordered by dependency (e.g. run analysis before validation).
"""


planner_agent: Agent[None, ExecutionPlan] = Agent(
    _get_planner_model(),
    output_type=ExecutionPlan,
    instructions=PLANNER_INSTRUCTIONS,
    name="planner",
    retries=2,
)


def get_planner_app():
    """Return the ASGI app for the Planner A2A server."""
    return planner_agent.to_a2a()

