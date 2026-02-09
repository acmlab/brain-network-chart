"""
Run mock user inquiries against the Planner agent (in-process) and print the returned plans.

Usage:
  python test_planner_queries.py                    # run all mock queries
  python test_planner_queries.py --query "your text" # run one custom query
  python test_planner_queries.py -n 1                # run only the first mock query

No A2A server required; uses planner_agent.run() directly.

If you get "Request timed out": the Planner calls the LLM (Ollama or OpenAI). Use OpenAI
for quick tests (in planner_agent.py set MODEL_NAME = "openai:gpt-4o-mini" and set
OPENAI_API_KEY in .env), or run Ollama locally (OLLAMA_HOST=localhost:11434). Remote
Ollama may need VPN; timeout is configurable via PLANNER_LLM_TIMEOUT (default 120s).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from planner_agent import planner_agent

# -----------------------------------------------------------------------------
# Mock user inquiries — oral, conversational (clinicians / researchers)
# -----------------------------------------------------------------------------

MOCK_QUERIES = [
    "I’ve got this fMRI run from last week, can we look at connectivity and make sure it’s okay?",
    "We’re interested in the cross-frequency stuff, the wavelet one — can you do that on our BOLD data?",
    "Need to find the hubs in one of our networks, then someone should double-check the output.",
    "Can we get the growth curve for global mean FC? I want to see it and have it checked.",
    "We have phenotype and overlay — can you run the normative thing and then confirm it’s right?",
    "What can this system actually do? Like, run something and then validate it.",
    # Queries that should trigger the researcher (literature, PubMed, stats, evidence)
    "Run hub detection on our data, then see what the literature says about these hubs and check the result.",
    "We did a CFC analysis — can someone look up PubMed or similar for how this compares to norms and then validate?",
    "I need the growth curve for system segregation and I want to know what's in the literature about it, then validate.",
    "Do the normative analysis, have someone search for evidence or stats on it, and then confirm it's right.",
    # Queries with uploaded BOLD / FC matrices (user uploads data along with query)
    "I'm uploading our BOLD matrix — can we run the CFC wavelet analysis on it and validate?",
    "Attached is our FC matrix; we need hub detection on it and then someone to double-check.",
    "Here's my uploaded BOLD and FC. I want connectivity and hub analysis, then check the results.",
]

# -----------------------------------------------------------------------------
# Run and print
# -----------------------------------------------------------------------------


def print_plan(query: str, plan) -> None:
    """Pretty-print an ExecutionPlan."""
    print("─" * 60)
    print("Query:", query)
    print("─" * 60)
    print("Summary:", plan.query_summary)
    print()
    print("Tasks:")
    for t in plan.tasks:
        payload = f"  payload={t.input_payload}" if t.input_payload else ""
        print(f"  {t.order}. [{t.agent}] {t.description}{payload}")
    print()


async def run_one(query: str) -> bool:
    """Run the Planner on one query; return True if success."""
    try:
        result = await planner_agent.run(query)
        if result.output is None:
            print("Planner returned no output for:", repr(query), "\n")
            return False
        print_plan(query, result.output)
        return True
    except Exception as e:
        print(f"Error for query {repr(query)}: {e}\n", file=sys.stderr)
        return False


async def main() -> int:
    parser = argparse.ArgumentParser(description="Test Planner with mock user inquiries")
    parser.add_argument(
        "-q", "--query",
        type=str,
        help="Run a single custom query instead of mock list",
    )
    parser.add_argument(
        "-n", "--num",
        type=int,
        default=None,
        help="Run only the first N mock queries (default: all)",
    )
    args = parser.parse_args()

    if args.query:
        queries = [args.query]
    else:
        n = args.num
        queries = MOCK_QUERIES[:n] if n is not None else MOCK_QUERIES

    print("Planner agent: mock user inquiry test (in-process)")
    print("Queries to run:", len(queries), "\n")

    ok = 0
    for q in queries:
        if await run_one(q):
            ok += 1

    print("─" * 60)
    print(f"Done: {ok}/{len(queries)} plans returned successfully.")
    return 0 if ok == len(queries) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
