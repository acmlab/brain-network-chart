from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.concurrency import run_in_threadpool
import sys
import io
import logging
import time
import os
import re
import requests
from urllib.parse import quote_plus
from requests.adapters import HTTPAdapter
from threading import Lock
from urllib3.util.retry import Retry
from typing import Optional, List, Dict, Any, Literal
from functools import wraps
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, Callable
from navigator_agent import ukb_navigate, UKBNavigatorConfig
from pydantic import BaseModel, Field, field_validator, ValidationInfo
from tools import (
    tool_cfc_wavelet,
    tool_hub_detection,
    tool_normative_analysis,
    AnalysisConfig,
    load_bolds_from_csv,
    load_curve_data,
    save_uploaded_file,
    list_uploaded_files,
    delete_uploaded_file,
    get_file_path,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('mcp_server.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW = 60  # seconds
client_requests: Dict[str, list] = {}

# Request/Response schemas
class CFCWaveletRequest(BaseModel):
    data_path: str = Field(default="data_example_BOLD.csv", description="Path to BOLD CSV file")
    window_size: int = Field(default=100, ge=10, le=1000, description="Sliding window size")
    step_size: int = Field(default=90, ge=1, le=500, description="Window step size")
    padding: bool = Field(default=True, description="Pad edges")
    ratio: float = Field(default=0.8, ge=0.0, le=1.0, description="Edge weight threshold ratio")
    wavelets_num: int = Field(default=10, ge=1, le=100, description="Number of wavelets")
    beta: float = Field(default=1.0, ge=0.0, description="Regularization parameter")
    gamma: float = Field(default=0.005, ge=0.0, description="Convergence threshold")
    max_iter: int = Field(default=100, ge=1, le=1000, description="Max iterations")
    node_select: int = Field(default=10, ge=1, description="Node selection parameter")
    
    @field_validator('step_size')
    @classmethod
    def validate_step_size(cls, v, info: ValidationInfo):
        if info.data.get('window_size') and v > info.data['window_size']:
            raise ValueError('step_size must be <= window_size')
        return v

class HubDetectionRequest(BaseModel):
    data_path: str = Field(default="data_example_BOLD.csv", description="Path to BOLD CSV file")
    window_size: int = Field(default=100, ge=10, le=1000, description="Sliding window size")
    step_size: int = Field(default=90, ge=1, le=500, description="Window step size")
    padding: bool = Field(default=True, description="Pad edges")
    ratio: float = Field(default=0.8, ge=0.0, le=1.0, description="Edge weight threshold")
    k: int = Field(default=2, ge=1, le=100, description="Embedding dimension")
    hub_num: int = Field(default=10, ge=1, description="Number of hubs")
    use_group: bool = Field(default=False, description="Use group method")

class NormativeAnalysisRequest(BaseModel):
    x_phenotype: str = Field(description="Phenotype name")
    y_path: str = Field(description="Path to Y data CSV")
    age_col: str = Field(description="Age column name")
    val_col: str = Field(description="Value column name")

class PubMedSearchRequest(BaseModel):
    query: str = Field(description="PubMed query string (supports PubMed syntax)")
    max_results: int = Field(20, ge=1, le=200, description="Maximum number of papers to return (1-200)")
    year_from: Optional[int] = Field(None, ge=1900, le=datetime.now().year, description="Filter Start year (inclusive)")
    year_to: Optional[int] = Field(None, ge=1900, le=datetime.now().year, description="Filter End year (inclusive)")

class OpenAlexSearchRequest(BaseModel):
    query: str = Field(..., description="Search query for OpenAlex works")
    max_results: int = Field(10, ge=1, le=50, description="Max results (1-50)")
    from_year: Optional[int] = Field(None, ge=1800, le=2100, description="Filter from publication year (inclusive)")
    to_year: Optional[int] = Field(None, ge=1800, le=2100, description="Filter to publication year (inclusive)")


class CrossrefEnrichRequest(BaseModel):
    dois: List[str] = Field(..., description="List of DOIs to enrich via Crossref (e.g., 10.1038/...)")
    max_items: int = Field(50, ge=1, le=200, description="Max DOIs to process (safety cap)")

class InternetSearchRequest(BaseModel):
    query: str = Field(..., description="Internet search query (OpenAlex + Crossref)")
    max_results: int = Field(10, ge=1, le=50, description="Max results (1-50)")
    from_year: Optional[int] = Field(None, ge=1800, le=2100, description="Filter from publication year (inclusive)")
    to_year: Optional[int] = Field(None, ge=1800, le=2100, description="Filter to publication year (inclusive)")

class UKBNavigatorRequest(BaseModel):
    extract: Literal["field_summary", "browse_list", "field_full"]
    field_id: Optional[int] = None
    browse_id: Optional[int] = None
    url: Optional[str] = None
    headless: bool = True
    timeout_s: float = 25.0
    max_wait_s: float = 10.0

class ResponseSchema(BaseModel):
    status: str
    timestamp: str
    message: str = ""
    data: dict = Field(default_factory=dict)
    console_output: str = ""
    progress: list = Field(default_factory=list)

@contextmanager
def capture_output():
    """Context manager to capture stdout."""
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield sys.stdout
    finally:
        sys.stdout = old_stdout


def rate_limit(f: Callable) -> Callable:
    """Decorator to enforce rate limiting per client."""
    @wraps(f)
    async def decorated_function(request: Request, *args, **kwargs):
        client_ip = request.client.host
        now = time.time()
        
        # Clean old requests
        if client_ip not in client_requests:
            client_requests[client_ip] = []
        
        client_requests[client_ip] = [
            req_time for req_time in client_requests[client_ip]
            if now - req_time < RATE_LIMIT_WINDOW
        ]
        
        # Check rate limit
        if len(client_requests[client_ip]) >= RATE_LIMIT_REQUESTS:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW}s"
            )
        
        client_requests[client_ip].append(now)
        return await f(request, *args, **kwargs)
    return decorated_function


