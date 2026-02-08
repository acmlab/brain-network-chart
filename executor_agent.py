from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator
from contextlib import asynccontextmanager
import httpx
import uvicorn
import pandas as pd
from typing import Optional, Dict, Any, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CONFIGURATION

MODEL_NAME = "MedAIBase/MedGemma1.5:4b"
MCP_URL = "http://localhost:8010"  
LLM_URL = "http://localhost:12345/api/generate"
EXECUTOR_PORT = 8012
RESEARCHER_PORT = 8013
VALIDATOR_PORT = 8014

# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION

class ResearchRequest(BaseModel):
    """Request schema for research execution via PubMed"""
    query: str = Field(..., min_length=3, max_length=500, description="Research query for PubMed search")
    
    @validator('query')
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace")
        return v.strip()

class TraitAnalysisRequest(BaseModel):
    """Request schema for neuroimaging trait analysis"""
    analysis_type: str = Field(..., description="Analysis type: cfc, hub, chart, or normative")
    file_name: str = Field(..., min_length=1, description="Input file name for analysis")
    
    @validator('analysis_type')
    def validate_analysis_type(cls, v):
        valid_types = ["cfc", "hub", "chart", "normative"]
        if v.lower() not in valid_types:
            raise ValueError(f"Analysis type must be one of: {', '.join(valid_types)}")
        return v.lower()

class ErrorResponse(BaseModel):
    """Standardized error response for downstream agents"""
    error_type: str = Field(..., description="Error category for programmatic handling")
    error_message: str = Field(..., description="Human-readable error description")
    failed_component: str = Field(..., description="Which component failed (MCP, LLM, parsing, etc.)")
    agent_id: str = "executor_asthav"
    port: int = EXECUTOR_PORT
    
class SuccessResponse(BaseModel):
    """Standardized success response"""
    status: str = "success"
    agent_id: str = "executor_asthav"
    port: int = EXECUTOR_PORT

# SHARED HTTP CLIENT WITH LIFESPAN MANAGEMENT

