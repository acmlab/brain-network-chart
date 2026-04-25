# from mcp.server.fastmcp import FastMCP
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.exceptions import HTTPException
import sys
import io
import logging
import time
import os
import re
import requests
from urllib.parse import quote_plus
import json
import xml.etree.ElementTree as ET
from requests.adapters import HTTPAdapter
from threading import Lock
from urllib3.util.retry import Retry
from typing import Optional, List, Dict, Any
from functools import wraps
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, Callable
from pydantic import BaseModel, Field, field_validator, ValidationInfo
from starlette.responses import Response as StarletteResponse, FileResponse
from hub_detection import detect_hubs_from_graphs
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
    _read_table,
    load_roi_list,
    composite_roi_images,
    load_bolds_full,
    load_bolds_list,
    load_adjs_from_path,
    list_bold_paths,
    load_adjs_from_npy,
    list_available_phenotypes,
    _ROI_FIG_DIR,
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from stats_tools import StatsToolkit
try:
    from civet_skills import (
        inspect_civet_folder,
        load_cortical_thickness_map,
        run_civet_qc_check,
        visualize_civet_surface,
    )
except ImportError:
    from mcp_server.civet_skills import (
        inspect_civet_folder,
        load_cortical_thickness_map,
        run_civet_qc_check,
        visualize_civet_surface,
    )

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
    # host=_SERVER_HOST,
    # port=_SERVER_PORT,
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
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW = 60  # seconds
client_requests: Dict[str, list] = {}

# Request/Response schemas
class CFCWaveletRequest(BaseModel):
    data_path: str = Field(default="data_example_BOLD.csv", description="Path to BOLD CSV file")
    
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

class InspectCivetFolderRequest(BaseModel):
    subject_dir: str = Field(..., description="Path to a CIVET subject output folder")

class RunCivetQcCheckRequest(BaseModel):
    qc_file: str = Field(..., description="Path to a CIVET QC CSV, TSV, or whitespace table")
    subject_id: Optional[str] = Field(None, description="Optional subject identifier to select one QC row")

class LoadCorticalThicknessMapRequest(BaseModel):
    thickness_file: str = Field(..., description="Path to a text file containing cortical thickness values")

class VisualizeCivetSurfaceRequest(BaseModel):
    surface_path: str = Field(..., description="Path to a CIVET OBJ surface file")
    overlay_path: Optional[str] = Field(None, description="Optional path to vertex-wise overlay values")
    output_dir: str = Field("outputs", description="Directory where the Plotly HTML figure will be written")

# class OpenNeuroSearchRequest(BaseModel):
#     query: str = Field(..., min_length=1, description="Keyword query for OpenNeuro datasets")
#     max_results: int = Field(default=10, ge=1, le=50, description="Number of datasets to return (1-50)")
#     modality: Optional[str] = Field(None, description="Optional modality filter (best-effort; depends on OpenNeuro schema)")

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


def _pubmed_efetch_abstracts(pmids: List[str]) -> Dict[str, str]:
    """Fetch PubMed abstracts via efetch XML. Returns mapping: PMID -> abstract text."""
    if not pmids:
        return {}

    url = f"{PUBMED_EUTILS_BASE}/efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        **_pubmed_base_params(),
    }

    r = _pubmed_session().get(url, params=params, timeout=40)
    r.raise_for_status()

    abstracts_by_pmid: Dict[str, str] = {}
    root = ET.fromstring(r.text)

    for article in root.findall(".//PubmedArticle"):
        pmid_node = article.find(".//MedlineCitation/PMID")
        if pmid_node is None or not (pmid_node.text or "").strip():
            continue
        pmid = (pmid_node.text or "").strip()

        abstract_text_nodes = article.findall(".//MedlineCitation/Article/Abstract/AbstractText")
        if not abstract_text_nodes:
            abstracts_by_pmid[pmid] = ""
            continue

        parts: List[str] = []
        for node in abstract_text_nodes:
            section_text = "".join(node.itertext()).strip()
            if not section_text:
                continue
            label = (node.attrib.get("Label") or "").strip()
            if label:
                parts.append(f"{label}: {section_text}")
            else:
                parts.append(section_text)

        abstracts_by_pmid[pmid] = "\n".join(parts).strip()

    return abstracts_by_pmid

from urllib.parse import quote_plus

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

OPENNEURO_GQL_URL = "https://openneuro.org/crn/graphql"

_openneuro_schema_cache: dict | None = None
_openneuro_schema_lock = Lock()


