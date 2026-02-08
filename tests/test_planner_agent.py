"""
Mock and unit tests for the planner agent: schemas, app, and mocked run.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# Import schemas without triggering planner agent creation (and thus env/API)
from planner_agent import (
    ExecutionPlan,
    MCP_TOOL_NAMES,
    PLANNER_INSTRUCTIONS,
    TaskAssignment,
    get_planner_app,
)


# -----------------------------------------------------------------------------
# Schema tests (no mocks)
# -----------------------------------------------------------------------------


def test_task_assignment_valid() -> None:
    t = TaskAssignment(
        agent="executor",
        description="Run connectivity analysis",
        order=1,
        input_payload={"dataset": "fmri_01"},
    )
    assert t.agent == "executor"
    assert t.order == 1
    assert t.input_payload == {"dataset": "fmri_01"}


def test_task_assignment_optional_payload() -> None:
    t = TaskAssignment(agent="researcher", description="Look up literature", order=2)
    assert t.input_payload is None


def test_task_assignment_invalid_agent() -> None:
    with pytest.raises(ValueError):
        TaskAssignment(agent="unknown", description="x", order=1)


def test_task_assignment_order_must_be_positive() -> None:
    with pytest.raises(ValueError):
        TaskAssignment(agent="executor", description="x", order=0)


def test_execution_plan_valid() -> None:
    plan = ExecutionPlan(
        query_summary="User wants connectivity analysis and validation.",
        tasks=[
            TaskAssignment(agent="executor", description="Run analysis", order=1),
            TaskAssignment(agent="validator", description="Validate results", order=2),
        ],
    )
    assert len(plan.tasks) == 2
    assert plan.tasks[0].agent == "executor"
    assert plan.tasks[1].agent == "validator"


def test_execution_plan_roundtrip() -> None:
    plan = ExecutionPlan(
        query_summary="Summary",
        tasks=[TaskAssignment(agent="researcher", description="Search", order=1)],
    )
    data = plan.model_dump()
    restored = ExecutionPlan.model_validate(data)
    assert restored.query_summary == plan.query_summary
    assert len(restored.tasks) == 1
    assert restored.tasks[0].agent == "researcher"


# -----------------------------------------------------------------------------
# App test
# -----------------------------------------------------------------------------


def test_get_planner_app_returns_asgi_app() -> None:
    app = get_planner_app()
    assert callable(app)
    # ASGI apps are called with (scope, receive, send)
    assert hasattr(app, "__call__")


# -----------------------------------------------------------------------------
# Mock run test (no real API call)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_planner_run_mock_returns_plan() -> None:
    from planner_agent import planner_agent

    mock_plan = ExecutionPlan(
        query_summary="Mocked: user asked for connectivity analysis.",
        tasks=[
            TaskAssignment(
                agent="executor",
                description="Run connectivity analysis on fMRI data",
                order=1,
                input_payload={"query": "connectivity"},
            ),
            TaskAssignment(
                agent="validator",
                description="Validate the analysis results",
                order=2,
            ),
        ],
    )

    class MockResult:
        output = mock_plan

    with patch.object(planner_agent, "run", new_callable=AsyncMock, return_value=MockResult()):
        result = await planner_agent.run("Run connectivity analysis and validate.")
    assert result.output is mock_plan
    assert result.output.query_summary.startswith("Mocked:")
    assert len(result.output.tasks) == 2
    assert result.output.tasks[0].agent == "executor"
    assert result.output.tasks[1].agent == "validator"


def test_planner_instructions_mention_agents() -> None:
    assert "executor" in PLANNER_INSTRUCTIONS
    assert "researcher" in PLANNER_INSTRUCTIONS
    assert "validator" in PLANNER_INSTRUCTIONS
    assert "ExecutionPlan" in PLANNER_INSTRUCTIONS or "execution plan" in PLANNER_INSTRUCTIONS.lower()


def test_mcp_tool_names_and_instructions_aligned() -> None:
    for tool in MCP_TOOL_NAMES:
        assert tool in PLANNER_INSTRUCTIONS, f"MCP tool {tool!r} should be mentioned in planner instructions"