def validate_parameters(**param_rules) -> Callable:
    """Decorator to validate function parameters."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            errors = []
            for param, rule in param_rules.items():
                if param in kwargs:
                    value = kwargs[param]
                    if 'min' in rule and value < rule['min']:
                        errors.append(f"{param} must be >= {rule['min']}, got {value}")
                    if 'max' in rule and value > rule['max']:
                        errors.append(f"{param} must be <= {rule['max']}, got {value}")
                    if 'type' in rule and not isinstance(value, rule['type']):
                        errors.append(f"{param} must be {rule['type'].__name__}, got {type(value).__name__}")
                    if 'file_exists' in rule and rule['file_exists']:
                        if not os.path.exists(value):
                            errors.append(f"File not found: {value}")
            
            if errors:
                logger.error(f"Parameter validation failed: {'; '.join(errors)}")
                raise ValueError(f"Parameter validation failed: {'; '.join(errors)}")
            
            return f(*args, **kwargs)
        return wrapper
    return decorator

PUBMED_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

_PUBMED_SESSION: Optional[requests.Session] = None


def _pubmed_session() -> requests.Session:
    """Create (once) a requests Session with retry/backoff for transient PubMed failures."""
    global _PUBMED_SESSION
    if _PUBMED_SESSION is not None:
        return _PUBMED_SESSION

    session = requests.Session()

    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=0.6,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # NCBI prefers a descriptive User-Agent.
    session.headers.update(
        {
            "User-Agent": "brain-network-chart/0.1 (contact: set PUBMED_EMAIL env var)",
        }
    )

    _PUBMED_SESSION = session
    return session


def _pubmed_base_params() -> Dict[str, str]:
    """Optional NCBI E-utilities parameters (api_key/email/tool) via env vars."""
    params: Dict[str, str] = {}

    api_key = (os.getenv("PUBMED_API_KEY") or "").strip()
    if api_key:
        params["api_key"] = api_key

    tool = (os.getenv("PUBMED_TOOL") or "brain-network-chart").strip()
    if tool:
        params["tool"] = tool

    email = (os.getenv("PUBMED_EMAIL") or "").strip()
    if email:
        params["email"] = email

    return params

def _extract_year(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(18|19|20)\d{2}", text)
    return int(m.group(0)) if m else None

def _pubmed_esearch(query: str, max_results: int) -> List[str]:
    url = f"{PUBMED_EUTILS_BASE}/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": str(max_results),
        "sort": "relevance",
        **_pubmed_base_params(),
    }
    r = _pubmed_session().get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("esearchresult", {}).get("idlist", []) or []

def _merge_pubmed_esummary_json(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {"result": {"uids": []}}
    merged_result = merged["result"]

    for part in parts:
        result_obj = (part or {}).get("result", {}) or {}
        uids = result_obj.get("uids", []) or []
        for uid in uids:
            if uid not in merged_result["uids"]:
                merged_result["uids"].append(uid)
            if uid in result_obj:
                merged_result[uid] = result_obj[uid]

    # Keep stable ordering
    try:
        merged_result["uids"] = [str(x) for x in merged_result["uids"]]
    except Exception:
        pass

    return merged


def _pubmed_esummary_call(pmids: List[str]) -> Dict[str, Any]:
    """Raw esummary call for a list of PMIDs (comma-separated)."""
    url = f"{PUBMED_EUTILS_BASE}/esummary.fcgi"
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        **_pubmed_base_params(),
    }
    r = _pubmed_session().get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _pubmed_esummary(pmids: List[str]) -> Dict[str, Any]:
    """Fetch PubMed summaries with batching + fallback splitting for transient 5xx."""
    if not pmids:
        return {"result": {"uids": []}}

    # Keep requests reasonably sized; NCBI is sometimes flaky for larger batches.
    batch_size_raw = (os.getenv("PUBMED_ESUMMARY_BATCH_SIZE") or "25").strip()
    try:
        batch_size = max(1, min(200, int(batch_size_raw)))
    except ValueError:
        batch_size = 25

    def fetch_resilient(ids: List[str]) -> Dict[str, Any]:
        try:
            return _pubmed_esummary_call(ids)
        except requests.RequestException:
            # If NCBI returns 5xx for a batch, split into smaller requests.
            if len(ids) <= 1:
                raise
            mid = len(ids) // 2
            left = fetch_resilient(ids[:mid])
            right = fetch_resilient(ids[mid:])
            return _merge_pubmed_esummary_json([left, right])

    parts: List[Dict[str, Any]] = []
    for i in range(0, len(pmids), batch_size):
        chunk = pmids[i : i + batch_size]
        parts.append(fetch_resilient(chunk))
        # Be polite to NCBI and reduce burstiness.
        time.sleep(0.12)

    if len(parts) == 1:
        return parts[0]
    return _merge_pubmed_esummary_json(parts)

OPENALEX_WORKS = "https://api.openalex.org/works"
CROSSREF_WORKS = "https://api.crossref.org/works"

CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "")
TOOL_NAME = os.getenv("TOOL_NAME", "brain-network-chart")

def _clean_doi(doi: str) -> str:
    doi = (doi or "").strip()
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]
    if doi.startswith("http://doi.org/"):
        doi = doi[len("http://doi.org/"):]
    return doi.lower()

def _openalex_get(params: dict) -> dict:
    # OpenAlex recommends including mailto for good citizenship
    p = dict(params)
    if CONTACT_EMAIL:
        p["mailto"] = CONTACT_EMAIL
    r = requests.get(OPENALEX_WORKS, params=p, timeout=20)
    r.raise_for_status()
    return r.json()

def _crossref_get_by_doi(doi: str) -> Optional[dict]:
    doi = _clean_doi(doi)
    if not doi:
        return None
    url = f"{CROSSREF_WORKS}/{quote_plus(doi)}"
    headers = {
        # Crossref asks for a descriptive UA with contact info when possible
        "User-Agent": f"{TOOL_NAME} (mailto:{CONTACT_EMAIL})" if CONTACT_EMAIL else TOOL_NAME
    }
    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("message")

def _get_server_host_port() -> tuple[str, int]:
    host = os.getenv("MCP_HOST", "0.0.0.0").strip() or "0.0.0.0"

    port_raw = os.getenv("MCP_PORT", os.getenv("PORT", "8010")).strip() or "8010"
    try:
        port = int(port_raw)
    except ValueError:
        raise ValueError(f"Invalid port: {port_raw!r} (set MCP_PORT or PORT)")

    if not (1 <= port <= 65535):
        raise ValueError(f"Invalid port: {port} (must be 1-65535)")

    return host, port


_SERVER_HOST, _SERVER_PORT = _get_server_host_port()

server = FastMCP(
    'Brain Network Analysis Server',
    host=_SERVER_HOST,
    port=_SERVER_PORT,
)


@server.tool(name="run_cfc_wavelet_analysis")
@validate_parameters(
    window_size={'min': 10, 'max': 1000, 'type': int},
    step_size={'min': 30, 'max': 500, 'type': int},
    ratio={'min': 0.0, 'max': 1.0, 'type': float},
    wavelets_num={'min': 1, 'max': 100, 'type': int},
    max_iter={'min': 1, 'max': 1000, 'type': int},
)
def run_cfc_wavelet_analysis(
    data_path: str = "data_example_BOLD.csv",
    window_size: int = 100,
    step_size: int = 90,
    padding: bool = True,
    ratio: float = 0.8,
    wavelets_num: int = 10,
    beta: float = 1.0,
    gamma: float = 0.005,
    max_iter: int = 100,
    node_select: int = 10,
) -> dict:
    """
    Run cross-frequency coupling (CFC) analysis using harmonic wavelets.
    
    Parameters:
    - data_path: Path to BOLD CSV file
    - window_size: Sliding window size (10-1000)
    - step_size: Window step size (30-500)
    - padding: Pad edges
    - ratio: Edge weight threshold ratio (0.0-1.0)
    - wavelets_num: Number of wavelets (1-100)
    - beta: Regularization parameter
    - gamma: Convergence threshold
    - max_iter: Maximum iterations (1-1000)
    - node_select: Node selection parameter
    
    Returns: Analysis results with console output and progress tracking
    """
    progress_log = []
    captured_output = []
    start_time = time.time()
    
    try:
        logger.info(f"CFC analysis started: window_size={window_size}, step_size={step_size}")
        
        # Resolve file path (checks uploaded_files first, then local directory)
        try:
            data_path = get_file_path(data_path)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Data file not found: {e}")
        
        # Validate parameters consistency
        if step_size > window_size:
            raise ValueError(f"step_size ({step_size}) must be <= window_size ({window_size})")
        
        config = AnalysisConfig()
        config.ratio = ratio
        config.wavelets_num = wavelets_num
        config.beta = beta
        config.gamma = gamma
        config.max_iter = max_iter
        config.node_select = node_select
        
        progress_log.append({"step": "loading", "message": f"Loading BOLD data from {data_path}"})
        with capture_output() as output:
            bolds = load_bolds_from_csv(data_path, window_size=window_size, step_size=step_size, padding=padding)
        captured_output.append(output.getvalue())
        num_windows = bolds.shape[0]
        progress_log.append({"step": "loaded", "message": f"Data loaded successfully: shape {list(bolds.shape)}"})
        
        progress_log.append({"step": "analyzing", "message": f"Starting CFC analysis on {num_windows} windows"})
        with capture_output() as output:
            cfcs = tool_cfc_wavelet(bolds, config)
        captured_output.append(output.getvalue())
        progress_log.append({"step": "analyzed", "message": f"CFC analysis complete: {len(cfcs)} windows processed"})
        
        elapsed = time.time() - start_time
        logger.info(f"CFC analysis completed in {elapsed:.2f}s")
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "data_path": data_path,
            "window_size": window_size,
            "step_size": step_size,
            "num_windows": num_windows,
            "shape": list(bolds.shape),
            "cfcs_count": len(cfcs),
            "elapsed_seconds": elapsed,
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }
    except FileNotFoundError as e:
        logger.error(f"File error: {str(e)}")
        progress_log.append({"step": "error", "message": f"File error: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": "FileNotFoundError",
            "error": str(e),
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        progress_log.append({"step": "error", "message": f"Validation error: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": "ValueError",
            "error": str(e),
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }
    except Exception as e:
        logger.error(f"Unexpected error in CFC analysis: {str(e)}", exc_info=True)
        progress_log.append({"step": "error", "message": f"Unexpected error: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": type(e).__name__,
            "error": str(e),
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }


@server.tool(name="run_hub_detection")
@validate_parameters(
    window_size={'min': 10, 'max': 1000, 'type': int},
    step_size={'min': 1, 'max': 500, 'type': int},
    ratio={'min': 0.0, 'max': 1.0, 'type': float},
    k={'min': 1, 'max': 100, 'type': int},
    hub_num={'min': 1, 'type': int},
)
def run_hub_detection(
    data_path: str = "data_example_BOLD.csv",
    window_size: int = 100,
    step_size: int = 90,
    padding: bool = True,
    ratio: float = 0.8,
    k: int = 2,
    hub_num: int = 10,
    use_group: bool = False,
) -> dict:
    """
    Detect hub nodes in brain networks using graph analysis.
    
    Parameters:
    - data_path: Path to BOLD CSV file
    - window_size: Sliding window size (10-1000)
    - step_size: Window step size (1-500)
    - padding: Pad edges
    - ratio: Edge weight threshold (0.0-1.0)
    - k: Embedding dimension (1-100)
    - hub_num: Number of hubs to identify
    - use_group: Use group/Grassmann manifold method for multiple networks
    
    Returns: Hub detection results with embeddings and selection matrices
    """
    progress_log = []
    captured_output = []
    start_time = time.time()
    
    try:
        logger.info(f"Hub detection started: window_size={window_size}, step_size={step_size}, k={k}, hub_num={hub_num}")
        
        # Resolve file path (checks uploaded_files first, then local directory)
        try:
            data_path = get_file_path(data_path)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Data file not found: {e}")
        
        # Validate parameters
        if step_size > window_size:
            raise ValueError(f"step_size ({step_size}) must be <= window_size ({window_size})")
        
        config = AnalysisConfig()
        config.ratio = ratio
        config.k = k
        config.hub_num = hub_num
        config.use_group = use_group
        
        progress_log.append({"step": "loading", "message": f"Loading BOLD data from {data_path}"})
        with capture_output() as output:
            bolds = load_bolds_from_csv(data_path, window_size=window_size, step_size=step_size, padding=padding)
        captured_output.append(output.getvalue())
        num_windows = bolds.shape[0]
        progress_log.append({"step": "loaded", "message": f"Data loaded successfully: shape {list(bolds.shape)}"})
        
        progress_log.append({"step": "detecting", "message": f"Starting hub detection on {num_windows} windows (k={k}, hub_num={hub_num}, use_group={use_group})"})
        with capture_output() as output:
            results = tool_hub_detection(bolds, config)
        captured_output.append(output.getvalue())
        progress_log.append({"step": "detected", "message": f"Hub detection complete"})
        
        elapsed = time.time() - start_time
        logger.info(f"Hub detection completed in {elapsed:.2f}s")
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "data_path": data_path,
            "window_size": window_size,
            "step_size": step_size,
            "num_windows": num_windows,
            "shape": list(bolds.shape),
            "k": k,
            "hub_num": hub_num,
            "use_group": use_group,
            "results": results,
            "elapsed_seconds": elapsed,
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }
    except FileNotFoundError as e:
        logger.error(f"File error: {str(e)}")
        progress_log.append({"step": "error", "message": f"File error: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": "FileNotFoundError",
            "error": str(e),
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        progress_log.append({"step": "error", "message": f"Validation error: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": "ValueError",
            "error": str(e),
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }
    except Exception as e:
        logger.error(f"Unexpected error in hub detection: {str(e)}", exc_info=True)
        progress_log.append({"step": "error", "message": f"Unexpected error: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": type(e).__name__,
            "error": str(e),
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }

@server.tool(name="ukb_navigator")
def ukb_navigator_tool(
    extract: str,
    field_id: int | None = None,
    browse_id: int | None = None,
    url: str | None = None,
    headless: bool = True,
    timeout_s: float = 25.0,
    max_wait_s: float = 10.0,
) -> dict:
    cfg = UKBNavigatorConfig(headless=headless, timeout_s=timeout_s, max_wait_s=max_wait_s)
    return ukb_navigate(extract=extract, field_id=field_id, browse_id=browse_id, url=url, cfg=cfg)

@server.tool(name="get_growth_curve")
def get_growth_curve(phenotype: str) -> dict:
    """
    Load growth curve data for a given phenotype.
    
    Available phenotypes:
    - Global mean of FC
    - Global system segregation
    - Visual system segregation (VIS)
    - Somatomotor system segregation (SM)
    - Dorsal attention system segregation (DA)
    - Ventral attention system segregation (VA)
    - Limbic system segregation (LIM)
    - Frontoparietal system segregation (FP)
    - Default mode system segregation (DM)
    """
    start_time = time.time()
    try:
        logger.info(f"Loading growth curve for phenotype: {phenotype}")
        data = load_curve_data(phenotype)
        elapsed = time.time() - start_time
        logger.info(f"Growth curve loaded in {elapsed:.2f}s")
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "phenotype": phenotype,
            "data": data,
            "elapsed_seconds": elapsed,
        }
    except KeyError as e:
        logger.error(f"Phenotype not found: {phenotype}")
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": "KeyError",
            "phenotype": phenotype,
            "error": f"Phenotype not found: {phenotype}. Available: Global mean of FC, Visual system segregation (VIS), etc.",
        }
    except Exception as e:
        logger.error(f"Error loading growth curve: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": type(e).__name__,
            "phenotype": phenotype,
            "error": str(e),
        }


@server.tool(name="run_normative_analysis")
def run_normative_analysis(
    x_phenotype: str,
    y_path: str,
    age_col: str,
    val_col: str,
) -> dict:
    """
    Run normative analysis comparing growth curves with overlay data.
    
    Parameters:
    - x_phenotype: Name of phenotype/growth curve
    - y_path: Path to CSV file with overlay data
    - age_col: Column name for age values
    - val_col: Column name for metric values
    
    Returns: Combined x and y data for normative modeling
    """
    start_time = time.time()
    try:
        logger.info(f"Starting normative analysis: phenotype={x_phenotype}, y_path={y_path}")
        
        # Resolve file path (checks uploaded_files first, then local directory)
        if y_path:
            try:
                y_path = get_file_path(y_path)
            except FileNotFoundError as e:
                raise FileNotFoundError(f"Overlay data file not found: {e}")
        
        # Validate column names
        if not age_col or not val_col:
            raise ValueError("age_col and val_col parameters are required")
        
        config = AnalysisConfig()
        config.x_phenotype = x_phenotype
        config.y_path = y_path
        config.age_col = age_col
        config.val_col = val_col
        
        results = tool_normative_analysis(config)
        elapsed = time.time() - start_time
        logger.info(f"Normative analysis completed in {elapsed:.2f}s")
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "phenotype": x_phenotype,
            "y_path": y_path,
            "data": results,
            "elapsed_seconds": elapsed,
        }
    except FileNotFoundError as e:
        logger.error(f"File error: {str(e)}")
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": "FileNotFoundError",
            "phenotype": x_phenotype,
            "error": str(e),
        }
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": "ValueError",
            "phenotype": x_phenotype,
            "error": str(e),
        }
    except Exception as e:
        logger.error(f"Unexpected error in normative analysis: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": type(e).__name__,
            "phenotype": x_phenotype,
            "error": str(e),
        }
    
@server.tool(name="search_pubmed")
@validate_parameters(
    max_results={"min": 1, "max": 200, "type": int},
)
def search_pubmed(
    query: str,
    max_results: int = 20,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> dict:
    """
    Search PubMed via NCBI E-utilities (esearch + esummary) and return table-ready results.

    Returns:
      {
        "status": "success",
        "timestamp": "...",
        "elapsed_seconds": ...,
        "query_used": "...",
        "count_returned": N,
        "results": [ {pmid,title,journal,year,authors,url}, ... ],
        "suggested_keywords": [...],
        "progress": [...]
      }
    """
    progress_log = []
    captured_output = []
    start_time = time.time()

    try:
        q = query.strip()
        if not q:
            raise ValueError("query must be a non-empty string")

        # Optional year filter (simple)
        if year_from is not None and year_to is not None and year_from > year_to:
            raise ValueError(f"year_from ({year_from}) must be <= year_to ({year_to})")

        progress_log.append({"step": "search", "message": f"Searching PubMed for: {q!r}"})
        pmids = _pubmed_esearch(q, max_results=max_results)

        if not pmids:
            elapsed = time.time() - start_time
            return {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "elapsed_seconds": elapsed,
                "query_used": q,
                "count_returned": 0,
                "results": [],
                "suggested_keywords": [],
                "console_output": "",
                "progress": progress_log + [{"step": "done", "message": "No results found"}],
            }

        progress_log.append({"step": "summarize", "message": f"Fetching summaries for {len(pmids)} PMIDs"})
        summary = _pubmed_esummary(pmids)

        result_obj = summary.get("result", {})
        uids = result_obj.get("uids", []) or []

        rows: List[Dict[str, Any]] = []
        for uid in uids:
            item = result_obj.get(uid, {}) or {}
            title = (item.get("title") or "").strip()
            journal = (item.get("fulljournalname") or item.get("source") or "").strip()

            # pubdate can be like "2022 Jan 3" — we extract first YYYY
            year = _extract_year(item.get("pubdate", ""))

            # authors often a list of dicts with "name"
            authors_list = item.get("authors", []) or []
            authors = ", ".join([a.get("name", "").strip() for a in authors_list if a.get("name")])[:300]

            row = {
                "pmid": str(uid),
                "title": title,
                "journal": journal,
                "year": year,
                "authors": authors,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
            }

            # Year filtering (post-filter)
            if year is not None:
                if year_from is not None and year < year_from:
                    continue
                if year_to is not None and year > year_to:
                    continue

            rows.append(row)

        # simple keyword suggestion: pull a few strong terms from query
        tokens = [t.lower() for t in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", q)]
        suggested_keywords = sorted(set(tokens))[:12]

        progress_log.append({"step": "done", "message": f"Returning {len(rows)} results"})

        elapsed = time.time() - start_time
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": elapsed,
            "query_used": q,
            "count_returned": len(rows),
            "results": rows,
            "suggested_keywords": suggested_keywords,
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }

    except ValueError as e:
        logger.error(f"Validation error in PubMed search: {str(e)}")
        progress_log.append({"step": "error", "message": f"Validation error: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": "ValueError",
            "error": str(e),
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }
    except requests.RequestException as e:
        logger.error(f"PubMed request failed: {str(e)}")
        progress_log.append({"step": "error", "message": f"PubMed request failed: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": "RequestException",
            "error": str(e),
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }
    except Exception as e:
        logger.error(f"Unexpected error in PubMed search: {str(e)}", exc_info=True)
        progress_log.append({"step": "error", "message": f"Unexpected error: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": type(e).__name__,
            "error": str(e),
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
        }

@server.tool(name="openalex_search")
@validate_parameters(max_results={"min": 1, "max": 50, "type": int})
def openalex_search(
    query: str,
    max_results: int = 10,
    from_year: Optional[int] = None,
    to_year: Optional[int] = None,
) -> dict:
    progress_log = []
    start_time = time.time()

    try:
        q = query.strip()
        if not q:
            raise ValueError("query must be a non-empty string")
        if from_year is not None and to_year is not None and from_year > to_year:
            raise ValueError("from_year must be <= to_year")

        progress_log.append({"step": "search", "message": f"OpenAlex searching for: {q!r}"})

        params = {
            "search": q,
            "per-page": max_results,
        }

        # OpenAlex filter syntax
        filters = []
        if from_year is not None:
            filters.append(f"from_publication_year:{from_year}")
        if to_year is not None:
            filters.append(f"to_publication_year:{to_year}")
        if filters:
            params["filter"] = ",".join(filters)

        data = _openalex_get(params)

        results = []
        for item in (data.get("results") or [])[:max_results]:
            doi = item.get("doi") or ""
            doi = _clean_doi(doi)

            host_venue = item.get("host_venue") or {}
            venue_name = host_venue.get("display_name") or ""

            authorships = item.get("authorships") or []
            authors = ", ".join(
                [(a.get("author") or {}).get("display_name", "") for a in authorships if (a.get("author") or {}).get("display_name")]
            )[:300]

            results.append({
                "title": (item.get("title") or "").strip(),
                "year": item.get("publication_year"),
                "doi": doi or None,
                "url": (item.get("doi") or item.get("id") or "").strip(),
                "venue": venue_name,
                "authors": authors,
                "cited_by_count": item.get("cited_by_count"),
                "source": "openalex",
            })

        elapsed = time.time() - start_time
        progress_log.append({"step": "done", "message": f"Returning {len(results)} results"})

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": elapsed,
            "query_used": q,
            "count_returned": len(results),
            "results": results,
            "console_output": "",
            "progress": progress_log,
        }

    except Exception as e:
        logger.error(f"OpenAlex search error: {str(e)}", exc_info=True)
        progress_log.append({"step": "error", "message": f"Error: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": type(e).__name__,
            "error": str(e),
            "console_output": "",
            "progress": progress_log,
        }

@server.tool(name="crossref_enrich")
def crossref_enrich(dois: List[str], max_items: int = 50) -> dict:
    progress_log = []
    start_time = time.time()
    try:
        if not dois:
            raise ValueError("dois must be a non-empty list")
        dois = [_clean_doi(d) for d in dois][:max_items]
        dois = [d for d in dois if d]

        progress_log.append({"step": "enrich", "message": f"Crossref enriching {len(dois)} DOIs"})

        results = []
        for i, doi in enumerate(dois, start=1):
            msg = _crossref_get_by_doi(doi)
            if not msg:
                continue

            title_list = msg.get("title") or []
            title = title_list[0].strip() if title_list else ""

            container = msg.get("container-title") or []
            journal = container[0].strip() if container else ""

            issued = (msg.get("issued") or {}).get("date-parts") or []
            year = None
            if issued and issued[0] and isinstance(issued[0][0], int):
                year = issued[0][0]

            author_list = msg.get("author") or []
            authors = ", ".join(
                [(" ".join([a.get("given","").strip(), a.get("family","").strip()]).strip()) for a in author_list if (a.get("given") or a.get("family"))]
            )[:300]

            results.append({
                "doi": doi,
                "title": title,
                "journal": journal,
                "year": year,
                "publisher": msg.get("publisher"),
                "url": (msg.get("URL") or f"https://doi.org/{doi}"),
                "authors": authors,
                "type": msg.get("type"),
                "source": "crossref",
            })

        elapsed = time.time() - start_time
        progress_log.append({"step": "done", "message": f"Enriched {len(results)} items"})

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": elapsed,
            "count_returned": len(results),
            "results": results,
            "console_output": "",
            "progress": progress_log,
        }

    except Exception as e:
        logger.error(f"Crossref enrich error: {str(e)}", exc_info=True)
        progress_log.append({"step": "error", "message": f"Error: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": type(e).__name__,
            "error": str(e),
            "console_output": "",
            "progress": progress_log,
        }

@server.tool(name="internet_search")
@validate_parameters(max_results={"min": 1, "max": 50, "type": int})
def internet_search(
    query: str,
    max_results: int = 10,
    from_year: Optional[int] = None,
    to_year: Optional[int] = None,
) -> dict:
    progress_log = []
    start_time = time.time()

    try:
        progress_log.append({"step": "phase", "message": "Phase 1: OpenAlex discovery"})
        oa = openalex_search(query=query, max_results=max_results, from_year=from_year, to_year=to_year)
        if oa.get("status") != "success":
            return oa  # propagate error

        oa_results = oa.get("results") or []
        dois = [r.get("doi") for r in oa_results if r.get("doi")]
        dois = [_clean_doi(d) for d in dois if d]

        progress_log.append({"step": "phase", "message": f"Phase 2: Crossref enrich ({len(dois)} DOIs)"})
        cr_map = {}
        if dois:
            cr = crossref_enrich(dois=dois, max_items=50)
            if cr.get("status") == "success":
                for item in cr.get("results") or []:
                    if item.get("doi"):
                        cr_map[item["doi"]] = item

        progress_log.append({"step": "phase", "message": "Phase 3: Merge results"})
        merged = []
        for r in oa_results:
            doi = _clean_doi(r.get("doi") or "")
            if doi and doi in cr_map:
                c = cr_map[doi]
                merged.append({
                    "title": c.get("title") or r.get("title"),
                    "year": c.get("year") or r.get("year"),
                    "doi": doi,
                    "url": c.get("url") or r.get("url"),
                    "venue": c.get("journal") or r.get("venue"),
                    "authors": c.get("authors") or r.get("authors"),
                    "source": "openalex+crossref",
                })
            else:
                merged.append({
                    "title": r.get("title"),
                    "year": r.get("year"),
                    "doi": doi or None,
                    "url": r.get("url"),
                    "venue": r.get("venue"),
                    "authors": r.get("authors"),
                    "source": "openalex",
                })

        elapsed = time.time() - start_time
        progress_log.append({"step": "done", "message": f"Returning {len(merged)} merged results"})

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": elapsed,
            "query_used": query,
            "count_returned": len(merged),
            "results": merged,
            "console_output": "",
            "progress": progress_log,
        }

    except Exception as e:
        logger.error(f"Internet search error: {str(e)}", exc_info=True)
        progress_log.append({"step": "error", "message": f"Error: {str(e)}"})
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": type(e).__name__,
            "error": str(e),
            "console_output": "",
            "progress": progress_log,
        }

@server.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint - no authentication required."""
    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "uptime_check": True
    })