def _openneuro_post(query: str, variables: dict | None = None, timeout_s: float = 20.0) -> dict:
    payload = {"query": query, "variables": variables or {}}
    headers = {
        "User-Agent": "brain-network-chart-openneuro-client",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    r = requests.post(OPENNEURO_GQL_URL, json=payload, headers=headers, timeout=timeout_s)

    if not r.ok:
        body = (r.text or "").strip()
        if len(body) > 800:
            body = body[:800] + " ...[truncated]"
        raise ValueError(f"OpenNeuro HTTP {r.status_code} error. Body: {body}")

    return r.json()

def _openneuro_get_query_fields(timeout_s: float = 20.0) -> dict:
    """
    Introspect OpenNeuro GraphQL schema once per process and cache it.
    We only need the root Query fields + their args to detect how dataset listing/search works.
    """
    global _openneuro_schema_cache
    with _openneuro_schema_lock:
        if _openneuro_schema_cache is not None:
            return _openneuro_schema_cache

        introspection = """
        query IntrospectQueryFields {
            __schema {
                queryType {
                    fields {
                        name
                        type { kind name ofType { kind name ofType { kind name ofType { kind name }}}}
                        args {
                            name
                            type { kind name ofType { kind name ofType { kind name ofType { kind name }}}}
                        }
                    }
                }
            }
        }
        """
        data = _openneuro_post(introspection, timeout_s=timeout_s)
        _openneuro_schema_cache = data
        return data


def _gql_type_name(t: dict | None) -> str:
    """
    Best-effort extract a readable GraphQL type name from introspection output.
    """
    if not t:
        return ""
    cur = t
    for _ in range(6):
        name = cur.get("name")
        if name:
            return name
        cur = cur.get("ofType") or {}
    return ""


def _gql_is_list(t: dict | None) -> bool:
    if not t:
        return False
    cur = t
    for _ in range(10):
        if cur.get("kind") == "LIST":
            return True
        cur = cur.get("ofType") or {}
    return False


_openneuro_type_cache: dict[str, dict] = {}


def _openneuro_get_type(type_name: str, timeout_s: float = 20.0) -> dict:
    """Introspect a single GraphQL type definition and cache it."""
    if not type_name:
        return {}
    with _openneuro_schema_lock:
        if type_name in _openneuro_type_cache:
            return _openneuro_type_cache[type_name]

    q = """
    query TypeDef($name: String!) {
      __type(name: $name) {
        name
        kind
        fields {
          name
          type { kind name ofType { kind name ofType { kind name ofType { kind name }}}}
        }
      }
    }
    """
    data = _openneuro_post(q, variables={"name": type_name}, timeout_s=timeout_s)
    with _openneuro_schema_lock:
        _openneuro_type_cache[type_name] = data
    return data


def _openneuro_type_fields(type_name: str) -> list[dict]:
    data = _openneuro_get_type(type_name)
    return (data.get("data") or {}).get("__type", {}).get("fields", []) or []


def _openneuro_pick_id_and_name_fields(type_name: str) -> tuple[str | None, str | None]:
    fields = _openneuro_type_fields(type_name)
    names = {f.get("name") for f in fields if f.get("name")}

    id_candidates = [
        "id",
        "datasetId",
        "accessionNumber",
        "openneuroId",
    ]
    name_candidates = [
        "name",
        "title",
    ]

    id_field = next((c for c in id_candidates if c in names), None)
    name_field = next((c for c in name_candidates if c in names), None)

    # Best-effort fallback: any field containing 'id'
    if not id_field:
        for n in sorted(names):
            if n and ("id" in n.lower()):
                id_field = n
                break

    return id_field, name_field


def _arg_is_string(arg: dict) -> bool:
    """
    Determine if an arg is (or wraps) a GraphQL String.
    """
    t = arg.get("type") or {}
    if _gql_type_name(t) == "String":
        return True
    cur = t
    for _ in range(8):
        cur = cur.get("ofType") or {}
        if _gql_type_name(cur) == "String":
            return True
    return False


def _openneuro_pick_dataset_field() -> tuple[str, str | None, set[str], dict, list[str]]:
    """
    Detect a root query field suitable for dataset search/listing.

        Returns:
            (field_name, string_arg_name_or_none, arg_names, type_ref, available_field_names)

    - If a field looks like search (has a String arg), returns that arg name.
    - Else, tries a 'datasets' list field with no string arg (client-side filtering fallback).
    - Else, returns ( "", None, available_fields ) and caller raises a helpful error.
    """
    schema = _openneuro_get_query_fields()
    fields = schema.get("data", {}).get("__schema", {}).get("queryType", {}).get("fields", []) or []
    available = sorted([f.get("name") for f in fields if f.get("name")])

    if not fields:
        return "", None, set(), {}, available

    preferred_arg_names = ["q", "query", "search", "term", "text", "keywords"]
    # Common non-search string args (pagination/filter/sort) that should not be treated
    # as free-text search parameters.
    non_search_string_args = {
        "after",
        "before",
        "cursor",
        "startcursor",
        "endcursor",
        "sort",
        "order",
        "orderby",
        "direction",
        "modality",
    }

    # 1) Prefer explicit search-like fields (search/find) with a String arg.
    for f in fields:
        fname = f.get("name") or ""
        if not fname:
            continue
        lname = fname.lower()
        if ("search" in lname) or ("find" in lname):
            args = f.get("args", []) or []
            # prefer well-known arg names
            for an in preferred_arg_names:
                for a in args:
                    if a.get("name") == an and _arg_is_string(a):
                        arg_names = {x.get("name") for x in args if x.get("name")}
                        return fname, an, arg_names, (f.get("type") or {}), available
            # else take any string arg
            for a in args:
                an = (a.get("name") or "").lower()
                if _arg_is_string(a) and an and an not in non_search_string_args:
                    arg_names = {x.get("name") for x in args if x.get("name")}
                    return fname, a.get("name"), arg_names, (f.get("type") or {}), available

    # 2) Dataset-like fields: only treat as search if they expose a known search arg name.
    for f in fields:
        fname = f.get("name") or ""
        if not fname:
            continue
        lname = fname.lower()
        if "dataset" in lname:
            args = f.get("args", []) or []
            for an in preferred_arg_names:
                for a in args:
                    if a.get("name") == an and _arg_is_string(a):
                        arg_names = {x.get("name") for x in args if x.get("name")}
                        return fname, an, arg_names, (f.get("type") or {}), available

    # 3) Fallback: a datasets-like list field (plural) even if no search arg
    for f in fields:
        fname = f.get("name") or ""
        if not fname:
            continue
        if "datasets" in fname.lower():
            args = f.get("args", []) or []
            arg_names = {x.get("name") for x in args if x.get("name")}
            return fname, None, arg_names, (f.get("type") or {}), available

    # 4) no usable field found
    return "", None, set(), {}, available


def _openneuro_parse_relay_connection(conn: dict) -> list[dict]:
    """
    Parse Relay-style connection objects: { edges: [{ node: {id, name, ...}}] }.
    Returns list of nodes.
    """
    if not isinstance(conn, dict):
        return []
    edges = conn.get("edges") or []
    out = []
    for e in edges:
        node = (e or {}).get("node") or {}
        if isinstance(node, dict) and node.get("id"):
            out.append(node)
    return out


def _openneuro_parse_nodes_list(nodes_payload: Any, id_key: str | None, name_key: str | None) -> list[dict]:
    if not isinstance(nodes_payload, list):
        return []
    out: list[dict] = []
    for node in nodes_payload:
        if not isinstance(node, dict):
            continue
        if id_key and node.get(id_key):
            out.append(node)
        elif (not id_key) and (name_key and node.get(name_key)):
            out.append(node)
    return out


def _openneuro_pick_container_shape(return_type_name: str) -> tuple[str, str | None, str]:
    """
    Determine how to traverse the result object to reach dataset nodes.

    Returns:
      (shape, edge_node_field, node_type_name)

    shape: one of 'edges', 'nodes', 'results', 'self'
    """
    fields = _openneuro_type_fields(return_type_name)
    by_name = {f.get("name"): f for f in fields if f.get("name")}

    if "edges" in by_name:
        edges_type = _gql_type_name((by_name["edges"].get("type") or {}))
        edge_fields = _openneuro_type_fields(edges_type)
        edge_field_names = {f.get("name") for f in edge_fields if f.get("name")}
        node_field = "node" if "node" in edge_field_names else ("dataset" if "dataset" in edge_field_names else None)
        if node_field:
            node_type = _gql_type_name((next((f for f in edge_fields if f.get("name") == node_field), {}) or {}).get("type") or {})
        else:
            node_type = ""
        return "edges", node_field, node_type

    if "nodes" in by_name:
        node_type = _gql_type_name((by_name["nodes"].get("type") or {}))
        return "nodes", None, node_type

    if "results" in by_name:
        node_type = _gql_type_name((by_name["results"].get("type") or {}))
        return "results", None, node_type

    # Fall back: assume return type is itself a Dataset-like object
    return "self", None, return_type_name


def _openneuro_try_queries(
    field_name: str,
    arg_name: str | None,
    arg_names: set[str],
    return_type_ref: dict,
    query_text: str,
    max_results: int,
    progress_log: list,
    modality: str | None = None,
) -> list[dict]:
    """
    Robust OpenNeuro GraphQL dataset retrieval.

    Key fixes vs previous version:
    - If field_name == "datasets", use a dedicated pagination query with `after` + `pageInfo`.
      This is the only reliable way right now because OpenNeuro `search()` returns null.
    - Remove the invalid "self" selection variant, which caused:
        Cannot query field "id" on type "DatasetConnection".
    - Stop safely on OpenNeuro cursor errors or datasets=null.

    Returns: list of {dataset_id, name, url, source}
    """
    return_type_name = _gql_type_name(return_type_ref)
    if not return_type_name:
        raise ValueError("OpenNeuro schema introspection did not return a usable return type")

    progress_log.append({"step": "schema", "message": f"OpenNeuro return type for '{field_name}' is {return_type_name!r}"})

    # Determine dataset node type + fields
    shape, edge_node_field, node_type_name = _openneuro_pick_container_shape(return_type_name)
    if not node_type_name:
        node_type_name = return_type_name

    ds_id_field, ds_name_field = _openneuro_pick_id_and_name_fields(node_type_name)
    if not ds_id_field:
        ds_id_field = "id"
    if not ds_name_field:
        ds_name_field = "name"

    leaf_fields = " ".join([f for f in [ds_id_field, ds_name_field] if f])

    # ----------------------------
    # Special-case: datasets() pagination (RECOMMENDED)
    # ----------------------------
    if field_name == "datasets":
        # We will fetch up to a fixed number of pages; caller will do scoring/filtering.
        # Over-fetch to increase chance of local matches.
        page_size = min(50, max(10, max_results))  # keep it reasonable
        max_pages = 12  # safety cap
        after = None

        gql = """
        query ListDatasets($first: Int!, $after: String, $modality: String, $public: Boolean) {
          datasets(first: $first, after: $after, modality: $modality, filterBy: { public: $public }) {
            edges {
              node {
                %s
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
        """ % leaf_fields

        results: list[dict] = []
        seen: set[str] = set()

        for page in range(1, max_pages + 1):
            vars_ = {
                "first": page_size,
                "after": after,
                "modality": modality,
                "public": True,
            }

            progress_log.append(
                {"step": "page", "message": f"OpenNeuro datasets(): fetching page {page} (first={page_size}, after={after!r})"}
            )

            data = _openneuro_post(gql, variables=vars_, timeout_s=25.0)

            # Handle GraphQL errors safely
            if isinstance(data, dict) and data.get("errors"):
                msg = data["errors"][0].get("message", "Unknown GraphQL error")
                progress_log.append({"step": "gql_error", "message": f"OpenNeuro datasets() error: {msg}"})
                break

            payload = (data.get("data") or {}).get("datasets")
            if payload is None:
                progress_log.append({"step": "warn", "message": "OpenNeuro returned datasets=null; stopping pagination"})
                break

            edges = payload.get("edges") or []
            for e in edges:
                node = (e or {}).get("node") or {}
                ds_id = node.get(ds_id_field) or node.get("id")
                name = (node.get(ds_name_field) or node.get("name") or "").strip()
                if not ds_id or ds_id in seen:
                    continue
                seen.add(ds_id)
                results.append(
                    {
                        "dataset_id": ds_id,
                        "name": name,
                        "url": f"https://openneuro.org/datasets/{quote_plus(ds_id)}",
                        "source": "openneuro",
                    }
                )

            page_info = payload.get("pageInfo") or {}
            has_next = bool(page_info.get("hasNextPage"))
            end_cursor = page_info.get("endCursor")

            progress_log.append(
                {"step": "cursor", "message": f"pageInfo: hasNextPage={has_next}, endCursor={end_cursor!r}"}
            )

            if not has_next or not end_cursor:
                break

            # Always pass the exact cursor string back; any corruption triggers OpenNeuro decode errors.
            after = end_cursor

            # If we already collected a lot, we can stop early. Caller will re-rank/filter.
            if len(results) >= max(200, max_results * 50):
                progress_log.append({"step": "stop", "message": "Collected enough candidate datasets; stopping early"})
                break

        return results

    # ----------------------------
    # Generic path for other fields (limited template tries)
    # ----------------------------

    def _call_args(include_limit: bool) -> tuple[str, dict, str]:
        parts: list[str] = []
        vars_: dict = {}
        var_defs: list[str] = []

        if arg_name is not None:
            parts.append(f"{arg_name}: $q")
            vars_["q"] = query_text
            var_defs.append("$q: String!")

        if modality and ("modality" in arg_names):
            parts.append("modality: $modality")
            vars_["modality"] = modality
            var_defs.append("$modality: String")

        if include_limit:
            if "first" in arg_names:
                parts.append("first: $limit")
                vars_["limit"] = max_results
                var_defs.append("$limit: Int!")
            elif "limit" in arg_names:
                parts.append("limit: $limit")
                vars_["limit"] = max_results
                var_defs.append("$limit: Int!")

        return ", ".join(parts), vars_, ", ".join(var_defs)

    selection_variants: list[tuple[str, str]] = []
    if shape == "edges":
        # Prefer detected edge field if present; else default to node/dataset
        if edge_node_field:
            selection_variants.append(("edges", f"edges {{ {edge_node_field} {{ {leaf_fields} }} }}"))
        selection_variants.append(("edges", f"edges {{ node {{ {leaf_fields} }} }}"))
        selection_variants.append(("edges", f"edges {{ dataset {{ {leaf_fields} }} }}"))
    if shape in ("nodes", "results"):
        selection_variants.append((shape, f"{shape} {{ {leaf_fields} }}"))
    # Extra fallbacks (SAFE only — no "self")
    selection_variants.extend([
        ("nodes", f"nodes {{ {leaf_fields} }}"),
        ("results", f"results {{ {leaf_fields} }}"),
    ])

    templates: list[tuple[str, dict, str]] = []
    for include_limit in (True, False):
        call_args, vars_, var_defs = _call_args(include_limit=include_limit)
        call = f"{field_name}({call_args})" if call_args else field_name
        defs = f"({var_defs})" if var_defs else ""
        for label, selection in selection_variants:
            gql = f"query OpenNeuro{defs} {{\n  {call} {{\n    {selection}\n  }}\n}}\n"
            templates.append((gql, vars_, label))

    last_err = None
    for i, (gql, vars_, label) in enumerate(templates, start=1):
        progress_log.append({"step": "gql", "message": f"Trying OpenNeuro GraphQL template #{i} (shape={label})"})
        try:
            data = _openneuro_post(gql, variables=vars_, timeout_s=25.0)
            if "errors" in data and data["errors"]:
                last_err = data["errors"][0].get("message", "Unknown GraphQL error")
                continue

            payload = (data.get("data") or {}).get(field_name)
            nodes: list[dict] = []

            if isinstance(payload, dict) and "edges" in payload:
                edges = payload.get("edges") or []
                for e in edges:
                    if not isinstance(e, dict):
                        continue
                    node = e.get("node") or e.get("dataset")
                    if isinstance(node, dict):
                        nodes.append(node)
            elif isinstance(payload, dict) and "nodes" in payload:
                nodes = _openneuro_parse_nodes_list(payload.get("nodes"), ds_id_field, ds_name_field)
            elif isinstance(payload, dict) and "results" in payload:
                nodes = _openneuro_parse_nodes_list(payload.get("results"), ds_id_field, ds_name_field)
            elif isinstance(payload, list):
                nodes = _openneuro_parse_nodes_list(payload, ds_id_field, ds_name_field)
            elif isinstance(payload, dict):
                nodes = [payload]

            results = []
            for node in nodes:
                ds_id = node.get(ds_id_field) if ds_id_field else node.get("id")
                name = (node.get(ds_name_field) if ds_name_field else node.get("name")) or ""
                if not ds_id:
                    continue
                results.append({
                    "dataset_id": ds_id,
                    "name": name,
                    "url": f"https://openneuro.org/datasets/{quote_plus(ds_id)}",
                    "source": "openneuro",
                })

            if results:
                return results

            last_err = "Template returned 0 datasets"
        except Exception as e:
            last_err = str(e)
            continue

    raise ValueError(f"OpenNeuro GraphQL query failed across templates. Last error: {last_err}")



@server.tool(name="run_cfc_wavelet_analysis")
def run_cfc_wavelet_analysis(
    data_path: str = "data_example_BOLD.csv",
) -> dict:
    """
    Run cross-frequency coupling (CFC) analysis using harmonic wavelets.
    
    Parameters:
    - data_path: Path to BOLD CSV file
    
    Returns: Analysis results with console output and progress tracking
    """
    progress_log = []
    captured_output = []
    start_time = time.time()
    window_size: int = 30
    step_size: int = 15
    padding: bool = True
    ratio: float = 0.8
    wavelets_num: int = 10
    beta: float = 1.0
    gamma: float = 0.1
    max_iter: int = 100
    node_select: int = 10
    
    try:
        logger.info(f"CFC analysis started: window_size={window_size}, step_size={step_size}")
        
        # Resolve file path (checks uploaded_files first, then local directory)
        try:
            data_path = get_file_path(data_path)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Data file not found: {e}")
        
        # Validate parameters consistency
        # if step_size > window_size:
        #     raise ValueError(f"step_size ({step_size}) must be <= window_size ({window_size})")
        
        config = AnalysisConfig()
        config.ratio = ratio
        config.wavelets_num = wavelets_num
        config.beta = beta
        config.gamma = gamma
        config.max_iter = max_iter
        config.node_select = node_select
        
        import numpy as _np
        all_cfcs = []
        files_cfcs = []
        files_avg_cfcs = []

        is_npy = data_path.lower().endswith('.npy')

        if is_npy:
            fname = os.path.basename(data_path)
            progress_log.append({"step": "loading", "message": f"Loading .npy adj from {fname}"})
            adjs = load_adjs_from_npy(data_path)   # (num_windows, nodes, nodes)
            progress_log.append({"step": "loaded", "message": f"Loaded {len(adjs)} adj matrices"})
            progress_log.append({"step": "analyzing", "message": f"Running CFC on {fname}"})
            with capture_output() as output:
                cfcs_for_file = tool_cfc_wavelet(adjs, config, precomputed_fcs=True)
            captured_output.append(output.getvalue())
            all_cfcs = list(cfcs_for_file)
            file_avg = _np.mean([_np.array(c) for c in cfcs_for_file], axis=0).tolist() if cfcs_for_file else []
            files_cfcs = [{"filename": fname, "cfcs": cfcs_for_file}]
            files_avg_cfcs = [{"filename": fname, "avg_cfc": file_avg}]
        else:
            progress_log.append({"step": "loading", "message": f"Resolving paths from {data_path}"})
            file_paths = list_bold_paths(data_path)
            progress_log.append({"step": "loaded", "message": f"Found {len(file_paths)} file(s)"})
            for fname, fpath in file_paths:
                progress_log.append({"step": "analyzing", "message": f"Running CFC on {fname}"})
                with capture_output() as output:
                    b = load_bolds_from_csv(fpath, window_size=window_size, step_size=step_size, padding=padding)
                    cfcs_for_file = tool_cfc_wavelet(b, config)
                captured_output.append(output.getvalue())
                all_cfcs.extend(cfcs_for_file)
                file_avg = _np.mean([_np.array(c) for c in cfcs_for_file], axis=0).tolist() if cfcs_for_file else []
                files_cfcs.append({"filename": fname, "cfcs": cfcs_for_file})
                files_avg_cfcs.append({"filename": fname, "avg_cfc": file_avg})

        num_windows = len(all_cfcs)
        if all_cfcs:
            avg_cfc = _np.mean([_np.array(c) for c in all_cfcs], axis=0).tolist()
        else:
            avg_cfc = []

        progress_log.append({"step": "analyzed", "message": f"CFC analysis complete: {num_windows} total windows"})

        elapsed = time.time() - start_time
        logger.info(f"CFC analysis completed in {elapsed:.2f}s")

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "data_path": data_path,
            "window_size": window_size,
            "step_size": step_size,
            "num_windows": num_windows,
            "cfcs_count": num_windows,
            "cfcs": all_cfcs,
            "avg_cfc": avg_cfc,
            "files_cfcs": files_cfcs,
            "files_avg_cfcs": files_avg_cfcs if len(files_cfcs) > 1 else [],
            "elapsed_seconds": elapsed,
            "console_output": "\n".join(captured_output),
            # "progress": progress_log,
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
            # "progress": progress_log,
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
            # "progress": progress_log,
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
            # "progress": progress_log,
        }


