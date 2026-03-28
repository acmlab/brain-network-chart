# Brain Network Analysis Server

A Model Context Protocol (MCP) server for brain network analysis using advanced signal processing and graph-based hub detection. Includes tools for cross-frequency coupling (CFC) analysis, hub detection in single and multiple networks, and normative developmental trajectory analysis.

## Installation

### Requirements
- Python 3.11+
- Dependencies listed in `pyproject.toml`

### Setup

```bash
# Clone repository
git clone <repository-url>
cd brain-network-chart
uv sync
uvicorn mcp_server:http_app --host 0.0.0.0 --port 8004
cd frontend
npm install
npm run dev
```