@server.custom_route("/api/schema", methods=["GET"])
async def api_schema(request: Request) -> JSONResponse:
    """Provide API schema documentation for agents."""
    schema = {
        "version": "1.0.0",
        "title": "Brain Network Analysis API",
        "description": "MCP server for brain network analysis",
        "endpoints": {
            "run_cfc_wavelet_analysis": {
                "method": "POST",
                "description": "Cross-frequency coupling wavelet analysis",
                "parameters": CFCWaveletRequest.model_json_schema(),
            },
            "run_hub_detection": {
                "method": "POST",
                "description": "Hub detection in brain networks",
                "parameters": HubDetectionRequest.model_json_schema(),
            },
            "get_growth_curve": {
                "method": "POST",
                "description": "Load growth curve data",
                "parameters": {
                    "phenotype": {"type": "string", "description": "Phenotype name"}
                }
            },
            "run_normative_analysis": {
                "method": "POST",
                "description": "Normative developmental trajectory analysis",
                "parameters": NormativeAnalysisRequest.model_json_schema(),
            },
            "search_pubmed": {
                "method": "POST",
                "description": "Search PubMed via NCBI E-utilities (esearch + esummary)",
                "parameters": PubMedSearchRequest.model_json_schema(),
            },
            "openalex_search": {
                "method": "POST",
                "description": "Scholarly discovery search via OpenAlex works",
                "parameters": OpenAlexSearchRequest.model_json_schema(),
            },
            "crossref_enrich": {
                "method": "POST",
                "description": "Enrich/normalize bibliographic metadata by DOI via Crossref",
                "parameters": CrossrefEnrichRequest.model_json_schema(),
            },
            "internet_search": {
                "method": "POST",
                "description": "Combined internet search (OpenAlex discovery + Crossref DOI enrichment)",
                "parameters": InternetSearchRequest.model_json_schema(),
            },
            "upload": {
                "method": "POST",
                "description": "Upload a file for analysis (multipart/form-data)",
                "parameters": {
                    "file": {"type": "file", "description": "Multipart file field named 'file'"}
                }
            },
            "list_files": {
                "method": "GET",
                "description": "List uploaded files",
                "parameters": {}
            },
            "delete_file": {
                "method": "DELETE or POST",
                "description": "Delete an uploaded file (JSON body: {\"filename\": \"...\"})",
                "parameters": {
                    "filename": {"type": "string", "description": "Name of the uploaded file to delete"}
                }
            },
        },
        "rate_limiting": {
            "requests_per_window": RATE_LIMIT_REQUESTS,
            "window_seconds": RATE_LIMIT_WINDOW,
        }
    }
    return JSONResponse(schema)