@server.tool(name="run_hub_detection")
@validate_parameters(
    ratio={'min': 0.0, 'max': 1.0, 'type': float},
    k={'min': 1, 'max': 100, 'type': int},
    hub_num={'min': 1, 'type': int},
)
def run_hub_detection(
    data_path: str = "data_example_BOLD.csv",
    ratio: float = 0.8,
    k: int = 2,
    hub_num: int = 10,
    use_group: bool = False,
) -> dict:
    """
    Detect hub nodes in brain networks using graph analysis.

    Parameters:
    - data_path: Path to BOLD CSV file
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
        logger.info(f"Hub detection started: k={k}, hub_num={hub_num}")

        config = AnalysisConfig()
        config.ratio = ratio
        config.k = k
        config.hub_num = hub_num
        config.use_group = use_group

        progress_log.append({"step": "loading", "message": f"Loading BOLD data from {data_path}"})
        with capture_output() as output:
            adjs = load_adjs_from_path(data_path, config)
        captured_output.append(output.getvalue())
        num_windows = len(adjs)
        progress_log.append({"step": "loaded", "message": f"Data loaded: {num_windows} adjacency matrices"})

        progress_log.append({"step": "detecting", "message": f"Starting hub detection (k={k}, hub_num={hub_num}, use_group={use_group})"})
        with capture_output() as output:
            results = detect_hubs_from_graphs(adjs, k=k, hub=hub_num, use_group=use_group)
        captured_output.append(output.getvalue())
        progress_log.append({"step": "detected", "message": f"Hub detection complete"})

        elapsed = time.time() - start_time
        logger.info(f"Hub detection completed in {elapsed:.2f}s")

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "data_path": data_path,
            "num_windows": num_windows,
            "k": k,
            "hub_num": hub_num,
            "use_group": use_group,
            "results": results,
            "elapsed_seconds": elapsed,
            "console_output": "\n".join(captured_output),
            "progress": progress_log,
            "roi_list": load_roi_list(),
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


# @server.tool(name="get_aging_curve")
# def get_aging_curve(phenotype: str) -> dict:
#     """
#     Load large scale aging curve database for a given phenotype.
    
