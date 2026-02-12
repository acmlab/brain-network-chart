"""
executor_agent.py  –  v3.2.0
Orchestrates neuroimaging analysis and medical research.

Architecture – Two-Track MCP Communication
───────────────────────────────────────────
The backend is TWO servers sharing the same port (8010):

  Track A – Plain REST  (mcp_server.py custom_route endpoints)
  ─────────────────────────────────────────────────────────────
  Used for: run_cfc_wavelet_analysis, run_hub_detection,
            run_normative_analysis, get_growth_curve,
            internet_search, search_pubmed, openalex_search,
            crossref_enrich, openneuro_search,
            upload, list_files, delete_file

  These are registered with @server.custom_route() and are
  reachable as plain POST/GET/DELETE calls:
      POST http://localhost:8010/internet_search
      POST http://localhost:8010/run_cfc_wavelet_analysis
      ... etc.

  Track B – MCP ADK Streamable-HTTP / JSON-RPC 2.0
  ─────────────────────────────────────────────────
  Used for: run_correlation, run_group_comparison,
            apply_fdr_correction, detect_outliers,
            check_data_normality

  These are registered with @server.tool() only — they have
  NO REST routes.  They are only reachable through the MCP
  wire protocol at POST http://localhost:8010/mcp.

  The MCP Streamable-HTTP transport uses session IDs even with
  stateless=True.  The correct sequence is:
    1. POST /mcp  with method="initialize"  → server returns
       a Mcp-Session-Id response header.
    2. POST /mcp  with the same Mcp-Session-Id header and
       method="tools/call".

  _call_mcp_stats_tool() implements this full handshake,
  acquiring a fresh session per call (stateless mode means the
  server does not store state between requests, but still
  requires the header to be present for routing).

Root cause of the v3.0.0 "Missing session ID" 400 error
─────────────────────────────────────────────────────────
v3.0.0 sent ALL tool calls (including REST-only endpoints like
/internet_search) through the JSON-RPC path without first
running the initialize handshake.  The fix has two parts:
  1. Route Track A tools back to plain REST.
  2. Add the initialize → call_tool two-step for Track B tools.

Changelog from v3.1.0
──────────────────────
• Fixed LLM 405 error: LLM_URL is validated at startup and the
  /api/generate path is appended automatically if missing.
  A 405 or ConnectError now emits a clear actionable message
  naming the exact URL that failed.
• Added LLM_CLINICAL_MODEL env var to override MedGemma at runtime.
• Fixed hardcoded LLM prompt: now queries against the actual user
  query instead of always summarising "BOLD connectivity".
• Added relevance filtering on internet_search results: off-topic
  papers with zero query-word overlap are dropped before LLM
  analysis. Raw count is preserved in metadata.raw_source_count.
"""

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from contextlib import asynccontextmanager
import httpx
import uvicorn
import pandas as pd
from typing import Optional, Dict, Any, List
import logging
import json
import os
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

MCP_URL         = os.getenv("MCP_URL",           "http://localhost:8010")

# LLM configuration
# ─────────────────────────────────────────────────────────────────────────────
# LLM_URL must point to an Ollama-compatible /api/generate endpoint.
# The 405 "Method Not Allowed" seen in v3.1.0 testing was caused by the
# LLM_URL env var being set to a non-Ollama placeholder (http://localhost:12345).
# Ensure the env var is either unset (falls back to 11434) or points to a
# live Ollama instance.  The /api/generate path is appended automatically if
# the URL does not already contain it, so you can set LLM_URL to either:
#   http://localhost:11434            ← base URL (path appended here)
#   http://localhost:11434/api/generate  ← full URL (used as-is)
_llm_base = os.getenv("LLM_URL", "http://localhost:11434/api/generate").rstrip("/")
LLM_URL = _llm_base if "/api/" in _llm_base else f"{_llm_base}/api/generate"

# Optional: override the default clinical analysis model via env var
# e.g. LLM_CLINICAL_MODEL=gemma3:12b
LLM_CLINICAL_MODEL_OVERRIDE = os.getenv("LLM_CLINICAL_MODEL", "")

EXECUTOR_PORT   = int(os.getenv("EXECUTOR_PORT",  "8012"))
RESEARCHER_PORT = int(os.getenv("RESEARCHER_PORT","8013"))
VALIDATOR_PORT  = int(os.getenv("VALIDATOR_PORT", "8014"))
PLANNER_PORT    = int(os.getenv("PLANNER_PORT",   "8011"))

# Track A: plain REST base URL  (@server.custom_route tools)
MCP_REST_BASE    = MCP_URL

# Track B: MCP Streamable-HTTP JSON-RPC endpoint  (@server.tool stats tools)
MCP_RPC_ENDPOINT = f"{MCP_URL}/mcp"

# MCP protocol version sent in the initialize handshake
MCP_PROTOCOL_VERSION = "2024-11-05"

