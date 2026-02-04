"""
Client that orchestrates the Brain Network multi-agent workflow.
Option 1 (this script): run agents locally in one process.
Option 2: run a2a_agents.py for each agent in separate terminals, then switch
          this client to HTTP calls to those A2A servers.
"""

from __future__ import annotations

import asyncio
import sys

# Local execution: use the planner agent from a2a_agents
from a2a_agents import planner_agent


async def run_planner(query: str) -> None:
    """Run the Planner agent locally and print the execution plan."""
    print("Planner (local) processing query:", repr(query), "\n")
    result = await planner_agent.run(query)
    if not result.output:
        print("Planner returned no output.")
        return
    plan = result.output
    print("Query summary:", plan.query_summary)
    print("\nTasks:")
    for t in plan.tasks:
        payload = f" | payload={t.input_payload}" if t.input_payload else ""
        print(f"  {t.order}. [{t.agent}] {t.description}{payload}")
    print("\n(Executor, Researcher, Validator not yet implemented — plan only.)")


def main() -> int:
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Run connectivity analysis on my fMRI data and validate the results."
    asyncio.run(run_planner(query))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