#     Available phenotypes:
#     - Global mean of FC
#     - Global system segregation
#     - Visual system segregation (VIS)
#     - Somatomotor system segregation (SM)
#     - Dorsal attention system segregation (DA)
#     - Ventral attention system segregation (VA)
#     - Limbic system segregation (LIM)
#     - Frontoparietal system segregation (FP)
#     - Default mode system segregation (DM)
#     """
#     start_time = time.time()
#     try:
#         logger.info(f"Loading growth curve for phenotype: {phenotype}")
#         data = load_curve_data(phenotype)
#         elapsed = time.time() - start_time
#         logger.info(f"Growth curve loaded in {elapsed:.2f}s")
        
#         return {
#             "status": "success",
#             "timestamp": datetime.now().isoformat(),
#             "phenotype": phenotype,
#             "data": data,
#             "elapsed_seconds": elapsed,
#         }
#     except KeyError as e:
#         logger.error(f"Phenotype not found: {phenotype}")
#         return {
#             "status": "error",
#             "timestamp": datetime.now().isoformat(),
#             "error_type": "KeyError",
#             "phenotype": phenotype,
#             "error": f"Phenotype not found: {phenotype}. Available: Global mean of FC, Visual system segregation (VIS), etc.",
#         }
#     except Exception as e:
#         logger.error(f"Error loading growth curve: {str(e)}", exc_info=True)
#         return {
#             "status": "error",
#             "timestamp": datetime.now().isoformat(),
#             "error_type": type(e).__name__,
#             "phenotype": phenotype,
#             "error": str(e),
#         }


