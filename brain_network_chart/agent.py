import random, os

from google.adk.agents.llm_agent import Agent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.tools.example_tool import ExampleTool
from google.genai import types

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm

OLLAMA_API_BASE = os.environ.get("OLLAMA_API_BASE", "http://yukon.acm.unc.edu:11434")
HOST_MODEL = os.environ.get("HOST_MODEL", "ollama_chat/qwen3:latest")
os.environ.setdefault("OLLAMA_API_BASE", OLLAMA_API_BASE)

planner_agent = RemoteA2aAgent(
    name="planner_agent",
    description="Agent that plans tasks for queries.",
    agent_card=(
        f"http://localhost:8031/a2a/planner_agent{AGENT_CARD_WELL_KNOWN_PATH}"
    ),
)
executor_agent = RemoteA2aAgent(
    name="executor_agent",
    description="Agent that executes tools for queries.",
    agent_card=(
        f"http://localhost:8031/a2a/executor_agent{AGENT_CARD_WELL_KNOWN_PATH}"
    ),
)
TEST_CASES = [
    # Neurodegenerative diseases
    "Identify biomarkers for Parkinson's disease using neuroimaging data",
    "Find early detection biomarkers for Alzheimer's disease progression",
    "Analyze protein aggregation biomarkers in frontotemporal dementia",

    # Cardiovascular diseases
    "Identify cardiac biomarkers for heart failure prognosis",
    "Find circulating biomarkers for myocardial infarction prediction",
    "Analyze endothelial dysfunction biomarkers in atherosclerosis",

    # Cancer research
    "Find tumor suppressor gene biomarkers in lung cancer",
    "Identify immunotherapy response biomarkers in melanoma",
    "Analyze circulating tumor DNA biomarkers for early cancer detection",

    # Metabolic disorders
    "Find insulin resistance biomarkers in type 2 diabetes",
    "Identify lipid metabolic biomarkers in metabolic syndrome",
    "Analyze adipokine biomarkers in obesity-related inflammation",

    # Autoimmune diseases
    "Find autoantibody biomarkers in systemic lupus erythematosus",
    "Identify complement activation biomarkers in rheumatoid arthritis",
    "Analyze T-cell dysfunction biomarkers in immunodeficiency disorders",

    # Infection and inflammation
    "Identify inflammatory cytokine biomarkers in sepsis prognosis",
    "Find pathogenic biomarkers for COVID-19 severity prediction",
    "Analyze bacterial toxin biomarkers in Clostridium difficile infection",

    # Organ dysfunction
    "Identify liver injury biomarkers in hepatic encephalopathy",
    "Find renal dysfunction biomarkers in chronic kidney disease progression",
    ]
example_tool = ExampleTool([
    {
        "input": {
            "role": "user",
            "parts": [{"text": case}],
        },
        "output": [
            {"role": "model", "parts": [{"text": "Dummy output."}]}
        ],
    } for case in TEST_CASES
])

analysis_pipeline_agent = SequentialAgent(
    name="analysis_pipeline_agent",
    sub_agents=[planner_agent, executor_agent],
)
root_agent = LlmAgent(
    model=LiteLlm(model=HOST_MODEL),
    name="root_agent",
        instruction="""
            You are the root coordinator for brain network analysis requests. Your responsibilities:
            1) Receive a user's neuroscience or brain-network analysis query.
            2) Forward the query to the remote Planner A2A agent (`planner_agent`) and request a structured ExecutionPlan JSON.
            3) Interpret the Planner's ExecutionPlan and orchestrate follow-up actions (invoke executor MCP tools, call researcher for literature/statistics, and run validator when tasks complete).
            4) Ensure Executor calls include `data_path` references (e.g. "uploaded_bold" or "uploaded_fc") when the user refers to uploaded data.
            5) Maintain a clear, human-readable summary for the user and return results only after validation.

            Always ask clarifying questions if the user's request or uploaded data are ambiguous. Do not attempt to execute MCP tools directly without an explicit ExecutionPlan from the Planner.
        """,
        global_instruction=(
                "You are BrainNetworkCoordinator: consult the Planner for execution plans, then orchestrate execution and validation."
        ),
    sub_agents=[analysis_pipeline_agent],
    tools=[example_tool],
    generate_content_config=types.GenerateContentConfig(
        safety_settings=[
            types.SafetySetting(  # avoid false alarm about rolling dice.
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.OFF,
            ),
        ]
    ),
)
