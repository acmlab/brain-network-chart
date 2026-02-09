"""
Planner agent definition for the Brain Network MAS.

Pipeline order: Planner (1) → Executor (2) → Researcher (3) → Validator (4).

This module is intentionally independent so it can be reused from:
- a2a_agents.py: use create_planner_agent() and get_planner_app() for the planner server.
- A2A clients (e.g. a2a_client.py) call the Planner via HTTP; no direct import needed.
- Other branches that define executor, researcher, validator.
"""

from __future__ import annotations

import json
import os
from typing import Literal

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

load_dotenv()

# -----------------------------------------------------------------------------
# Configuration (edit these for your environment)
# -----------------------------------------------------------------------------
# Default: MedGemma via Ollama. For OpenAI set PLANNER_MODEL=openai:gpt-4o-mini and OPENAI_API_KEY in .env.
MODEL_NAME = os.environ.get("PLANNER_MODEL", "MedAIBase/MedGemma1.5:4b")
_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "")
if _OLLAMA_BASE_URL:
    _u = _OLLAMA_BASE_URL.replace("https://", "").replace("http://", "").rstrip("/")
    OLLAMA_HOST = _u
else:
    OLLAMA_HOST = "yukon.acm.unc.edu:11434"
# To use MedGemma: set PLANNER_MODEL=MedAIBase/MedGemma1.5:4b and ensure Ollama is reachable at OLLAMA_HOST.


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
# Brain Network Analysis MCP server (Executor calls this backend)
# -----------------------------------------------------------------------------
# Model Context Protocol (MCP) server for brain network analysis: signal processing
# and graph-based hub detection. HTTP REST API (FastMCP) on yukon.acm.unc.edu:8010.
# Features: progress streaming, timestamped logging, async-ready (Starlette).
# Executor tasks use input_payload with "tool" and tool-specific params.

MCP_SERVER_BASE_URL = "http://yukon.acm.unc.edu:8010"

MCP_TOOL_NAMES = (
    "run_cfc_wavelet_analysis",  # CFC wavelet analysis
    "run_hub_detection",         # Hub detection (single or multi-network)
    "get_growth_curve",          # Growth curve / developmental trajectory
    "run_normative_analysis",    # Normative analysis with overlay data
)

# -----------------------------------------------------------------------------
# Model and Planner agent
# -----------------------------------------------------------------------------

# Timeout for LLM requests (Ollama/remote can be slow; default httpx is ~5s).
LLM_TIMEOUT_SECONDS = float(os.environ.get("PLANNER_LLM_TIMEOUT", "120.0"))


def _get_planner_model():
    """Use OpenAI if MODEL_NAME starts with 'openai:', else Ollama (e.g. MedGemma)."""
    if MODEL_NAME.startswith("openai:"):
        return MODEL_NAME  # requires OPENAI_API_KEY in env
    base = _OLLAMA_BASE_URL.rstrip("/") if _OLLAMA_BASE_URL else f"http://{OLLAMA_HOST}"
    base_url = f"{base}/v1" if not base.endswith("/v1") else base
    # Use a longer timeout for Ollama (remote or slow model)
    timeout = httpx.Timeout(LLM_TIMEOUT_SECONDS, connect=30.0)
    http_client = httpx.AsyncClient(timeout=timeout)
    client = AsyncOpenAI(
        base_url=base_url,
        api_key="ollama",
        http_client=http_client,
    )
    return OpenAIChatModel(
        MODEL_NAME,
        provider=OpenAIProvider(openai_client=client),
    )