@server.tool(name="overlay_with_aging_curve", description=f"""
To see the difference with normative model, overlay the uploaded data on top of aging curves for a specific phenotype.

Parameters:
- x_phenotype: Name of phenotype in the database to compare, select from {list_available_phenotypes()}
- y_path: Path to uploaded CSV file with overlay data
- age_col: Column name for age values in the CSV file
- val_col: Column name for overlay values in the CSV file

Returns: Combined x and y data for normative modeling
             """)
def overlay_with_aging_curve(
    x_phenotype: str,
    y_path: str,
    age_col: str,
    val_col: str,
) -> dict:
    f"""
    To see the difference with normative model, overlay the uploaded data on top of aging curves for a specific phenotype.
    
    Parameters:
    - x_phenotype: Name of phenotype in the database to compare, select from {list_available_phenotypes()}
    - y_path: Path to uploaded CSV file with overlay data
    - age_col: Column name for age values in the CSV file
    - val_col: Column name for overlay values in the CSV file
    
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
                "results": [ {pmid,title,journal,year,authors,abstract,url}, ... ],
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
            return {"results": []}
            # return {
            #     "status": "success",
            #     "timestamp": datetime.now().isoformat(),
            #     "elapsed_seconds": elapsed,
            #     "query_used": q,
            #     "count_returned": 0,
            #     "results": [],
            #     "suggested_keywords": [],
            #     "console_output": "",
            #     "progress": progress_log + [{"step": "done", "message": "No results found"}],
            # }

        progress_log.append({"step": "summarize", "message": f"Fetching summaries for {len(pmids)} PMIDs"})
        summary = _pubmed_esummary(pmids)

        progress_log.append({"step": "abstracts", "message": f"Fetching abstracts for {len(pmids)} PMIDs"})
        abstracts_by_pmid = _pubmed_efetch_abstracts(pmids)

        result_obj = summary.get("result", {})
        uids = result_obj.get("uids", []) or []

        rows: List[Dict[str, Any]] = []
        for uid in uids[:10]:
            item = result_obj.get(uid, {}) or {}
            title = (item.get("title") or "").strip()
            journal = (item.get("fulljournalname") or item.get("source") or "").strip()

            # pubdate can be like "2022 Jan 3" — we extract first YYYY
            year = _extract_year(item.get("pubdate", ""))

            # authors often a list of dicts with "name"
            authors_list = item.get("authors", []) or []
            authors = ", ".join([a.get("name", "").strip() for a in authors_list if a.get("name")])[:300]
            abstract = abstracts_by_pmid.get(str(uid), "")

            row = {
                "pmid": str(uid),
                "title": title,
                "journal": journal,
                "year": year,
                "authors": authors,
                "abstract": abstract,
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
            # "status": "success",
            # "timestamp": datetime.now().isoformat(),
            # "elapsed_seconds": elapsed,
            # "query_used": q,
            # "count_returned": len(rows),
            "results": rows,
            # "suggested_keywords": suggested_keywords,
            # "console_output": "\n".join(captured_output),
            # "progress": progress_log,
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

# @server.tool(name="openneuro_search")
# def openneuro_search(query: str, max_results: int = 10, modality: str | None = None) -> dict:
#     """
#     OpenNeuro keyword search via GraphQL.