UPLOAD_DIR = Path("/tmp/executor_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# MODEL SELECTION
# ──────────────────────────────────────────────────────────────────────────────

def select_model(task: str) -> str:
    """
    Intelligent model selection per Kaggle HAI-DEF requirements.
    Model zoo: https://developers.google.com/health-ai-developer-foundations

    The LLM_CLINICAL_MODEL env var overrides the clinical_analysis and
    research models at runtime — useful for swapping in a locally-pulled
    model (e.g. LLM_CLINICAL_MODEL=gemma3:12b) without editing this file.
    """
    model_map = {
        "planning":          "qwen3:latest",
        "clinical_analysis": "MedAIBase/MedGemma1.5:4b",
        "validation":        "Huzderu/txgemma-27B-chat-Q8_0_GGUF:latest",
        "research":          "MedAIBase/MedGemma1.5:4b",
    }
    # Apply runtime override for medical domain models
    if LLM_CLINICAL_MODEL_OVERRIDE and task in ("clinical_analysis", "research"):
        model_map["clinical_analysis"] = LLM_CLINICAL_MODEL_OVERRIDE
        model_map["research"]          = LLM_CLINICAL_MODEL_OVERRIDE

    selected = model_map.get(task, "MedAIBase/MedGemma1.5:4b")
    logger.info(f"Model selected for '{task}': {selected}")
    return selected

# ──────────────────────────────────────────────────────────────────────────────
# A2A PROTOCOL MODELS  (preserved — Planner / Validator compatibility)
# ──────────────────────────────────────────────────────────────────────────────

class AgentCard(BaseModel):
    """A2A Agent Card — Identifies agent capabilities"""
    name:        str = "Executor Agent"
    description: str = "Orchestrates neuroimaging tools and medical literature research"
    version:     str = "3.2.0"
    agent_id:    str = "executor_agent"
    port:        int = EXECUTOR_PORT
    capabilities: List[str] = [
        "Broad scholarly search (OpenAlex + Crossref via internet_search)",
        "PubMed literature search",
        "Neuroimaging trait analysis (CFC, Hub, Normative)",
        "MCP REST tool coordination (Track A — custom_route endpoints)",
        "MCP ADK JSON-RPC tool coordination (Track B — @server.tool stats tools)",
        "Group comparison (t-test / Mann-Whitney)",
        "FDR correction (Benjamini-Hochberg)",
        "Outlier detection & normality testing",
        "File upload / download / management",
        "Markdown table generation",
        "Multi-model LLM orchestration (MedGemma, TxGemma, Qwen3)",
        "Inter-agent communication (A2A)",
    ]
    tasks: List[Dict[str, Any]] = [
        {
            "task_id": "execute_research",
            "description": "Execute medical literature research via OpenAlex/Crossref/PubMed",
            "input_schema":  {"query": "string (research query)"},
            "output_schema": {
                "analysis_result":  "string",
                "tabular_evidence": "markdown_table",
                "metadata":         "object",
                "validation":       "object",
            },
        },
        {
            "task_id": "analyze_traits",
            "description": "Analyze neuroimaging traits (CFC, Hub, Normative)",
            "input_schema":  {
                "analysis_type": "string (cfc|hub|chart|normative)",
                "file_name":     "string",
            },
            "output_schema": {
                "trait_table":         "markdown_table",
                "analysis_type":       "string",
                "statistical_summary": "object",
            },
        },
        {
            "task_id": "run_group_comparison",
            "description": "Compare two groups using t-test or Mann-Whitney U",
            "input_schema": {
                "data_source": "string (CSV path or JSON string)",
                "group_col":   "string",
                "metric_col":  "string",
                "group_a":     "string",
                "group_b":     "string",
                "method":      "string (ttest|mannwhitney, optional)",
            },
            "output_schema": {"comparison_result": "object"},
        },
        {
            "task_id": "apply_fdr_correction",
            "description": "Apply Benjamini-Hochberg FDR correction to p-values",
            "input_schema":  {"p_values": "array[number]"},
            "output_schema": {"corrected_p_values": "array[number]", "rejected": "array[bool]"},
        },
        {
            "task_id": "upload_file",
            "description": "Upload neuroimaging file for analysis",
            "input_schema":  {"file": "binary (nifti/csv/tsv)"},
            "output_schema": {
                "file_name":   "string",
                "file_size":   "integer",
                "upload_path": "string",
            },
        },
        {
            "task_id": "list_files",
            "description": "List uploaded files available for analysis",
            "input_schema":  {},
            "output_schema": {"files": "array[object]"},
        },
    ]
    connected_agents: Dict[str, int] = {
        "planner":    PLANNER_PORT,
        "researcher": RESEARCHER_PORT,
        "validator":  VALIDATOR_PORT,
    }
    mcp_server:       str = MCP_URL
    mcp_rest_base:    str = MCP_REST_BASE
    mcp_rpc_endpoint: str = MCP_RPC_ENDPOINT
    models: List[str] = [
        "qwen3:latest",
        "MedAIBase/MedGemma1.5:4b",
        "Huzderu/txgemma-27B-chat-Q8_0_GGUF:latest",
    ]


class A2AMessage(BaseModel):
    """A2A JSON-RPC 2.0 Message Format"""
    jsonrpc: str            = "2.0"
    method:  str            = Field(..., description="Task method to invoke")
    params:  Dict[str, Any] = Field(default_factory=dict)
    id:      Optional[str]  = None


class A2AResponse(BaseModel):
    """A2A JSON-RPC 2.0 Response Format"""
    jsonrpc: str                      = "2.0"
    result:  Optional[Dict[str, Any]] = None
    error:   Optional[Dict[str, Any]] = None
    id:      Optional[str]            = None

# ──────────────────────────────────────────────────────────────────────────────
# PYDANTIC REQUEST / RESPONSE MODELS
# ──────────────────────────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    """Request schema for research execution via internet_search"""
    query: str = Field(..., min_length=3, max_length=500)

    @validator("query")
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace")
        return v.strip()


class TraitAnalysisRequest(BaseModel):
    """Request schema for neuroimaging trait analysis"""
    analysis_type: str = Field(..., description="cfc | hub | chart | normative")
    file_name:     str = Field(..., min_length=1)

    @validator("analysis_type")
    def validate_analysis_type(cls, v):
        valid = ["cfc", "hub", "chart", "normative"]
        if v.lower() not in valid:
            raise ValueError(f"analysis_type must be one of: {valid}")
        return v.lower()


class GroupComparisonRequest(BaseModel):
    """Request schema for group comparison analysis"""
    data_source: str = Field(..., description="CSV path or JSON-encoded data string")
    group_col:   str
    metric_col:  str
    group_a:     str
    group_b:     str
    method:      str = Field(default="ttest")

    @validator("method")
    def validate_method(cls, v):
        if v not in ("ttest", "mannwhitney"):
            raise ValueError("method must be 'ttest' or 'mannwhitney'")
        return v


class FDRCorrectionRequest(BaseModel):
    """Request schema for FDR correction"""
    p_values: List[float] = Field(..., description="List of raw p-values")

    @validator("p_values")
    def validate_p_values(cls, v):
        if not v:
            raise ValueError("p_values must be a non-empty list")
        if any(p < 0 or p > 1 for p in v):
            raise ValueError("All p-values must be in [0, 1]")
        return v


class ErrorResponse(BaseModel):
    """Standardised error response for downstream agents"""
    error_type:       str = Field(...)
    error_message:    str = Field(...)
    failed_component: str = Field(...)
    agent_id:         str = "executor_agent"
    port:             int = EXECUTOR_PORT


class SuccessResponse(BaseModel):
    """Standardised success response"""
    status:   str = "success"
    agent_id: str = "executor_agent"
    port:     int = EXECUTOR_PORT

# ──────────────────────────────────────────────────────────────────────────────
# A2A CLIENT  (unchanged from v2.1.0)
# ──────────────────────────────────────────────────────────────────────────────

class A2AClient:
    """Lightweight A2A client for calling other agents"""

    def __init__(self, agent_url: str, agent_name: str):
        self.agent_url       = agent_url
        self.agent_name      = agent_name
        self.request_counter = 0

    async def call_task(
        self, method: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        client = HTTPClientManager.client
        if not client:
            raise RuntimeError("HTTP client not initialised")

        self.request_counter += 1
        request_id = (
            f"{self.agent_name}_{self.request_counter}_{datetime.now().timestamp()}"
        )
        message = A2AMessage(method=method, params=params, id=request_id)

        try:
            logger.info(f"A2A Call → {self.agent_name}: {method}")
            response = await client.post(
                f"{self.agent_url}/a2a/invoke",
                json=message.dict(),
                timeout=60.0,
            )
            response.raise_for_status()
            a2a_response = A2AResponse(**response.json())
            if a2a_response.error:
                logger.error(f"A2A Error from {self.agent_name}: {a2a_response.error}")
                raise RuntimeError(
                    f"{self.agent_name} error: {a2a_response.error['message']}"
                )
            return a2a_response.result
        except httpx.HTTPError as e:
            logger.error(f"A2A connection failed to {self.agent_name}: {e}")
            raise RuntimeError(f"Failed to communicate with {self.agent_name}: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# HTTP CLIENT MANAGER
# ──────────────────────────────────────────────────────────────────────────────

class HTTPClientManager:
    """Manages a single httpx.AsyncClient across the app lifecycle"""
    client:            Optional[httpx.AsyncClient] = None
    researcher_client: Optional[A2AClient]         = None
    validator_client:  Optional[A2AClient]         = None

    @classmethod
    async def start(cls):
        cls.client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=30.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        )
        cls.researcher_client = A2AClient(
            f"http://localhost:{RESEARCHER_PORT}", "researcher_agent"
        )
        cls.validator_client = A2AClient(
            f"http://localhost:{VALIDATOR_PORT}", "validator_agent"
        )
        logger.info("HTTP client and A2A clients initialised")
        logger.info(f"MCP REST base    : {MCP_REST_BASE}")
        logger.info(f"MCP RPC endpoint : {MCP_RPC_ENDPOINT}")
        logger.info(f"LLM server       : {LLM_URL}")

    @classmethod
    async def stop(cls):
        if cls.client:
            await cls.client.aclose()
            logger.info("HTTP client closed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await HTTPClientManager.start()
    logger.info(f"Executor Agent started on port {EXECUTOR_PORT}")
    logger.info("A2A Server Mode: Enabled")
    logger.info(f"Upload directory : {UPLOAD_DIR}")
    yield
    await HTTPClientManager.stop()
    logger.info("Executor Agent shutdown complete")

# ──────────────────────────────────────────────────────────────────────────────
# FASTAPI APPLICATION
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Executor Agent – UNC ACM Lab (A2A / Two-Track MCP)",
    description=(
        "A2A-compliant agent orchestrating neuroimaging tools and medical "
        "literature research via REST (Track A) and MCP ADK JSON-RPC (Track B)."
    ),
    version="3.2.0",
    lifespan=lifespan,
)

# ──────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def safe_dataframe_to_markdown(
    data: Any, default_message: str = "No data available"
) -> str:
    """Convert various data shapes to a Markdown table safely."""
    try:
        if not data or (isinstance(data, (list, dict)) and len(data) == 0):
            return default_message
        if isinstance(data, dict):
            df = pd.DataFrame([data])
        elif isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, pd.DataFrame):
            df = data
        else:
            return default_message
        if df.empty:
            return default_message
        return df.to_markdown(index=False)
    except Exception as e:
        logger.error(f"Markdown conversion error: {e}")
        return f"{default_message} (Parse error: {e})"