@server.custom_route("/run_cfc_wavelet_analysis", methods=["POST"])
@rate_limit
async def http_run_cfc_wavelet_analysis(request: Request) -> JSONResponse:
    """HTTP endpoint for CFC wavelet analysis."""
    try:
        data = await request.json()
        # Validate using Pydantic model
        validated_data = CFCWaveletRequest(**data)
        
        result = run_cfc_wavelet_analysis(
            data_path=validated_data.data_path,
            window_size=validated_data.window_size,
            step_size=validated_data.step_size,
            padding=validated_data.padding,
            ratio=validated_data.ratio,
            wavelets_num=validated_data.wavelets_num,
            beta=validated_data.beta,
            gamma=validated_data.gamma,
            max_iter=validated_data.max_iter,
            node_select=validated_data.node_select,
        )
        return JSONResponse(result)
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@server.custom_route("/run_hub_detection", methods=["POST"])
@rate_limit
async def http_run_hub_detection(request: Request) -> JSONResponse:
    """HTTP endpoint for hub detection."""
    try:
        data = await request.json()
        # Validate using Pydantic model
        validated_data = HubDetectionRequest(**data)
        
        result = run_hub_detection(
            data_path=validated_data.data_path,
            window_size=validated_data.window_size,
            step_size=validated_data.step_size,
            padding=validated_data.padding,
            ratio=validated_data.ratio,
            k=validated_data.k,
            hub_num=validated_data.hub_num,
            use_group=validated_data.use_group,
        )
        return JSONResponse(result)
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@server.custom_route("/get_growth_curve", methods=["POST"])
@rate_limit
async def http_get_growth_curve(request: Request) -> JSONResponse:
    """HTTP endpoint for growth curve data."""
    try:
        data = await request.json()
        phenotype = data.get("phenotype", "Global mean of FC")
        
        if not phenotype:
            raise HTTPException(status_code=400, detail="phenotype parameter required")
        
        result = get_growth_curve(phenotype=phenotype)
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@server.custom_route("/run_normative_analysis", methods=["POST"])
@rate_limit
async def http_run_normative_analysis(request: Request) -> JSONResponse:
    """HTTP endpoint for normative analysis."""
    try:
        data = await request.json()
        # Validate using Pydantic model
        validated_data = NormativeAnalysisRequest(**data)
        
        result = run_normative_analysis(
            x_phenotype=validated_data.x_phenotype,
            y_path=validated_data.y_path,
            age_col=validated_data.age_col,
            val_col=validated_data.val_col,
        )
        return JSONResponse(result)
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@server.custom_route("/search_pubmed", methods=["POST"])
@rate_limit
async def http_search_pubmed(request: Request) -> JSONResponse:
    """HTTP endpoint for PubMed search."""
    try:
        data = await request.json()
        validated = PubMedSearchRequest(**data)

        result = search_pubmed(
            query=validated.query,
            max_results=validated.max_results,
            year_from=validated.year_from,
            year_to=validated.year_to,
        )
        return JSONResponse(result)
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@server.custom_route("/openalex_search", methods=["POST"])
@rate_limit
async def http_openalex_search(request: Request) -> JSONResponse:
    data = await request.json()
    v = OpenAlexSearchRequest(**data)
    return JSONResponse(openalex_search(v.query, v.max_results, v.from_year, v.to_year))