#     Practical reality (as of your tests):
#     - OpenNeuro root field `search(q, ...)` exists but returns `null` for all queries, so we
#       always prefer `datasets(...)` listing + client-side scoring/filtering.
#     - `DatasetFilter` does not support keyword filtering.
#     - Dataset `name` alone is often not descriptive (e.g., ds000005), so we at least match on id+name.
#       (You can later expand to metadata/latestSnapshot once you introspect those subfields.)
#     """
#     progress_log: list[dict] = []
#     start_time = time.time()

#     try:
#         q = (query or "").strip()
#         if not q:
#             raise ValueError("query must be a non-empty string")

#         max_results = int(max_results)
#         if max_results < 1:
#             raise ValueError("max_results must be >= 1")

#         # Keep tokens short and safe; cap to avoid overly strict matching
#         tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-]{2,}", q)]
#         tokens = tokens[:8]

#         progress_log.append({"step": "search", "message": f"Searching OpenNeuro for: {q!r} (tokens={tokens})"})
#         if modality:
#             progress_log.append({"step": "filter", "message": f"Modality filter requested: {modality!r} (best-effort)"})

#         field_name, arg_name, arg_names, return_type_ref, available_fields = _openneuro_pick_dataset_field()
#         if not field_name:
#             raise ValueError(
#                 "OpenNeuro GraphQL schema did not expose a datasets/search field. "
#                 f"Available root fields: {available_fields}"
#             )

#         progress_log.append({"step": "schema", "message": f"Picked OpenNeuro field={field_name!r} arg={arg_name!r}"})

#         # IMPORTANT: OpenNeuro's `search()` resolver returns null in practice (verified).
#         # Force fallback to `datasets()` listing.
#         if field_name == "search":
#             progress_log.append({"step": "schema", "message": "OpenNeuro search() returns null; switching to datasets() listing"})
#             field_name = "datasets"
#             arg_name = None

#         # If server-side search arg exists, we'd use it directly; but we force datasets listing above.
#         fetch_limit = min(200, max_results * 50)  # over-fetch to make local scoring meaningful

#         raw_rows = _openneuro_try_queries(
#             field_name=field_name,
#             arg_name=arg_name,              # should be None after the override
#             arg_names=arg_names,
#             return_type_ref=return_type_ref,
#             query_text=q,
#             max_results=fetch_limit,
#             progress_log=progress_log,
#             modality=modality,
#         )

#         def haystack(row: Dict[str, Any]) -> str:
#             return " ".join([
#                 (row.get("dataset_id") or ""),
#                 (row.get("name") or ""),
#             ]).lower()

#         def score(row: Dict[str, Any]) -> int:
#             h = haystack(row)
#             # score by # matched tokens (ANY-token match, not ALL)
#             return sum(1 for t in tokens if t in h)

#         # Local ranking/filtering
#         if tokens:
#             # Keep only rows that match at least one token
#             filtered = [r for r in raw_rows if score(r) > 0]
#             # Sort by score descending, then by name to stabilize ordering
#             filtered.sort(key=lambda r: (score(r), (r.get("name") or "").lower()), reverse=True)
#         else:
#             filtered = list(raw_rows)

#         results: List[Dict[str, Any]] = filtered[:max_results]

#         elapsed = time.time() - start_time
#         progress_log.append({"step": "done", "message": f"Returning {len(results)} datasets"})

#         return {
#             "status": "success",
#             "timestamp": datetime.now().isoformat(),
#             "elapsed_seconds": elapsed,
#             "query_used": q,
#             "count_returned": len(results),
#             "results": results,
#             "console_output": "",
#             "progress": progress_log,
#         }

