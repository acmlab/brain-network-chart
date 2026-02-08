# Validator Agent Documentation

## Overview
The **Validator Agent** acts as a Research Supervisor in the multi-agent system. Its primary role is to verify the outputs of the Researcher Agent before they are finalized. It performs a hybrid validation check:
1.  **Statistical Logic:** Ensures p-values, degrees of freedom, and sample sizes are consistent and methodology is appropriate.
2.  **Scientific Fact-Checking:** Cross-references claims against live PubMed literature to detect hallucinations or contradictions with established science.

## Technical Architecture & SDKs
* **Model:** TxGemma-27B (via Ollama)
    * *Note: Requires SSH tunnel to university server if running locally.*
* **Server Framework:** FastAPI / Uvicorn
* **Data Validation:** Pydantic
* **External Integration:** Connects to `mcp_server.py` for PubMed search tools.
* **Key Libraries:** `fastapi`, `uvicorn`, `pydantic`, `requests`, `ollama`

## Logic Flow
1.  **Input Parsing:** Receives a research claim, the original query, and the tool used from the Researcher Agent.
2.  **Context Retrieval (RAG):**
    * The agent dynamically imports the `search_pubmed` tool from the main MCP server.
    * It executes a live search using the `original_query` to gather relevant abstracts.
3.  **LLM Evaluation:**
    * Constructs a structured prompt containing the claim, the statistical results, and the retrieved literature context.
    * Instructs the TxGemma-27B model to verify if the logic holds (e.g., "is p=0.03 actually significant?") and if the result aligns with the provided literature.
4.  **Structured Output:** Returns a JSON verdict including a validity boolean, a confidence score (1-10), and specific feedback.

## API Reference

### Endpoint
`POST http://localhost:8014/validate`

### Request Format
The Researcher Agent should send the following JSON payload:

```json
{
  "original_query": "Does stress affect brain network hubs?",
  "analysis_result": "Stress significantly reduced hub connectivity (p=0.03).",
  "tool_used": "run_group_comparison"
}