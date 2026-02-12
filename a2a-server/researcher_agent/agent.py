from __future__ import annotations

import inspect
import json
import os
from typing import Any, Dict, List, Optional

import httpx

from .formatters import base_result, extract_items, format_summary_lines, normalize_citations
from .mcp_client import MCPClient
from .policy import (
    build_config_update_suggestion,
    build_pubmed_query,
    build_stats_recommendation,
    build_stats_request,
    expand_query,
    infer_outcome_type,
    safe_json_loads,
)
from .schemas import AgentRequest, AgentResponse, Intent
from .tools_duckduck import search_duckduck
from .tools_pubmed import search_pubmed
from .tools_stats import run_stats
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm


OLLAMA_API_BASE = os.environ.get("OLLAMA_API_BASE", "http://yukon.acm.unc.edu:11434")
HOST_MODEL = os.environ.get("HOST_MODEL", "ollama_chat/qwen3:latest")
os.environ.setdefault("OLLAMA_API_BASE", OLLAMA_API_BASE)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class AdkLlmClient:
    def __init__(self, model: LiteLlm) -> None:
        self.model = model

    async def aclose(self) -> None:
        return None

    async def generate(self, prompt: str) -> str:
        if hasattr(self.model, "generate"):
            result = await _maybe_await(self.model.generate(prompt))
        else:
            result = await _maybe_await(self.model.invoke(prompt))

        if isinstance(result, str):
            return result.strip()
        if isinstance(result, dict):
            text_value = result.get("text") or result.get("content")
            if text_value is not None:
                return str(text_value).strip()
        if hasattr(result, "text"):
            return str(result.text).strip()
        return str(result).strip()


class AgentResources:
    def __init__(self) -> None:
        self.mcp_client: Optional[MCPClient] = None
        self.llm_client: Optional[AdkLlmClient] = None

    async def init(self) -> "AgentResources":
        if self.mcp_client is None:
            self.mcp_client = await MCPClient.create()
        if self.llm_client is None:
            self.llm_client = AdkLlmClient(LiteLlm(model=HOST_MODEL))
        return self

    async def aclose(self) -> None:
        if self.mcp_client is not None:
            await self.mcp_client.aclose()
        if self.llm_client is not None:
            await self.llm_client.aclose()


_RESOURCES = AgentResources()


def _parse_request(data: Dict[str, Any]) -> AgentRequest:
    if hasattr(AgentRequest, "model_validate"):
        return AgentRequest.model_validate(data)
    return AgentRequest.parse_obj(data)


def _dump_response(response: AgentResponse) -> Dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    return response.dict()


def _dump_request(request: AgentRequest) -> Dict[str, Any]:
    if hasattr(request, "model_dump"):
        return request.model_dump()
    return request.dict()


async def act(request: AgentRequest) -> AgentResponse:
    logs: List[str] = []
    payload = request.payload or {}
    result = base_result()

    await _RESOURCES.init()
    if _RESOURCES.mcp_client is None or _RESOURCES.llm_client is None:
        raise RuntimeError("ADK agent resources not initialized")

    try:
        if request.intent == Intent.KEYWORDS:
            keywords = await handle_keywords(payload, _RESOURCES.llm_client, logs)
            result["keywords"] = keywords
            result["confidence"] = 0.6

        elif request.intent == Intent.EVIDENCE:
            evidence_result = await handle_evidence(
                payload, _RESOURCES.mcp_client, _RESOURCES.llm_client, logs
            )
            result.update(evidence_result)
            result["confidence"] = 0.7

        elif request.intent == Intent.STATS:
            stats_result = await handle_stats(payload, _RESOURCES.mcp_client, logs)
            result.update(stats_result)
            result["confidence"] = 0.65

        elif request.intent == Intent.CONFIG_CHECK:
            config_result = handle_config_check(payload, logs)
            result.update(config_result)
            result["confidence"] = 0.55

        else:
            raise ValueError(f"Unsupported intent: {request.intent}")

        if payload.get("request_forwarding") is True:
            forwarding = await forward_to_agents(request, logs)
            result["forwarding"] = forwarding

        return AgentResponse(task_id=request.task_id, status="ok", result=result, logs=logs)
    except Exception as exc:
        logs.append(f"error: {exc}")
        return AgentResponse(
            task_id=request.task_id,
            status="error",
            result=result,
            logs=logs,
        )


async def handle_keywords(
    payload: Dict[str, Any], llm_client: AdkLlmClient, logs: List[str]
) -> List[str]:
    text = (
        payload.get("text")
        or payload.get("query")
        or payload.get("question")
        or json.dumps(payload)
    )
    prompt = (
        "Extract 5-10 concise keywords from the input. "
        "Return ONLY valid JSON: {\"keywords\": [\"k1\", \"k2\", ...]}.\n\n"
        f"Input:\n{text}"
    )
    response = await llm_client.generate(prompt)
    data = safe_json_loads(response)
    keywords = data.get("keywords", [])
    keywords = [str(k).strip() for k in keywords if str(k).strip()]
    logs.append(f"keywords_count={len(keywords)}")
    return keywords


