"""
Planner agent definition for the Brain Network MAS.

Pipeline order: Planner (1) → Executor (2) → Researcher (3) → Validator (4).

This module is intentionally independent so it can be reused from:
- A2A servers (e.g. small wrappers that expose the agent over HTTP)
- Local clients / orchestrators
- Other branches that define additional agents (executor, researcher, validator)
"""

from __future__ import annotations

from typing import Literal

from dotenv import load_dotenv

from openai import AsyncOpenAI

load_dotenv()
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

# -----------------------------------------------------------------------------
# Configuration (edit these for your environment)
# -----------------------------------------------------------------------------
# Default: MedGemma via Ollama (Planner agent). For OpenAI set MODEL_NAME and OPENAI_API_KEY.
MODEL_NAME = "MedAIBase/MedGemma1.5:4b"
OLLAMA_HOST = "yukon.acm.unc.edu:11434"
# Optional: use OpenAI instead (set in env or here):
# MODEL_NAME = "openai:gpt-4o-mini"  # requires OPENAI_API_KEY in .env


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
# MCP server context (Executor / Validator call this backend)
# -----------------------------------------------------------------------------
# Brain Network Analysis MCP server: HTTP REST API for analysis tools.
# Base URL typically: http://yukon.acm.unc.edu:8010 (see README).
# Executor tasks should use input_payload with a "tool" and tool-specific params.

MCP_TOOL_NAMES = (
    "run_cfc_wavelet_analysis",  # CFC wavelet analysis on BOLD connectivity
    "run_hub_detection",         # Hub detection (single or multi-network)
    "get_growth_curve",          # Growth curve / developmental phenotype
    "run_normative_analysis",    # Normative analysis with overlay data
)

# -----------------------------------------------------------------------------
# Model and Planner agent
# -----------------------------------------------------------------------------

def _get_planner_model():
    """Use OpenAI if MODEL_NAME starts with 'openai:', else Ollama (e.g. MedGemma)."""
    if MODEL_NAME.startswith("openai:"):
        return MODEL_NAME  # requires OPENAI_API_KEY in env
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
   - executor: Runs MCP tools for brain network analysis. Available tools (use input_payload.tool and params):
     * run_cfc_wavelet_analysis: Cross-frequency coupling wavelet analysis. Params: data_path, window_size, step_size, padding, ratio, wavelets_num, beta, gamma, max_iter, node_select.
     * run_hub_detection: Hub detection in single or multiple networks. Params: data_path, window_size, step_size, padding, ratio, k, hub_num, use_group.
     * get_growth_curve: Developmental trajectory / growth curve. Params: phenotype (e.g. "Global mean of FC", "Global system segregation").
     * run_normative_analysis: Normative analysis with overlay data. Params: x_phenotype, y_path, age_col, val_col.
     For executor tasks, set input_payload to {"tool": "<tool_name>", ...params}. Include data_path when the user refers to "my data" or a file (e.g. after upload).
   - researcher: Statistical analysis, literature/database searches, evidence lookup.
   - validator: Validates results, checks consistency, confirms the query is resolved.

Output a structured ExecutionPlan with:
- query_summary: your understanding of what the user wants.
- tasks: list of TaskAssignment, each with agent, description, order (1, 2, 3...), and optional input_payload.

Keep tasks focused and ordered by dependency (e.g. run analysis before validation). When the user asks for CFC, hub detection, growth curves, or normative analysis, assign an executor task with the corresponding tool and sensible defaults for missing params.
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