#     except Exception as e:
#         elapsed = time.time() - start_time
#         logger.error(f"OpenNeuro search error: {str(e)}", exc_info=True)
#         progress_log.append({"step": "error", "message": str(e)})
#         return {
#             "status": "error",
#             "timestamp": datetime.now().isoformat(),
#             "elapsed_seconds": elapsed,
#             "error_type": type(e).__name__,
#             "error": str(e),
#             "results": [],
#             "console_output": "",
#             "progress": progress_log,
#         }

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
                "description": """Run cross-frequency coupling (CFC) analysis using harmonic wavelets on brain functional connectivity data.
Computes sliding-window adjacency matrices and applies wavelet decomposition to extract CFC features.
Parameters:
- data_path: Path to input data. """,
                "parameters":  """Run cross-frequency coupling (CFC) analysis using harmonic wavelets on brain functional connectivity data.
Computes sliding-window adjacency matrices and applies wavelet decomposition to extract CFC features.
Parameters:
- data_path: Path to input data. """,
            },
            "run_hub_detection": {
                "method": "POST",
                "description": """Detect hub nodes in brain functional connectivity networks using graph embedding analysis.
Supports both single-subject and group-level Grassmann manifold methods.
Parameters:
- data_path: Path to input data.
- ratio: Edge weight threshold for binarizing adjacency matrix (default: 0.8, range: 0.0-1.0)
- k: Graph embedding dimension (default: 2, range: 1-100)
- hub_num: Number of hub nodes to identify (default: 10)
- use_group: Use group/Grassmann manifold method combining multiple networks (default: False)""",
                "parameters": """Detect hub nodes in brain functional connectivity networks using graph embedding analysis.
Supports both single-subject and group-level Grassmann manifold methods.
Parameters:
- data_path: Path to input data.
- ratio: Edge weight threshold for binarizing adjacency matrix (default: 0.8, range: 0.0-1.0)
- k: Graph embedding dimension (default: 2, range: 1-100)
- hub_num: Number of hub nodes to identify (default: 10)
- use_group: Use group/Grassmann manifold method combining multiple networks (default: False)""",
            },
            # "get_aging_curve": {
            #     "method": "POST",
            #     "description": "Load age-vs-phenotype data from the database of a large-scale lifespan cohort",
            #     "parameters": {
            #         "phenotype": {"type": "string", "description": "One phenotype name among all available phenotypes."}
            #     }
            # },
            "overlay_with_aging_curve": {
                "method": "POST",
                "description": f"""To see the difference with normative model, overlay the uploaded data on top of aging curves for a specific phenotype.
Parameters:
- x_phenotype: Name of phenotype in the database to compare, select from {list_available_phenotypes()}
- y_path: Path to uploaded CSV file with overlay data
- age_col: Column name for age values in the CSV file
- val_col: Column name for overlay values in the CSV file
Returns: Combined x and y data for normative modeling""",
                "parameters": f"""To see the difference with normative model, overlay the uploaded data on top of aging curves for a specific phenotype.
Parameters:
- x_phenotype: Name of phenotype in the database to compare, select from {list_available_phenotypes()}
- y_path: Path to uploaded CSV file with overlay data
- age_col: Column name for age values in the CSV file
- val_col: Column name for overlay values in the CSV file
Returns: Combined x and y data for normative modeling""",
            },
            "search_pubmed": {
                "method": "POST",
                "description": "Search PubMed via NCBI E-utilities (esearch + esummary)",
                "parameters": PubMedSearchRequest.model_json_schema(),
            },
            "inspect_civet_folder": {
                "method": "POST",
                "description": "Inspect a CIVET subject folder for common output groups.",
                "parameters": InspectCivetFolderRequest.model_json_schema(),
            },
            "run_civet_qc_check": {
                "method": "POST",
                "description": "Parse a CIVET QC table and flag common QC problems.",
                "parameters": RunCivetQcCheckRequest.model_json_schema(),
            },
            "load_cortical_thickness_map": {
                "method": "POST",
                "description": "Summarize a CIVET cortical thickness text file.",
                "parameters": LoadCorticalThicknessMapRequest.model_json_schema(),
            },
            "visualize_civet_surface": {
                "method": "POST",
                "description": "Generate an interactive Plotly HTML visualization for a CIVET OBJ surface.",
                "parameters": VisualizeCivetSurfaceRequest.model_json_schema(),
            },
            # "openalex_search": {
            #     "method": "POST",
            #     "description": "Scholarly discovery search via OpenAlex works",
            #     "parameters": OpenAlexSearchRequest.model_json_schema(),
            # },
            # "crossref_enrich": {
            #     "method": "POST",
            #     "description": "Enrich/normalize bibliographic metadata by DOI via Crossref",
            #     "parameters": CrossrefEnrichRequest.model_json_schema(),
            # },
            # "internet_search": {
            #     "method": "POST",
            #     "description": "Combined internet search (OpenAlex discovery + Crossref DOI enrichment)",
            #     "parameters": InternetSearchRequest.model_json_schema(),
            # },
        },
        "rate_limiting": {
            "requests_per_window": RATE_LIMIT_REQUESTS,
            "window_seconds": RATE_LIMIT_WINDOW,
        }
    }
    return JSONResponse(schema)


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

@server.custom_route("/inspect_civet_folder", methods=["POST"])
@rate_limit
async def http_inspect_civet_folder(request: Request) -> JSONResponse:
    """HTTP endpoint for CIVET folder inspection."""
    try:
        data = await request.json()
        validated_data = InspectCivetFolderRequest(**data)

        result = inspect_civet_folder(subject_dir=validated_data.subject_dir)
        return JSONResponse(result)
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@server.custom_route("/run_civet_qc_check", methods=["POST"])
@rate_limit
async def http_run_civet_qc_check(request: Request) -> JSONResponse:
    """HTTP endpoint for CIVET QC checks."""
    try:
        data = await request.json()
        validated_data = RunCivetQcCheckRequest(**data)

        result = run_civet_qc_check(
            qc_file=validated_data.qc_file,
            subject_id=validated_data.subject_id,
        )
        return JSONResponse(result)
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@server.custom_route("/load_cortical_thickness_map", methods=["POST"])
@rate_limit
async def http_load_cortical_thickness_map(request: Request) -> JSONResponse:
    """HTTP endpoint for CIVET cortical thickness summaries."""
    try:
        data = await request.json()
        validated_data = LoadCorticalThicknessMapRequest(**data)

        result = load_cortical_thickness_map(
            thickness_file=validated_data.thickness_file,
        )
        return JSONResponse(result)
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@server.custom_route("/visualize_civet_surface", methods=["POST"])
@rate_limit
async def http_visualize_civet_surface(request: Request) -> JSONResponse:
    """HTTP endpoint for CIVET surface visualization."""
    try:
        data = await request.json()
        validated_data = VisualizeCivetSurfaceRequest(**data)

        result = visualize_civet_surface(
            surface_path=validated_data.surface_path,
            overlay_path=validated_data.overlay_path,
            output_dir=validated_data.output_dir,
        )
        return JSONResponse(result)
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


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


# @server.custom_route("/get_aging_curve", methods=["POST"])
# @rate_limit
# async def http_get_aging_curve(request: Request) -> JSONResponse:
#     """HTTP endpoint for large scale aging curve database."""
#     try:
#         data = await request.json()
#         phenotype = data.get("phenotype", "Global mean of FC")
        
#         if not phenotype:
#             raise HTTPException(status_code=400, detail="phenotype parameter required")
        
#         result = get_aging_curve(phenotype=phenotype)
#         return JSONResponse(result)
#     except Exception as e:
#         logger.error(f"Request error: {str(e)}")
#         raise HTTPException(status_code=500, detail="Internal server error")


