"""
Example A2A client: call the Planner agent over HTTP, then show how to dispatch
tasks to other agents (Executor, Researcher, Validator).

Use this after deploying the Planner as an A2A server (e.g. localhost:8011).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid

import httpx
from fasta2a.client import A2AClient
from fasta2a.schema import Message, TextPart

# Optional: parse plan and show how you'd call other agents
from planner_agent import ExecutionPlan


PLANNER_URL = os.environ.get("PLANNER_A2A_URL", "http://localhost:8011")
POLL_INTERVAL = 0.5
POLL_TIMEOUT = 120


def build_user_message(text: str) -> Message:
    return Message(
        role="user",
        parts=[TextPart(kind="text", text=text)],
        kind="message",
        message_id=str(uuid.uuid4()),
    )


async def call_planner(query: str) -> ExecutionPlan | None:
    """Call the Planner A2A server and return the ExecutionPlan when done."""
    async with httpx.AsyncClient() as http_client:
        client = A2AClient(base_url=PLANNER_URL, http_client=http_client)
        message = build_user_message(query)
        print("Sending query to Planner at", PLANNER_URL, "...")
        response = await client.send_message(message)

        if "error" in response:
            print("Planner error:", response["error"], file=sys.stderr)
            return None

        task = response["result"]
        task_id = task["id"]
        print("Task id:", task_id, "| Status:", task["status"]["state"])

        # Poll until completed
        deadline = time.monotonic() + POLL_TIMEOUT
        while time.monotonic() < deadline:
            get_resp = await client.get_task(task_id)
            if "error" in get_resp:
                print("GetTask error:", get_resp["error"], file=sys.stderr)
                return None
            task = get_resp["result"]
            state = task["status"]["state"]
            print("  Status:", state)
            if state == "completed":
                break
            if state in ("failed", "rejected", "canceled"):
                print("  Task ended with state:", state, file=sys.stderr)
                return None
            await asyncio.sleep(POLL_INTERVAL)
        else:
            print("  Timeout waiting for completion", file=sys.stderr)
            return None

        # Read ExecutionPlan from artifacts (DataPart with result)
        artifacts = task.get("artifacts") or []
        for art in artifacts:
            for part in art.get("parts") or []:
                if part.get("kind") == "data" and "data" in part:
                    data = part["data"]
                    if "result" in data:
                        return ExecutionPlan.model_validate(data["result"])
        print("  No result artifact in task", file=sys.stderr)
        return None


def print_plan_and_dispatch_example(plan: ExecutionPlan) -> None:
    """Print the plan and show how you would dispatch to other agents."""
    print("\n--- Execution plan ---")
    print("Query summary:", plan.query_summary)
    print("\nTasks (assign to agents in order: Planner → Executor → Researcher → Validator):")
    for t in plan.tasks:
        payload = f"  payload={t.input_payload}" if t.input_payload else ""
        print(f"  {t.order}. [{t.agent}] {t.description}{payload}")

    print("\n--- How to call other agents ---")
    print("For each task above, your orchestrator would:")
    print("  - executor  → POST to Executor A2A server (e.g. http://localhost:8012) with task description + input_payload")
    print("  - researcher → POST to Researcher A2A server (e.g. http://localhost:8013)")
    print("  - validator  → POST to Validator A2A server (e.g. http://localhost:8014)")
    print("Use the same A2A protocol (message/send, tasks/get) with each agent's base URL.")


async def main_async() -> int:
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Run hub detection on my fMRI data and validate the results."
    plan = await call_planner(query)
    if plan is None:
        return 1
    print_plan_and_dispatch_example(plan)
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
