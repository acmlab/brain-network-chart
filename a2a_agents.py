"""
Brain Network Chart A2A agents.

This file is intended to host multiple agents (planner, executor, researcher,
validator, etc.) on main. On this branch we only implement the Planner and
delegate its definition to `planner_agent.py`.

Run as: python a2a_agents.py <agent_name> <port>
e.g. python a2a_agents.py planner 8011
"""

from __future__ import annotations

import argparse
import sys

from planner_agent import get_planner_app


def main() -> int:
    """CLI entrypoint to run individual agents as A2A servers.

    On this branch only the `planner` agent is available; other agents
    will be added in main or other feature branches.
    """
    parser = argparse.ArgumentParser(description="Run a Brain Network A2A agent server")
    parser.add_argument("agent", choices=["planner"], help="Agent to run")
    parser.add_argument("port", type=int, help="Port to bind (e.g. 8011)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    args = parser.parse_args()

    if args.agent == "planner":
        app = get_planner_app()
    else:
        print(f"Unknown agent: {args.agent}", file=sys.stderr)
        return 1

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