@server.custom_route("/overlay_with_aging_curve", methods=["POST"])
@rate_limit
async def http_overlay_with_aging_curve(request: Request) -> JSONResponse:
    """HTTP endpoint for normative analysis."""
    try:
        data = await request.json()
        # Validate using Pydantic model
        validated_data = NormativeAnalysisRequest(**data)
        
        result = overlay_with_aging_curve(
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

# @server.custom_route("/openalex_search", methods=["POST"])
# @rate_limit
# async def http_openalex_search(request: Request) -> JSONResponse:
#     data = await request.json()
#     v = OpenAlexSearchRequest(**data)
#     return JSONResponse(openalex_search(v.query, v.max_results, v.from_year, v.to_year))


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

import pandas as pd
import os

@server.tool(name="merge_datasets")
def merge_csv_datasets(file_paths: list[str], output_filename: str = "merged_dataset.csv") -> str:
    """
    Merges multiple CSV files. Dynamically finds a common ID column 
    to perform a full outer join. Otherwise, it stacks the datasets vertically.
    """
    if not file_paths:
        return "Error: No files provided."
    
    # Load all CSVs into DataFrames
    import pandas as pd
    import os
    dfs = [pd.read_csv(f) for f in file_paths]
    if len(dfs) == 1:
        return "Only one file provided. No merge needed."

    # Dynamically find columns that exist in ALL provided files
    common_cols = set(dfs[0].columns)
    for df in dfs[1:]:
        common_cols.intersection_update(df.columns)
    
    # Prioritize columns that look like IDs, otherwise use the first common column
    id_col = None
    if common_cols:
        # Check if any common column has 'id', 'case', 'subject', etc. in its name
        for col in common_cols:
            if any(keyword in col.lower() for keyword in ['id', 'case', 'subject', 'rid']):
                id_col = col
                break
        # If no obvious ID name is found, just use the first shared column we found
        if not id_col:
            id_col = list(common_cols)[0]

    # Merge or Concatenate
    if id_col:
        merged_df = dfs[0]
        for df in dfs[1:]:
            merged_df = pd.merge(merged_df, df, on=id_col, how='outer')
            
        # Move ID column to the front for readability
        cols = merged_df.columns.tolist()
        cols.insert(0, cols.pop(cols.index(id_col)))
        merged_df = merged_df[cols]
    else:
        # Absolute Fallback: Only stack if they literally share ZERO columns
        merged_df = pd.concat(dfs, ignore_index=True)

    # Cleanup: Fill missing values with empty strings
    merged_df = merged_df.fillna("")

    # Save to disk
    os.makedirs("uploaded_files", exist_ok=True)
    output_path = os.path.join("uploaded_files", output_filename)
    merged_df.to_csv(output_path, index=False)
    
    return f"Successfully merged {len(file_paths)} datasets into {output_filename}. Used ID column: {id_col if id_col else 'None (Stacked)'}"

# @server.tool(name="run_correlation")
# def run_correlation(data_source: str, var1: str, var2: str) -> str:
#     """
#     Calculates Pearson correlation between two variables (Linear Relationship).
#     Returns correlation coefficient, p-value, and significance.
#     """
#     result = StatsToolkit.correlation_analysis(data_source, var1, var2)
#     return json.dumps(result)

# @server.tool(name="run_group_comparison")
# def run_group_comparison(data_source: str, group_col: str, metric_col: str, group_a: str, group_b: str, method: str = "ttest") -> str:
#     """
#     Compares two groups. Returns p-value AND Cohen's d Effect Size.
#     Args:
#         method: 'ttest' (standard) or 'mannwhitney' (use if data is non-normal/skewed).
#     """
#     result = StatsToolkit.compare_groups(data_source, group_col, metric_col, group_a, group_b, method)
#     return json.dumps(result)

# @server.tool(name="apply_fdr_correction")
# def apply_fdr_correction(p_values: list[float]) -> str:
#     """
#     Applies False Discovery Rate (Benjamini-Hochberg) correction.
#     MANDATORY when testing multiple brain regions to prevent false positives.
#     """
#     result = StatsToolkit.correct_p_values(p_values)
#     return json.dumps(result)

# @server.tool(name="detect_outliers")
# def detect_outliers(data_source: str, column: str) -> str:
#     """
#     Scans a column for statistical outliers (Z-score > 3).
#     Use this to clean data before running T-tests.
#     """
#     result = StatsToolkit.detect_outliers_zscore(data_source, column)
#     return json.dumps(result)

@server.custom_route("/roi_figs/composite", methods=["GET"])
async def roi_composite(request: Request):
    ids_str = request.query_params.get("ids", "")
    roi_ids = [s.strip() for s in ids_str.split(",") if s.strip()]
    if not roi_ids:
        raise HTTPException(status_code=400, detail="ids required")
    try:
        png_bytes = composite_roi_images(roi_ids)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(png_bytes, media_type="image/png")


# @server.custom_route("/roi_figs/{path:path}", methods=["GET"])
# async def roi_figs(request: Request):
#     path = request.path_params["path"]
#     fp = os.path.join(_ROI_FIG_DIR, path)
#     if not os.path.isfile(fp):
#         raise HTTPException(status_code=404, detail="Image not found")
#     return FileResponse(fp)

# app = FastAPI()

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# import uvicorn

# app.mount("/", server)
# from fastmcp.utilities.lifespan import combine_lifespans
# from contextlib import asynccontextmanager

# # Your existing lifespan
# @asynccontextmanager
# async def app_lifespan(app: FastAPI):
#     print("Starting up the app...")
#     yield
#     print("Shutting down the app...")

# # Create MCP server
# mcp_app = server.http_app(path="/")

# # Combine both lifespans
# app = FastAPI(lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))
# app.mount("/mcp", mcp_app)  # MCP endpoint at /mcp
### 
# uvicorn mcp_server:http_app --port 8010
###
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# Define middleware
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]
http_app = server.http_app(middleware=middleware)
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
    logger.info("  POST /get_aging_curve           - large scale aging curve database")
    logger.info("  POST /overlay_with_aging_curve     - Normative analysis")
    logger.info("  POST /search_pubmed             - PubMed literature search")
    logger.info("  POST /upload                     - Upload file for analysis")
    logger.info("  GET  /list_files                 - List uploaded files")
    logger.info("  DELETE /delete_file              - Delete uploaded file")
    logger.info("="*60)
    
    try:
        # server.run(transport="http", host="0.0.0.0", port=8010)
        # server.run(transport="streamable-http", mount_path='/ram/USERS/ziquanw/brain-network-chart/uploaded_files')
        server.run(transport="sse", host="0.0.0.0", port=8010)
        # uvicorn.run(
        #     app,
        #     host="127.0.0.1",
        #     port=8010,
        # )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {str(e)}", exc_info=True)
    finally:
        logger.info("Server stopped")