@server.custom_route("/crossref_enrich", methods=["POST"])
@rate_limit
async def http_crossref_enrich(request: Request) -> JSONResponse:
    data = await request.json()
    v = CrossrefEnrichRequest(**data)
    return JSONResponse(crossref_enrich(v.dois, v.max_items))


@server.custom_route("/internet_search", methods=["POST"])
@rate_limit
async def http_internet_search(request: Request) -> JSONResponse:
    data = await request.json()
    v = InternetSearchRequest(**data)
    return JSONResponse(internet_search(v.query, v.max_results, v.from_year, v.to_year))


@server.custom_route("/run_ukb_navigator", methods=["POST"])
@rate_limit
async def http_run_ukb_navigator(request: Request) -> JSONResponse:
    try:
        data = await request.json()
        validated_data = UKBNavigatorRequest(**data)

        result = await run_in_threadpool(
            ukb_navigator_tool,
            extract=validated_data.extract,
            field_id=validated_data.field_id,
            browse_id=validated_data.browse_id,
            url=validated_data.url,
            headless=validated_data.headless,
            timeout_s=validated_data.timeout_s,
            max_wait_s=validated_data.max_wait_s,
        )
        return JSONResponse(result)

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")

    except Exception as e:
        logger.error(f"Request error: {str(e)}", exc_info=True)
        return JSONResponse(
            {"status": "error", "error_type": type(e).__name__, "error": str(e)},
            status_code=500,
        )

