# Researcher Agent (TxGemma)

Production-ready A2A server for evidence search and statistics on `localhost:8013`.

## Setup

```bash
pip install -r requirements.txt
```

Environment variables (optional):
- `OLLAMA_BASE_URL` (default `http://yukon.acm.unc.edu:11434`)
- `OLLAMA_MODEL` (default `Huzderu/txgemma-27B-chat-Q8_0_GGUF:latest`)
- `OLLAMA_TIMEOUT_SECONDS` (default `120`)
- `MCP_BASE_URL` (default `http://yukon.acm.unc.edu:8010`)
- `MCP_PUBMED_ENDPOINT` (fallback if schema discovery fails)
- `MCP_DUCKDUCK_ENDPOINT`
- `MCP_STATS_ENDPOINT`

## Run

```bash
./scripts/run_researcher.sh
```

## Test

```bash
./scripts/test_researcher.sh
```

## API

- `GET /health` -> `{ "status": "ok" }`
- `POST /a2a/act` -> A2A compatible request/response

## Stats MCP Notes

### Behavior with MCP Endpoints

- **MCP_STATS_ENDPOINT with run_correlation**: 
  When `MCP_STATS_ENDPOINT` points to an endpoint containing `run_correlation`, the stats payload is adapted to:
  ```json
  {
    "data_source": "<json string of table>",
    "var1": "<first numeric column>",
    "var2": "<second numeric column>"
  }
  ```
  Numeric variables are auto-detected from the table if not explicitly specified.

- **MCP_STATS_ENDPOINT not set**:
  When `MCP_STATS_ENDPOINT` is unset, `run_stats` is skipped (no error), and logs record `stats_skipped=true`.
  The response still includes `stats_recommendation` and `stats_tool_results`.

- **Response Structure**:
  - `stats_output`: Result from MCP endpoint (if called), or empty dict if skipped
  - `stats_tool_results`: Tool-specific results extracted from MCP response
  - `stats_recommendation`: Recommendation based on outcome type (always present)