async def handle_evidence(
    payload: Dict[str, Any],
    mcp_client: MCPClient,
    llm_client: AdkLlmClient,
    logs: List[str],
) -> Dict[str, Any]:
    query = build_pubmed_query(payload)
    top_k = int(payload.get("top_k") or 8)
    pubmed_raw = await search_pubmed(mcp_client, query=query, top_k=top_k)
    pubmed_items = extract_items(pubmed_raw)
    logs.append(f"pubmed_results={len(pubmed_items)}")

    duck_raw = None
    if len(pubmed_items) < 3:
        duck_query = expand_query(query)
        duck_raw = await search_duckduck(mcp_client, query=duck_query, top_k=6)
        logs.append("duckduck_called=true")

    citations = normalize_citations(pubmed_raw, duck_raw)
    summary = await summarize_citations(citations, llm_client, logs)

    return {
        "literature_summary": summary,
        "citations": citations,
    }


async def summarize_citations(
    citations: List[Dict[str, Any]], llm_client: AdkLlmClient, logs: List[str]
) -> List[str]:
    if not citations:
        return []
    formatted = []
    for item in citations[:12]:
        title = item.get("title", "")
        year = item.get("year", "")
        journal = item.get("journal", "")
        formatted.append(f"- {title} ({year}) {journal}".strip())

    prompt = (
        "Summarize the citation list into 3-6 bullet points. "
        "Return ONLY valid JSON: {\"literature_summary\": [\"point1\", ...]}.\n\n"
        "Citations:\n" + "\n".join(formatted)
    )
    response = await llm_client.generate(prompt)
    data = safe_json_loads(response)
    summary = data.get("literature_summary", [])
    summary = [str(item).strip() for item in summary if str(item).strip()]
    logs.append(f"summary_count={len(summary)}")
    return summary or format_summary_lines("\n".join(formatted[:6]))


async def handle_stats(
    payload: Dict[str, Any], mcp_client: MCPClient, logs: List[str]
) -> Dict[str, Any]:
    table = payload.get("table")
    csv_text = payload.get("csv_text")
    outcome_column = payload.get("outcome_column")
    if table is None and csv_text is None:
        raise ValueError("STATS intent requires payload.table or payload.csv_text")

    outcome_type = infer_outcome_type(table, outcome_column)
    stats_request = build_stats_request(outcome_type)
    stats_output: Dict[str, Any] = {}
    if os.getenv("MCP_STATS_ENDPOINT"):
        stats_output = await run_stats(
            mcp_client, stats_request=stats_request, table=table, csv_text=csv_text
        )
        logs.append("stats_called=true")
    else:
        logs.append("stats_skipped=true")

    stats_tool_results = {}
    if isinstance(stats_output, dict):
        stats_tool_results = stats_output.get("tool_results", {})

    return {
        "stats_recommendation": build_stats_recommendation(outcome_type),
        "stats_output": stats_output,
        "stats_tool_results": stats_tool_results,
    }


def handle_config_check(payload: Dict[str, Any], logs: List[str]) -> Dict[str, Any]:
    evidence_summary = payload.get("literature_summary")
    stats_summary = payload.get("stats_recommendation")
    config_update = build_config_update_suggestion(payload, evidence_summary, stats_summary)
    logs.append(f"config_updates={len(config_update.get('updates', []))}")
    return {"config_update_suggestion": config_update}


async def forward_to_agents(request: AgentRequest, logs: List[str]) -> Dict[str, Any]:
    targets = request.payload.get("forward_to") or []
    if not isinstance(targets, list):
        targets = []

    endpoints = {
        "planner": "http://localhost:8011/a2a/act",
        "executor": "http://localhost:8012/a2a/act",
        "validator": "http://localhost:8014/a2a/act",
    }
    results: Dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
        for target in targets:
            url = endpoints.get(str(target))
            if not url:
                continue
            response = await client.post(url, json=_dump_request(request))
            results[str(target)] = response.json()

    logs.append(f"forwarded={len(results)}")
    return results


async def a2a_act(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle A2A payloads for keywords, evidence, stats, and config_check.

    Args:
        request (Dict[str, Any]): A2A request with task_id, intent, sender, and payload.

    Returns:
        Dict[str, Any]: A2A-compatible response with status, result, and logs.
    """
    parsed = _parse_request(request)
    response = await act(parsed)
    return _dump_response(response)


root_agent = LlmAgent(
    model=LiteLlm(model=HOST_MODEL),
    name="researcher_agent",
    description="ADK agent wrapper for the A2A researcher endpoint",
    tools=[a2a_act],
)