class HTTPClientManager:
    """Manages a single httpx.AsyncClient instance across the application lifecycle"""
    client: Optional[httpx.AsyncClient] = None
    
    @classmethod
    async def start(cls):
        """Initialize the shared HTTP client"""
        cls.client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=30.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )
        logger.info("HTTP client initialized")
    
    @classmethod
    async def stop(cls):
        """Close the shared HTTP client"""
        if cls.client:
            await cls.client.aclose()
            logger.info("HTTP client closed")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan event handler for startup/shutdown"""
    # Startup
    await HTTPClientManager.start()
    logger.info(f"Executor Agent (Asthav) started on port {EXECUTOR_PORT}")
    yield
    # Shutdown
    await HTTPClientManager.stop()
    logger.info("Executor Agent shutdown complete")

# FASTAPI APPLICATION

app = FastAPI(
    title="Executor Agent - UNC ACM Lab",
    description="Orchestrates neuroimaging tools and medical literature research for multi-agent system",
    version="2.0.0",
    lifespan=lifespan
)

# UTILITY FUNCTIONS

def safe_dataframe_to_markdown(data: Any, default_message: str = "No data available") -> str:

    try:
        # Handle empty data
        if not data or (isinstance(data, (list, dict)) and len(data) == 0):
            return default_message
        
        # Convert to DataFrame
        if isinstance(data, dict):
            # Single dictionary -> single row
            df = pd.DataFrame([data])
        elif isinstance(data, list):
            # List of dictionaries
            df = pd.DataFrame(data)
        elif isinstance(data, pd.DataFrame):
            df = data
        else:
            logger.warning(f"Unexpected data type for table conversion: {type(data)}")
            return default_message
        
        # Handle empty DataFrame
        if df.empty:
            return default_message
        
        # Convert to markdown
        return df.to_markdown(index=False)
        
    except Exception as e:
        logger.error(f"Error converting data to markdown: {str(e)}")
        return f"{default_message} (Parse error: {str(e)})"

def create_error_response(
    error_type: str,
    message: str,
    component: str
) -> ErrorResponse:
    """Factory function for consistent error responses"""
    return ErrorResponse(
        error_type=error_type,
        error_message=message,
        failed_component=component
    )

# API ENDPOINTS

@app.get("/")
async def root():
    """Health check and agent identification endpoint"""
    return {
        "message": "Executor Agent is Online",
        "agent_id": "executor_asthav",
        "port": EXECUTOR_PORT,
        "role": "Executor Agent",
        "assigned_model": MODEL_NAME,
        "capabilities": [
            "PubMed literature search",
            "Neuroimaging trait analysis (CFC, Hub, Normative)",
            "Markdown table generation",
            "Multi-agent communication"
        ],
        "connected_agents": {
            "researcher": RESEARCHER_PORT,
            "validator": VALIDATOR_PORT
        },
        "mcp_server": MCP_URL
    }

@app.get("/health")
async def health_check():
    """Detailed health check for monitoring"""
    return {
        "status": "healthy",
        "http_client_active": HTTPClientManager.client is not None,
        "port": EXECUTOR_PORT
    }

@app.post("/execute_research")
async def execute_research(request: ResearchRequest) -> Dict[str, Any]:
    client = HTTPClientManager.client
    if not client:
        raise HTTPException(status_code=503, detail="HTTP client not initialized")
    
    try:
        # 1. Broad Scholarly Search via Xiyun's pipeline (OpenAlex -> Crossref)
        logger.info(f"Executing scholarly search: {request.query}")
        search_res = await client.post(
            f"{MCP_URL}/internet_search", # Combined pipeline on Yukon:8010
            json={"query": request.query},
            timeout=30.0
        )
        search_res.raise_for_status()
        search_results = search_res.json().get("results", [])
        
        # 2. Parse results for the Researcher Agent (Andy)
        results_table = safe_dataframe_to_markdown(
            search_results[:5], # Send top 5 most relevant for token efficiency
            "No scholarly results found."
        )
        
        # 3. Clinical Analysis via MedGemma (Asthav's core brain)
        prompt = (
            f"Analyze these scholarly findings for clinical relevance:\n\n"
            f"{results_table}\n\n"
            f"Query: {request.query}\n\n"
            f"Summarize the consensus on neuroimaging traits found here."
        )
        
        llm_res = await client.post(
            LLM_URL,
            json={"model": MODEL_NAME, "prompt": prompt, "stream": False}
        )
        llm_analysis = llm_res.json().get("response", "Analysis failed.")
        
        # 4. Standardized payload for Researcher/Validator
        return {
            "status": "success",
            "agent_id": "executor_asthav",
            "data_payload": {
                "original_query": request.query,
                "analysis_result": llm_analysis,
                "tabular_evidence": results_table,
                "tool_used": "internet_search_pipeline"
            },
            "metadata": {
                "source_count": len(search_results),
                "model": MODEL_NAME
            }
        }
        
    except Exception as e:
        logger.error(f"Execution failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze_traits")
async def analyze_traits(request: TraitAnalysisRequest) -> Dict[str, Any]:
    
    # Endpoint mapping for MCP server
    endpoints = {
        "cfc": "/run_cfc_wavelet_analysis",
        "hub": "/run_hub_detection",
        "chart": "/run_normative_analysis",
        "normative": "/run_normative_analysis"
    }
    
    client = HTTPClientManager.client
    if not client:
        raise HTTPException(
            status_code=503,
            detail=create_error_response(
                "SERVICE_UNAVAILABLE",
                "HTTP client not initialized",
                "http_client"
            ).dict()
        )
    
    try:
        endpoint = endpoints[request.analysis_type]
        logger.info(f"Running {request.analysis_type} analysis on {request.file_name}")
        
        try:
            # Step 1: Call MCP server tool
            response = await client.post(
                f"{MCP_URL}{endpoint}",
                json={"file": request.file_name},
                timeout=5.0  # Short timeout for testing
            )
            response.raise_for_status()
            data = response.json()
            
            # Step 2: Parse as Markdown table
            trait_table = safe_dataframe_to_markdown(
                data,
                f"No trait data returned from {request.analysis_type} analysis"
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.warning("MCP Connection failed. Returning dummy data for submission testing.")
            trait_table = "| Metric | Value |\n| :--- | :--- |\n| Status | CONNECTION_FAILED |\n| Component | MCP_8011 |"

        return {
            "trait_table": trait_table,
            "analysis_type": request.analysis_type,
            "file_analyzed": request.file_name,
            "status": "success" if "CONNECTION_FAILED" not in trait_table else "fallback_mode",
            "agent_id": "executor_asthav"
        }
        
    except httpx.HTTPStatusError as e:
        logger.error(f"MCP server error: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=create_error_response(
                "MCP_SERVICE_ERROR",
                f"MCP server returned {e.response.status_code}: {str(e)}",
                "mcp_server"
            ).dict()
        )
    except httpx.TimeoutException:
        logger.error("MCP request timeout")
        raise HTTPException(
            status_code=504,
            detail=create_error_response(
                "TIMEOUT",
                f"MCP server timeout for {request.analysis_type} analysis",
                "mcp_server"
            ).dict()
        )
    except Exception as e:
        logger.error(f"Unexpected error in analyze_traits: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                "INTERNAL_ERROR",
                str(e),
                "executor_agent"
            ).dict()
        )


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=EXECUTOR_PORT,
        log_level="info"
    )