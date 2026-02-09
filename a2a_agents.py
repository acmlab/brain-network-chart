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
# from typing import Optional
# from pydantic_ai import Agent
# import uvicorn
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi import FastAPI

from typing import Optional, Dict, Any
from pydantic_ai import Agent
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request

# app = FastAPI()

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# Ollama Configuration
# OLLAMA_HOST = "yukon.acm.unc.edu:11434"
OLLAMA_HOST = "localhost:11434"
# MODEL_NAME = "MedAIBase/MedGemma1.5:4b"
MODEL_NAME = "Huzderu/txgemma-27B-chat-Q8_0_GGUF:latest"
OLLAMA_BASE_URL = f"http://{OLLAMA_HOST}/v1"
a2a_host = 'localhost'
# Set environment variable for Ollama
os.environ["OLLAMA_BASE_URL"] = OLLAMA_BASE_URL


# ============================================================================
# Define Agents
# ============================================================================

def create_planner_agent() -> Agent:
    """Agent 1: Parse query and create task plan"""
    return Agent(
        f"ollama:{MODEL_NAME}",
        name="planner",
        instructions="""You are a planning agent. Analyze the user's query and create a brief 
execution plan with 3 tasks: executor, researcher, and validator.
Keep response concise with task descriptions only."""
    )


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

# def create_planner_app():
#     """Create planner A2A server"""
#     agent = create_planner_agent()
#     return agent.to_a2a()

def create_planner_app():
    """Create planner REST API server"""
    agent = create_planner_agent()  # ✅ 使用 pydantic-ai
    app = FastAPI()
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.post("/api/planner/chat")
    async def planner_chat_endpoint(request: Request):
        try:
            body = await request.json()
            query = body.get("query", "")
            print(f"[DEBUG] Received query: {query}")
            
            if not query:
                return {"response": "Error: No query provided"}
            
            print(f"[DEBUG] Calling pydantic-ai agent...")
            result = await agent.run(query)
            
            # ✅ 使用 result.output
            reply = str(result.output)
            print(f"[DEBUG] Got response: {reply[:100]}...")
            
            return {"response": reply, "message": reply}
                
        except Exception as e:
            print(f"[ERROR] Exception: {e}")
            import traceback
            traceback.print_exc()
            return {"response": f"Error: {str(e)}"}
    
    @app.get("/api/tasks")
    async def get_tasks():
        return {"tasks": []}
    
    return app



# def create_executor_app():
#     """Create executor A2A server"""
#     agent = create_executor_agent()
#     return agent.to_a2a()

def create_executor_app():
    """Create executor REST API server"""
    agent = create_executor_agent()  # ✅ 使用 pydantic-ai
    app = FastAPI()
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.post("/api/chat")
    async def executor_chat_endpoint(request: Request):
        try:
            body = await request.json()
            messages = body.get("messages", [])
            user_message = ""
            if messages:
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        user_message = msg.get("content", "")
                        break
            if not user_message:
                return {"response": "Error: No user message found"}
            
            result = await agent.run(user_message)
            
            # ✅ 使用 result.output
            return {"response": str(result.output), "action": None}
        except Exception as e:
            print(f"Error in /api/chat: {e}")
            import traceback
            traceback.print_exc()
            return {"response": f"Error: {str(e)}"}
    
    @app.get("/api/tasks")
    async def get_tasks():
        return {"tasks": []}
    
    return app



# def create_researcher_app():
#     """Create researcher A2A server"""
#     agent = create_researcher_agent()
#     return agent.to_a2a()

def create_researcher_app():
    """Create researcher REST API server"""
    agent = create_researcher_agent()  # ✅ 使用 pydantic-ai
    app = FastAPI()
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.post("/api/chat")
    async def chat_endpoint(request: Request):
        try:
            body = await request.json()
            messages = body.get("messages", [])
            user_message = ""
            if messages:
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        user_message = msg.get("content", "")
                        break
            
            if not user_message:
                return {"response": "Error: No user message found"}
            
            result = await agent.run(user_message)
            
            # ✅ 使用 result.output
            return {"response": str(result.output), "action": None}
                
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return {"response": f"Error: {str(e)}"}
    
    @app.get("/api/tasks")
    async def get_tasks():
        return {"tasks": []}
    
    return app

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

    # print(f"Starting {agent_name} agent on port {port}...")
    # print(f"  Model: {MODEL_NAME}")
    # print(f"  Host: {OLLAMA_HOST}")
    # print(f"  API Docs: http://{a2a_host}:{port}/docs")

    print(f"Starting {agent_name} agent on port {port}...")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Host: {OLLAMA_HOST}")
    print(f"  API Docs: http://{a2a_host}:{port}/docs")
    print(f"  REST API endpoints:")
    print(f"    - POST /api/chat (for executor, researcher, validator)")
    print(f"    - POST /api/planner/chat (for planner)")
    print(f"    - GET /api/tasks")

    uvicorn.run(app, host=f"{a2a_host}", port=port, log_level="info")