def create_error_response(
    error_type: str, message: str, component: str
) -> ErrorResponse:
    """Factory for consistent error responses."""
    return ErrorResponse(
        error_type=error_type, error_message=message, failed_component=component
    )

# ──────────────────────────────────────────────────────────────────────────────
# TRACK A — PLAIN REST HELPER
# ──────────────────────────────────────────────────────────────────────────────

async def _call_rest_endpoint(
    path: str,
    payload: Dict[str, Any],
    timeout: float = 60.0,
) -> Any:
    """
    POST a JSON payload to a plain REST endpoint on the MCP server (Track A).

    Covers all @server.custom_route() tools:
        /internet_search, /run_cfc_wavelet_analysis, /run_hub_detection,
        /run_normative_analysis, /get_growth_curve, /search_pubmed,
        /openalex_search, /crossref_enrich, /openneuro_search

    Args:
        path:    URL path relative to MCP_REST_BASE, e.g. "/internet_search"
        payload: JSON-serialisable request body
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON response body (dict or list)

    Raises:
        RuntimeError on connection failure or non-2xx response
    """
    client = HTTPClientManager.client
    if not client:
        raise RuntimeError("HTTP client not initialised")

    url = f"{MCP_REST_BASE}{path}"
    logger.info(f"REST POST → {url}  keys={list(payload.keys())}")

    try:
        response = await client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()
    except httpx.ConnectError as e:
        logger.error(f"MCP REST server unreachable ({url}): {e}")
        raise RuntimeError(f"MCP REST server unreachable at {url}: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(
            f"MCP REST error at {path}: "
            f"{e.response.status_code} – {e.response.text[:300]}"
        )
        raise RuntimeError(
            f"MCP REST {path} HTTP {e.response.status_code}: {e.response.text[:300]}"
        )

    try:
        result = response.json()
    except Exception as e:
        raise RuntimeError(f"MCP REST {path} returned non-JSON response: {e}")

    logger.info(f"REST POST ← {path}  OK")
    return result