@server.custom_route("/upload", methods=["POST"])
@rate_limit
async def upload_file(request: Request) -> JSONResponse:
    """Upload a file to the server for analysis.
    
    Expects multipart form data with 'file' field.
    """
    try:
        form = await request.form()
        
        if 'file' not in form:
            raise HTTPException(status_code=400, detail="No file provided in request")
        
        uploaded_file = form['file']
        
        if not uploaded_file.filename:
            raise HTTPException(status_code=400, detail="File has no name")
        
        # Read file content
        file_content = await uploaded_file.read()
        
        if not file_content:
            raise HTTPException(status_code=400, detail="File is empty")
        
        # Save file
        file_path, file_info = save_uploaded_file(file_content, uploaded_file.filename)
        
        logger.info(f"File uploaded: {file_info['saved_filename']}")
        
        return JSONResponse({
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "file_info": file_info,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@server.custom_route("/list_files", methods=["GET"])
async def list_files(request: Request) -> JSONResponse:
    """List all uploaded files."""
    try:
        files = list_uploaded_files()
        logger.info(f"Listed {len(files)} uploaded files")
        
        return JSONResponse({
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "count": len(files),
            "files": files,
        })
    except Exception as e:
        logger.error(f"List files error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@server.custom_route("/delete_file", methods=["DELETE", "POST"])
@rate_limit
async def delete_file(request: Request) -> JSONResponse:
    """Delete an uploaded file.
    
    Expects JSON with 'filename' field.
    """
    try:
        if request.method == "DELETE":
            data = await request.json()
        else:
            data = await request.json()
        
        filename = data.get("filename", "")
        if not filename:
            raise HTTPException(status_code=400, detail="Filename required")
        
        result = delete_uploaded_file(filename)
        logger.info(f"File deleted: {filename}")
        
        return JSONResponse({
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "result": result,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete file error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


if __name__ == "__main__":
    logger.info("="*60)
    logger.info("Brain Network Analysis MCP Server starting...")
    logger.info(f"Rate limiting: {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW}s")
    logger.info(f"Listening on: http://{_SERVER_HOST}:{_SERVER_PORT}")
    logger.info("="*60)
    logger.info("Available endpoints:")
    logger.info("  GET  /health                     - Health check")
    logger.info("  GET  /api/schema                 - API schema documentation")
    logger.info("  POST /run_cfc_wavelet_analysis   - CFC analysis")
    logger.info("  POST /run_hub_detection          - Hub detection")
    logger.info("  POST /get_growth_curve           - Growth curve data")
    logger.info("  POST /run_normative_analysis     - Normative analysis")
    logger.info("  POST /search_pubmed             - PubMed literature search")
    logger.info("  POST /upload                     - Upload file for analysis")
    logger.info("  GET  /list_files                 - List uploaded files")
    logger.info("  DELETE /delete_file              - Delete uploaded file")
    logger.info("="*60)
    
    try:
        server.run(transport="streamable-http", mount_path='/ram/USERS/ziquanw/brain-network-chart/uploaded_files')
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {str(e)}", exc_info=True)
    finally:
        logger.info("Server stopped")