PLANNER_INSTRUCTIONS = """
You are the Planner agent in a brain network / fMRI analysis multi-agent system.
The Executor calls a Brain Network Analysis MCP server (HTTP REST API at yukon.acm.unc.edu:8010)
with progress streaming, timestamped logging, and async-ready processing.

Your role:
1. Understand the user's query (analysis requests, visualization, data questions).
2. Create an execution plan: a sequence of tasks.
3. Assign each task to exactly one of these agents.

   Users submit queries (and often upload BOLD or FC matrices) through a frontend UI; uploads are handled securely there. When the user refers to uploaded data, "the data I attached", "my BOLD", "my FC matrix", or similar, set data_path in executor input_payload to a clear reference (e.g. "uploaded_bold", "uploaded_fc"). The orchestrator receives the actual secure path from the frontend and substitutes it when calling the executor—you do not need to know or emit real file paths.

   - executor: Runs MCP tools for brain network analysis. Available tools (set input_payload.tool and params):
     * run_cfc_wavelet_analysis — Cross-frequency coupling (CFC) wavelet analysis: compute harmonic wavelets from brain network adjacency matrices with iterative optimization and error tracking. Params: data_path, window_size, step_size, padding, ratio, wavelets_num, beta, gamma, max_iter, node_select. Use when the user asks for CFC, cross-frequency coupling, wavelet analysis, or harmonic analysis of connectivity.
     * run_hub_detection — Hub detection: identify critical hub nodes. Single-network via spectral embedding; multi-network via Grassmann manifold optimization. Params: data_path, window_size, step_size, padding, ratio, k, hub_num, use_group. Use when the user asks for hub detection, critical nodes, single-network or multi-network hub analysis.
     * get_growth_curve — Normative developmental trajectory: growth curves and normative curves for brain metrics (e.g. global mean FC, system segregation). Params: phenotype (e.g. "Global mean of FC", "Global system segregation"). Use when the user asks for developmental trajectory, growth curve, normative curve, or phenotype over age.
     * run_normative_analysis — Normative analysis with overlay data. Params: x_phenotype, y_path, age_col, val_col. Use when the user asks for normative comparison, overlay, or age-matched norms.
     Data loading: the server can read brain activity from CSV with sliding-window extraction. Users upload BOLD/FC via the frontend UI (secure). Always include data_path in executor input_payload when they refer to "my data", uploaded matrices, or an attached file—use a reference like "uploaded_bold" or "uploaded_fc"; the frontend/orchestrator supplies the real path when invoking the executor.
     For executor tasks, set input_payload to {"tool": "<tool_name>", "data_path": "<reference or path>", ...params}.

   - researcher: Statistical analysis, literature/database searches, evidence lookup. Use when the user needs literature, PubMed, or statistical interpretation of results.

   - validator: Validates results from the Executor and Researcher: checks consistency, confirms the original query is resolved, and reports confidence/issues/recommendations. Always assign a validator task after executor (and researcher if used) so the user gets a clear answer and quality check.

Output format:
- You MUST respond with PURE JSON only, no markdown, no prose, no comments, no explanations.
- You MUST return EXACTLY ONE JSON object, not multiple objects, not a list.
- NEVER return a bare payload like {"tool": "..."} or any dict that is not wrapped as an ExecutionPlan.
- The JSON must ALWAYS match this ExecutionPlan schema exactly:

{
  "query_summary": "short summary string",
  "tasks": [
    {
      "agent": "executor" | "researcher" | "validator",
      "description": "what this task should do",
      "order": 1,
      "input_payload": { ... } | null
    }
  ]
}

- "query_summary" is ALWAYS required.
- "tasks" is ALWAYS required (use an empty list [] only if absolutely necessary).
- Every task MUST have all fields: agent, description, order, input_payload (use null if you have no payload).
- Do NOT include any extra top-level keys beyond "query_summary" and "tasks".
- Do NOT include any extra commentary or text before or after the JSON object.

Keep tasks ordered by dependency: run executor (and researcher if needed) before validator. When the user mentions CFC, hub detection, growth curve, normative analysis, sliding window, or CSV brain data, assign an executor task with the corresponding tool and sensible defaults for missing params.
"""


# NOTE: We use plain-text JSON output (str) so that MedGemma via Ollama does NOT need
# OpenAI-style tools/function-calling. Structured typing is enforced by our own
# JSON parsing into the ExecutionPlan model below.
planner_agent: Agent[None, str] = Agent(
    _get_planner_model(),
    output_type=str,
    instructions=PLANNER_INSTRUCTIONS,
    name="planner",
    retries=2,
)


async def run_planner(query: str) -> ExecutionPlan:
    """Run the planner LLM and parse its JSON into an ExecutionPlan.

    MedGemma (via Ollama) may sometimes wrap JSON with extra text; we robustly
    extract the first {...} block before parsing.
    """
    result = await planner_agent.run(query)
    if not result.output:
        raise RuntimeError("Planner returned empty output")

    text = result.output.strip()

    # First try direct JSON parse
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: extract the first balanced {...} JSON object
        start = text.find("{")
        if start == -1:
            raise RuntimeError(f"Planner output is not valid JSON: {text[:200]!r}")

        depth = 0
        end = None
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if end is None:
            raise RuntimeError(f"Planner output has unbalanced braces: {text[:200]!r}")

        snippet = text[start : end + 1]
        data = json.loads(snippet)

    return ExecutionPlan.model_validate(data)


def create_planner_agent() -> Agent:
    """Return the Planner agent. Used by a2a_agents.create_planner_app()."""
    return planner_agent


def get_planner_app():
    """Return the ASGI app for the Planner A2A server (a2a_agents or uvicorn)."""
    return planner_agent.to_a2a()