# ──────────────────────────────────────────────────────────────────────────────
# TRACK B — MCP ADK JSON-RPC HELPER  (stats tools only)
# ──────────────────────────────────────────────────────────────────────────────

async def _call_mcp_stats_tool(
    tool_name: str,
    arguments: Dict[str, Any],
) -> Any:
    """
    Call an MCP @server.tool() stats tool via the Streamable-HTTP
    JSON-RPC 2.0 two-step handshake (Track B).

    Why two steps are required
    ──────────────────────────
    The MCP Streamable-HTTP transport assigns a Mcp-Session-Id on every
    POST to /mcp whose method is "initialize".  Every subsequent request
    within that session must echo the same session ID as a request header
    — even when the server is configured with stateless=True (stateless
    means it does not persist state *between* sessions, but still requires
    the header for internal routing within a single request/response cycle).

    This is what caused the v3.0.0 "Bad Request: Missing session ID" 400:
    the old code sent call_tool directly without first initializing.

    Step 1 – initialize
      POST /mcp
      Body: { jsonrpc:"2.0", method:"initialize",
              params: { protocolVersion, capabilities:{}, clientInfo:{} } }
      → Response header: Mcp-Session-Id: <uuid>

    Step 2 – tools/call
      POST /mcp
      Header: Mcp-Session-Id: <uuid>
      Body: { jsonrpc:"2.0", method:"tools/call",
              params: { name:<tool>, arguments:{...} } }
      → Response body: { result:{ content:[{ type:"text", text:"<json>" }] } }

    Args:
        tool_name:  Registered @server.tool name
        arguments:  Dict matching the tool's parameter signature

    Returns:
        Parsed Python object from the tool's JSON return value

    Raises:
        RuntimeError on any failure with full context logged
    """
    client = HTTPClientManager.client
    if not client:
        raise RuntimeError("HTTP client not initialised")

    # ── Step 1: initialize ───────────────────────────────────────────────────
    init_id = f"init_{tool_name}_{datetime.now().timestamp()}"
    init_body = {
        "jsonrpc": "2.0",
        "id":      init_id,
        "method":  "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities":    {},
            "clientInfo": {
                "name":    "executor_agent",
                "version": "3.2.0",
            },
        },
    }

    logger.info(f"MCP init → {tool_name}")
    try:
        init_response = await client.post(
            MCP_RPC_ENDPOINT,
            json=init_body,
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )
        init_response.raise_for_status()
    except httpx.ConnectError as e:
        raise RuntimeError(f"MCP ADK server unreachable ({MCP_RPC_ENDPOINT}): {e}")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"MCP initialize HTTP {e.response.status_code}: {e.response.text[:300]}"
        )

    # Extract the session ID — try response header first, then JSON body
    session_id = (
        init_response.headers.get("mcp-session-id") or
        init_response.headers.get("Mcp-Session-Id")
    )
    if not session_id:
        try:
            init_data  = init_response.json()
            session_id = (
                init_data.get("result", {}).get("sessionId") or
                init_data.get("sessionId")
            )
        except Exception:
            pass

    if not session_id:
        raise RuntimeError(
            "MCP initialize succeeded but no Mcp-Session-Id was returned. "
            "Check that the ADK server version supports Streamable-HTTP sessions."
        )

    logger.info(f"MCP session acquired: {session_id[:12]}… for tool '{tool_name}'")

    # ── Step 2: tools/call ───────────────────────────────────────────────────
    call_id   = f"call_{tool_name}_{datetime.now().timestamp()}"
    call_body = {
        "jsonrpc": "2.0",
        "id":      call_id,
        "method":  "tools/call",
        "params": {
            "name":      tool_name,
            "arguments": arguments,
        },
    }

    logger.info(f"MCP tools/call → {tool_name}  args={list(arguments.keys())}")
    try:
        call_response = await client.post(
            MCP_RPC_ENDPOINT,
            json=call_body,
            headers={
                "Content-Type":   "application/json",
                "Mcp-Session-Id": session_id,
            },
            timeout=60.0,
        )
        call_response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"MCP tools/call '{tool_name}' HTTP {e.response.status_code}: "
            f"{e.response.text[:300]}"
        )

    try:
        rpc_response = call_response.json()
    except Exception as e:
        raise RuntimeError(
            f"MCP tools/call '{tool_name}' returned non-JSON: {e}"
        )

    # Propagate JSON-RPC level errors
    if rpc_response.get("error"):
        err = rpc_response["error"]
        raise RuntimeError(
            f"MCP tool '{tool_name}' JSON-RPC error "
            f"{err.get('code')}: {err.get('message')}"
        )

    # Decode TextContent block → JSON → Python object
    try:
        content_blocks = rpc_response["result"]["content"]
        raw_text       = content_blocks[0]["text"]
        result         = json.loads(raw_text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise RuntimeError(
            f"Cannot parse MCP tool '{tool_name}' response: {e} | "
            f"raw={str(rpc_response)[:200]}"
        )

    # Surface application-level errors embedded in the payload
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(
            f"MCP tool '{tool_name}' application error: {result['error']}"
        )

    logger.info(f"MCP tools/call ← {tool_name}  OK")
    return result

# ──────────────────────────────────────────────────────────────────────────────
# A2A PROTOCOL ENDPOINTS  (preserved)
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/agent-card")
async def get_agent_card():
    """A2A Protocol: Return agent card with capabilities."""
    return AgentCard().dict()


@app.post("/a2a/invoke")
async def a2a_invoke(request: Request):
    """
    A2A Protocol: JSON-RPC 2.0 task invocation endpoint.
    Entry point for Planner, Validator, and other A2A agents.
    """
    message = None
    try:
        body    = await request.json()
        message = A2AMessage(**body)
        logger.info(f"A2A Invoke: {message.method}  (ID: {message.id})")

        dispatch = {
            "execute_research":     _handle_execute_research,
            "analyze_traits":       _handle_analyze_traits,
            "list_files":           _handle_list_files,
            "run_group_comparison": _handle_group_comparison,
            "apply_fdr_correction": _handle_fdr_correction,
        }

        handler = dispatch.get(message.method)
        if handler is None:
            return A2AResponse(
                error={"code": -32601, "message": f"Method not found: {message.method}"},
                id=message.id,
            ).dict()

        result = await handler(message.params)
        return A2AResponse(result=result, id=message.id).dict()

    except Exception as e:
        logger.error(f"A2A invoke error: {e}")
        return A2AResponse(
            error={"code": -32603, "message": f"Internal error: {e}"},
            id=message.id if message else None,
        ).dict()

# ──────────────────────────────────────────────────────────────────────────────
# FILE LIFECYCLE ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a neuroimaging file.
    Saves locally then forwards to MCP via REST /upload (Track A).
    """
    try:
        allowed = [".nii", ".nii.gz", ".csv", ".tsv"]
        if not any(file.filename.endswith(ext) for ext in allowed):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(allowed)}",
            )

        file_path = UPLOAD_DIR / file.filename
        content   = await file.read()
        file_path.write_bytes(content)
        logger.info(f"Saved locally: {file.filename} ({len(content)} bytes)")

        # Forward to MCP via multipart REST (Track A — /upload is a custom_route)
        mcp_result: Dict = {}
        try:
            client = HTTPClientManager.client
            mcp_response = await client.post(
                f"{MCP_REST_BASE}/upload",
                files={"file": (file.filename, content)},
                timeout=30.0,
            )
            mcp_response.raise_for_status()
            mcp_result = mcp_response.json()
            logger.info(f"Forwarded to MCP REST /upload: {file.filename}")
        except Exception as e:
            logger.warning(f"MCP upload failed (non-critical): {e}")
            mcp_result = {"status": "local_only", "reason": str(e)}

        return {
            "status":      "success",
            "file_name":   file.filename,
            "file_size":   len(content),
            "upload_path": str(file_path),
            "mcp_result":  mcp_result,
            "agent_id":    "executor_agent",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete_file/{filename}")
async def delete_file(filename: str):
    """Delete file locally and from MCP REST /delete_file (Track A)."""
    try:
        file_path = UPLOAD_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")
        file_path.unlink()
        logger.info(f"Deleted locally: {filename}")

        try:
            client = HTTPClientManager.client
            await client.post(
                f"{MCP_REST_BASE}/delete_file",
                json={"filename": filename},
                timeout=10.0,
            )
        except Exception as e:
            logger.warning(f"MCP delete failed (non-critical): {e}")

        return {"status": "success", "deleted": filename, "agent_id": "executor_agent"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list_files")
async def list_files():
    """List all uploaded files (local + MCP REST /list_files, Track A)."""
    try:
        local_files = [
            {
                "filename": fp.name,
                "size":     fp.stat().st_size,
                "modified": datetime.fromtimestamp(fp.stat().st_mtime).isoformat(),
                "source":   "local",
            }
            for fp in UPLOAD_DIR.iterdir() if fp.is_file()
        ]

        mcp_files: List[Dict] = []
        try:
            client   = HTTPClientManager.client
            mcp_resp = await client.get(f"{MCP_REST_BASE}/list_files", timeout=10.0)
            mcp_resp.raise_for_status()
            mcp_files = mcp_resp.json().get("files", [])
            for f in mcp_files:
                f["source"] = "mcp"
        except Exception as e:
            logger.warning(f"MCP list_files failed (non-critical): {e}")

        combined = local_files + mcp_files
        return {
            "status":   "success",
            "files":    combined,
            "count":    len(combined),
            "agent_id": "executor_agent",
        }
    except Exception as e:
        logger.error(f"List files failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ──────────────────────────────────────────────────────────────────────────────
# INTERNAL TASK HANDLERS  (A2A router delegates here)
# ──────────────────────────────────────────────────────────────────────────────

async def _handle_execute_research(params: Dict[str, Any]) -> Dict[str, Any]:
    query = params.get("query")
    if not query:
        raise ValueError("Missing required parameter: query")
    return await _execute_research_logic(ResearchRequest(query=query))


async def _handle_analyze_traits(params: Dict[str, Any]) -> Dict[str, Any]:
    at = params.get("analysis_type")
    fn = params.get("file_name")
    if not at or not fn:
        raise ValueError("Missing required parameters: analysis_type, file_name")
    return await _analyze_traits_logic(
        TraitAnalysisRequest(analysis_type=at, file_name=fn)
    )


async def _handle_list_files(params: Dict[str, Any]) -> Dict[str, Any]:
    files = [
        {
            "filename": fp.name,
            "size":     fp.stat().st_size,
            "modified": datetime.fromtimestamp(fp.stat().st_mtime).isoformat(),
        }
        for fp in UPLOAD_DIR.iterdir() if fp.is_file()
    ]
    return {"status": "success", "files": files, "count": len(files)}


async def _handle_group_comparison(params: Dict[str, Any]) -> Dict[str, Any]:
    return await _group_comparison_logic(GroupComparisonRequest(**params))


async def _handle_fdr_correction(params: Dict[str, Any]) -> Dict[str, Any]:
    return await _fdr_correction_logic(FDRCorrectionRequest(**params))

# ──────────────────────────────────────────────────────────────────────────────
# CORE BUSINESS LOGIC
# ──────────────────────────────────────────────────────────────────────────────

async def _execute_research_logic(request: ResearchRequest) -> Dict[str, Any]:
    """
    Research pipeline:
      1. internet_search  → Track A  (POST /internet_search)
      2. MedGemma LLM analysis
      3. Researcher Agent → A2A (optional)
      4. Validator Agent  → A2A (optional)
    """
    try:
        # ── Step 1: Broad scholarly search (Track A) ─────────────────────────
        logger.info(f"internet_search query: {request.query}")
        search_result = await _call_rest_endpoint(
            "/internet_search",
            {"query": request.query, "max_results": 20},
            timeout=45.0,
        )

        if isinstance(search_result, dict):
            search_results = search_result.get("results", [])
        elif isinstance(search_result, list):
            search_results = search_result
        else:
            search_results = []

        model = select_model("clinical_analysis")

        if not search_results:
            logger.warning(f"No results for query: {request.query}")
            return {
                "status":   "partial_success",
                "agent_id": "executor_agent",
                "data_payload": {
                    "original_query":   request.query,
                    "analysis_result":  "No relevant scholarly articles were found.",
                    "tabular_evidence": "No scholarly results found.",
                    "tool_used":        "internet_search",
                },
                "metadata": {
                    "source_count": 0,
                    "model":        model,
                    "timestamp":    datetime.now().isoformat(),
                    "agent_version":"3.2.0",
                },
            }

        # ── Step 2: Filter and build evidence representations ────────────────
        # Discard results where the title has zero word overlap with the query.
        # This removes the clearly off-topic papers (e.g. ADAM10 synapse
        # function appearing in Alzheimer's BOLD queries) that slip through
        # the OpenAlex + Crossref pipeline when citation graphs are traversed.
        def _relevance_score(result: Dict[str, Any], query: str) -> int:
            query_words = set(query.lower().split())
            # Remove common stop words that would inflate false matches
            stop = {"the", "of", "in", "a", "an", "and", "or", "for", "to",
                    "with", "by", "on", "at", "from", "is", "are", "was"}
            query_words -= stop
            if not query_words:
                return 1  # Can't filter, keep everything
            title = (result.get("title") or "").lower()
            abstract = (result.get("abstract") or "").lower()
            searchable = f"{title} {abstract}"
            return sum(1 for w in query_words if w in searchable)

        # Keep top-N results by relevance, with a minimum score of 1 match
        scored = [
            (r, _relevance_score(r, request.query)) for r in search_results
        ]
        # Sort by score descending; anything with 0 matches is dropped
        relevant = [r for r, score in sorted(scored, key=lambda x: -x[1]) if score > 0]

        # Fall back to unfiltered if filtering removed everything
        if not relevant:
            logger.warning("Relevance filter removed all results — using unfiltered set")
            relevant = search_results

        logger.info(
            f"Relevance filter: {len(search_results)} raw → {len(relevant)} kept"
        )

        results_table = safe_dataframe_to_markdown(
            relevant[:10], "No structured results available"
        )
        results_summary = "\n".join(
            f"- {r.get('title', 'Unknown title')} "
            f"({r.get('year', r.get('publication_year', 'n.d.'))})"
            for r in relevant[:5]
        )

        # ── Step 3: Clinical analysis via MedGemma ───────────────────────────
        prompt = (
            f"<start_of_turn>user\n"
            f"You are a neuroscience research assistant. "
            f"Based on these papers:\n{results_summary}\n\n"
            f"Task: Briefly summarise the key findings relevant to "
            f'"{request.query}" in 2-3 sentences. '
            f"Focus on clinical and methodological insights.<end_of_turn>\n"
            f"<start_of_turn>model\n"
            f"Based on the research provided,"
        )

        client = HTTPClientManager.client
        logger.info(f"Calling LLM ({model}) at {LLM_URL} …")
        try:
            llm_res = await client.post(
                LLM_URL,
                json={
                    "model":  model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature":    0.1,
                        "repeat_penalty": 1.2,
                        "num_ctx":        4096,
                        "num_predict":    512,
                        "top_p":          0.9,
                    },
                },
                timeout=120.0,
            )
            llm_res.raise_for_status()
            llm_analysis = llm_res.json().get("response", "Analysis failed.")
        except httpx.HTTPStatusError as e:
            # 405 almost always means the URL path is wrong or not an Ollama endpoint.
            # Emit a clear actionable message rather than a raw exception dump.
            logger.warning(
                f"LLM returned {e.response.status_code} at {LLM_URL}. "
                f"Check that LLM_URL points to a live Ollama /api/generate endpoint. "
                f"Current value: LLM_URL={LLM_URL}"
            )
            llm_analysis = (
                f"[LLM unavailable — {e.response.status_code} at {LLM_URL}. "
                f"Set the LLM_URL env var to your Ollama server, "
                f"e.g. http://localhost:11434/api/generate]"
            )
        except httpx.ConnectError as e:
            logger.warning(f"LLM connection refused at {LLM_URL}: {e}")
            llm_analysis = (
                f"[LLM unavailable — connection refused at {LLM_URL}. "
                f"Is Ollama running? Start it with: ollama serve]"
            )
        except Exception as e:
            logger.warning(f"LLM call failed: {e}")
            llm_analysis = f"[LLM unavailable: {e}]"

        # ── Step 4: Researcher Agent (A2A, optional) ─────────────────────────
        try:
            researcher_result = await HTTPClientManager.researcher_client.call_task(
                method="research_query",
                params={
                    "original_query":     request.query,
                    "preliminary_results":results_summary,
                    "analysis":           llm_analysis,
                },
            )
            refined_keywords    = researcher_result.get("keywords",  [])
            researcher_analysis = researcher_result.get("analysis",  "")
        except Exception as e:
            logger.warning(f"Researcher communication failed (optional): {e}")
            refined_keywords    = []
            researcher_analysis = ""

        # ── Step 5: Assemble payload ─────────────────────────────────────────
        payload = {
            "status":   "success",
            "agent_id": "executor_agent",
            "data_payload": {
                "original_query":          request.query,
                "analysis_result":         llm_analysis,
                "tabular_evidence":        results_table,
                "refined_keywords":        refined_keywords,
                "researcher_contribution": researcher_analysis,
                "tool_used":               "internet_search",
            },
            "metadata": {
                "source_count":       len(relevant),
                "raw_source_count":   len(search_results),
                "model":         model,
                "timestamp":     datetime.now().isoformat(),
                "agent_version": "3.2.0",
            },
        }

        # ── Step 6: Validator Agent (A2A, optional) ──────────────────────────
        try:
            validation_result = await HTTPClientManager.validator_client.call_task(
                method="validate",
                params={
                    "original_query":   request.query,
                    "analysis_result":  llm_analysis,
                    "tabular_evidence": results_table,
                    "tool_used":        "internet_search",
                },
            )
            payload["validation"] = validation_result
        except Exception as e:
            logger.warning(f"Validator communication failed (optional): {e}")
            payload["validation"] = {"status": "skipped", "reason": str(e)}

        return payload

    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in _execute_research_logic: {e}")
        raise


async def _analyze_traits_logic(request: TraitAnalysisRequest) -> Dict[str, Any]:
    """
    Core trait analysis.
      Primary analysis  → Track A (plain REST)
      Statistical tools → Track B (MCP ADK JSON-RPC, @server.tool only)
    """
    rest_path_map = {
        "cfc":       "/run_cfc_wavelet_analysis",
        "hub":       "/run_hub_detection",
        "chart":     "/run_normative_analysis",
        "normative": "/run_normative_analysis",
    }
    normative_defaults = {
        "x_phenotype": "Global mean of FC",
        "age_col":     "age",
        "val_col":     "value",
    }

    try:
        rest_path = rest_path_map[request.analysis_type]
        logger.info(f"Trait analysis: {request.analysis_type} → {rest_path}")

        # ── Step 1: Primary analysis (Track A) ───────────────────────────────
        try:
            if request.analysis_type in ("chart", "normative"):
                api_payload = {"y_path": request.file_name, **normative_defaults}
            else:
                api_payload = {"data_path": request.file_name}

            data = await _call_rest_endpoint(rest_path, api_payload, timeout=90.0)

        except RuntimeError as e:
            if "unreachable" in str(e).lower():
                logger.warning("MCP REST unreachable — returning fallback response.")
                return {
                    "trait_table": (
                        "| Metric | Value |\n| :--- | :--- |\n"
                        "| Status | CONNECTION_FAILED |\n"
                        "| Component | MCP_REST_8010 |"
                    ),
                    "analysis_type": request.analysis_type,
                    "file_analyzed": request.file_name,
                    "status":        "fallback_mode",
                    "agent_id":      "executor_agent",
                }
            raise

        # ── Step 2: Render Markdown table ────────────────────────────────────
        trait_table = safe_dataframe_to_markdown(
            data, f"No trait data returned from {request.analysis_type} analysis"
        )

        # ── Step 3: Statistical validation (Track B) ─────────────────────────
        # Infer a representative numeric column from the result payload.
        inferred_column: Optional[str] = None
        try:
            sample = data[0] if isinstance(data, list) and data else data
            if isinstance(sample, dict):
                inferred_column = next(
                    (k for k, v in sample.items() if isinstance(v, (int, float))),
                    None,
                )
        except Exception:
            pass

        stats_summary: Dict[str, Any] = {}

        if inferred_column:
            # Pass the analysis result as an inline JSON string so the stats
            # tools can parse it without needing a physical file on disk.
            data_source_json = json.dumps(
                data if isinstance(data, list) else [data]
            )

            # detect_outliers  (Track B)
            try:
                outlier_result = await _call_mcp_stats_tool(
                    "detect_outliers",
                    {"data_source": data_source_json, "column": inferred_column},
                )
                stats_summary["outliers_detected"] = outlier_result.get("has_outliers", False)
                stats_summary["outlier_details"]   = outlier_result
            except Exception as e:
                logger.warning(f"detect_outliers failed (optional): {e}")
                stats_summary["outliers_detected"] = None
                stats_summary["outlier_error"]     = str(e)

            # check_data_normality  (Track B)
            try:
                normality_result = await _call_mcp_stats_tool(
                    "check_data_normality",
                    {"data_source": data_source_json, "column": inferred_column},
                )
                stats_summary["normality_test"]    = normality_result.get("is_normal", None)
                stats_summary["normality_details"] = normality_result

                # apply_fdr_correction on the Shapiro-Wilk p-value  (Track B)
                sw_pval = normality_result.get("p_value")
                if sw_pval is not None:
                    try:
                        fdr_result = await _call_mcp_stats_tool(
                            "apply_fdr_correction",
                            {"p_values": [float(sw_pval)]},
                        )
                        stats_summary["fdr_corrected_normality"] = fdr_result
                    except Exception as e:
                        logger.warning(f"apply_fdr_correction failed (optional): {e}")

            except Exception as e:
                logger.warning(f"check_data_normality failed (optional): {e}")
                stats_summary["normality_test"]  = None
                stats_summary["normality_error"] = str(e)

            stats_summary["statistical_tests_applied"] = [
                "detect_outliers", "check_data_normality", "apply_fdr_correction"
            ]
            stats_summary["column_analysed"] = inferred_column
        else:
            stats_summary = {
                "status": "skipped",
                "reason": "No numeric column detected in analysis output",
            }

        return {
            "trait_table":         trait_table,
            "analysis_type":       request.analysis_type,
            "file_analyzed":       request.file_name,
            "statistical_summary": stats_summary,
            "status":              "success",
            "agent_id":            "executor_agent",
            "timestamp":           datetime.now().isoformat(),
            "metadata": {
                "mcp_rest_path":  rest_path,
                "agent_version":  "3.2.0",
            },
        }

    except Exception as e:
        logger.error(f"Trait analysis error: {e}")
        raise


async def _group_comparison_logic(
    request: GroupComparisonRequest,
) -> Dict[str, Any]:
    """
    Group comparison via Track B  (run_group_comparison has no REST route).
    Automatically chains FDR correction on the resulting p-value.
    """
    try:
        logger.info(
            f"Group comparison: {request.group_a} vs {request.group_b} "
            f"on '{request.metric_col}' [{request.method}]"
        )
        comparison_result = await _call_mcp_stats_tool(
            "run_group_comparison",
            {
                "data_source": request.data_source,
                "group_col":   request.group_col,
                "metric_col":  request.metric_col,
                "group_a":     request.group_a,
                "group_b":     request.group_b,
                "method":      request.method,
            },
        )

        fdr_result: Optional[Dict] = None
        raw_pval = comparison_result.get("p_value")
        if raw_pval is not None:
            try:
                fdr_result = await _call_mcp_stats_tool(
                    "apply_fdr_correction",
                    {"p_values": [float(raw_pval)]},
                )
            except Exception as e:
                logger.warning(f"FDR correction after group comparison failed (optional): {e}")

        return {
            "status":            "success",
            "agent_id":          "executor_agent",
            "comparison_result": comparison_result,
            "fdr_correction":    fdr_result,
            "method":            request.method,
            "groups":  {"group_a": request.group_a, "group_b": request.group_b},
            "columns": {"group_col": request.group_col, "metric_col": request.metric_col},
            "timestamp":     datetime.now().isoformat(),
            "agent_version": "3.2.0",
        }
    except Exception as e:
        logger.error(f"Group comparison error: {e}")
        raise


async def _fdr_correction_logic(
    request: FDRCorrectionRequest,
) -> Dict[str, Any]:
    """Apply Benjamini-Hochberg FDR correction via Track B."""
    try:
        logger.info(f"FDR correction on {len(request.p_values)} p-values")
        fdr_result = await _call_mcp_stats_tool(
            "apply_fdr_correction",
            {"p_values": request.p_values},
        )
        return {
            "status":         "success",
            "agent_id":       "executor_agent",
            "fdr_result":     fdr_result,
            "input_p_values": request.p_values,
            "count":          len(request.p_values),
            "timestamp":      datetime.now().isoformat(),
            "agent_version":  "3.2.0",
        }
    except Exception as e:
        logger.error(f"FDR correction error: {e}")
        raise

# ──────────────────────────────────────────────────────────────────────────────
# REST ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Health check and agent identification."""
    return {
        "message":    "Executor Agent is Online (A2A / Two-Track MCP Mode)",
        "agent_id":   "executor_agent",
        "port":       EXECUTOR_PORT,
        "protocol":   "A2A JSON-RPC 2.0 | MCP REST (Track A) | MCP ADK JSON-RPC (Track B)",
        "models":     AgentCard().models,
        "capabilities": AgentCard().capabilities,
        "connected_agents": {
            "planner":    PLANNER_PORT,
            "researcher": RESEARCHER_PORT,
            "validator":  VALIDATOR_PORT,
        },
        "mcp_rest_base":    MCP_REST_BASE,
        "mcp_rpc_endpoint": MCP_RPC_ENDPOINT,
        "llm_server":       LLM_URL,
        "endpoints": {
            "a2a_card":         "/agent-card",
            "a2a_invoke":       "/a2a/invoke",
            "upload":           "/upload",
            "list_files":       "/list_files",
            "delete_file":      "/delete_file/{filename}",
            "legacy_research":  "/execute_research",
            "legacy_traits":    "/analyze_traits",
            "group_comparison": "/run_group_comparison",
            "fdr_correction":   "/apply_fdr_correction",
        },
    }


@app.get("/health")
async def health_check():
    """Detailed health check for monitoring."""
    return {
        "status":             "healthy",
        "http_client_active": HTTPClientManager.client is not None,
        "a2a_clients_ready": {
            "researcher": HTTPClientManager.researcher_client is not None,
            "validator":  HTTPClientManager.validator_client is not None,
        },
        "port":       EXECUTOR_PORT,
        "protocol":   "A2A + Two-Track MCP",
        "upload_dir": str(UPLOAD_DIR),
        "config": {
            "mcp_rest_base":    MCP_REST_BASE,
            "mcp_rpc_endpoint": MCP_RPC_ENDPOINT,
            "llm_url":          LLM_URL,
        },
    }


@app.post("/execute_research")
async def execute_research(request: ResearchRequest) -> Dict[str, Any]:
    """Legacy REST endpoint — routes through internet_search (Track A)."""
    try:
        return await _execute_research_logic(request)
    except Exception as e:
        logger.error(f"Research execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze_traits")
async def analyze_traits(request: TraitAnalysisRequest) -> Dict[str, Any]:
    """Legacy REST endpoint — primary analysis Track A, stats Track B."""
    try:
        return await _analyze_traits_logic(request)
    except Exception as e:
        logger.error(f"Trait analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/run_group_comparison")
async def run_group_comparison(request: GroupComparisonRequest) -> Dict[str, Any]:
    """Group comparison via Track B (t-test / Mann-Whitney + auto FDR)."""
    try:
        return await _group_comparison_logic(request)
    except Exception as e:
        logger.error(f"Group comparison failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/apply_fdr_correction")
async def apply_fdr_correction(request: FDRCorrectionRequest) -> Dict[str, Any]:
    """Benjamini-Hochberg FDR correction via Track B."""
    try:
        return await _fdr_correction_logic(request)
    except Exception as e:
        logger.error(f"FDR correction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ──────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=EXECUTOR_PORT, log_level="info")