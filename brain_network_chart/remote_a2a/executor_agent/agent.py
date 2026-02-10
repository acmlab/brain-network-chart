import os # Required for path operations

from google.adk.models.lite_llm import LiteLlm

import asyncio
import json
from typing import Any

from dotenv import load_dotenv
from google.adk.agents.llm_agent import LlmAgent
# from google.adk.artifacts.in_memory_artifact_service import (
#     InMemoryArtifactService,  # Optional
# )
# from google.adk.runners import Runner
# from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool.mcp_toolset import (
    McpToolset,
)
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPServerParams
# from google.genai import types
from rich import print
load_dotenv()

OLLAMA_API_BASE = os.environ.get("OLLAMA_API_BASE", "http://yukon.acm.unc.edu:11434")
HOST_MODEL = os.environ.get("HOST_MODEL", "ollama_chat/qwen3:latest")
os.environ.setdefault("OLLAMA_API_BASE", OLLAMA_API_BASE)


root_agent = LlmAgent(
    model=LiteLlm(model=HOST_MODEL),
    name="executor_agent",
    instruction="""Execute tools given planned tasks.
    """,
    tools=[
        McpToolset(
        connection_params=StreamableHTTPServerParams(
            url="http://localhost:8010/mcp",
        )
    )
    ],
)