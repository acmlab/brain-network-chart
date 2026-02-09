# Executor Agent

The Executor Agent serves as the primary processing engine for the `brain-network-chart` pipeline. It orchestrates medical tool calls through an MCP server and utilizes **MedGemma 1.5 4B** for clinical reasoning and data synthesis.

## Technical Overview
* **Model:** MedGemma 1.5 4B via Ollama.
* **Stability Fixes:** Implemented an aggressive **1.6 repetition penalty** and a "primed" prompt structure to prevent the 4B model from entering infinite loops.
* **Error Handling:** Integrated guard clauses that validate tool output before summarization to prevent hallucinations on empty search results.

## Integration & Network
The agent is configured to operate within a multi-agent A2A (Agent-to-Agent) ecosystem.
* **Local Port:** `8012`
* **Peer Handshakes:**
    * **Researcher Agent:** Expected on port `8013`
    * **Validator Agent:** Expected on port `8014`


## API Endpoints

### 1. Standard Research Execution
**`POST /execute_research`**
* **Purpose:** Triggers the full research and execution pipeline for a given query.
* **Format:** Standard REST.

### 2. A2A Invoke (JSON-RPC)
**`POST /a2a/invoke`**
* **Purpose:** Handles inter-agent communication and task delegation.
* **Protocol:** JSON-RPC 2.0 compliant.
* **Example Body:**
  ```json
  {
    "jsonrpc": "2.0",
    "method": "analyze_traits",
    "params": {"query": "patient neuro-sensitivity"},
    "id": 1
  }