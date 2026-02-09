from __future__ import annotations

from typing import Any, Dict, Optional, List
import json

from .mcp_client import MCPClient


async def run_stats(
    client: MCPClient,
    stats_request: Dict[str, Any],
    table: Optional[list[dict[str, Any]]] = None,
    csv_text: Optional[str] = None,
) -> Dict[str, Any]:
    endpoint = client.get_stats_endpoint()

    # If endpoint expects run_correlation, adapt payload to its expected shape
    if endpoint and "run_correlation" in endpoint:
        # prefer var1/var2 from stats_request if present
        var1 = stats_request.get("var1") if isinstance(stats_request, dict) else None
        var2 = stats_request.get("var2") if isinstance(stats_request, dict) else None

        # helper to detect numeric columns from table
        def find_numeric_columns(rows: List[Dict[str, Any]]) -> List[str]:
            if not rows:
                return []
            keys = list(rows[0].keys())
            numeric_keys: List[str] = []
            for k in keys:
                all_numeric = True
                for r in rows:
                    v = r.get(k)
                    if v is None:
                        all_numeric = False
                        break
                    if not isinstance(v, (int, float)):
                        all_numeric = False
                        break
                if all_numeric:
                    numeric_keys.append(k)
            return numeric_keys

        if (not var1 or not var2) and table is not None:
            numeric_cols = find_numeric_columns(table)
            if len(numeric_cols) >= 2:
                if not var1:
                    var1 = numeric_cols[0]
                if not var2:
                    var2 = numeric_cols[1]

        payload: Dict[str, Any] = {
            "data_source": json.dumps(table) if table is not None else (csv_text or "[]")
        }
        if var1:
            payload["var1"] = var1
        if var2:
            payload["var2"] = var2

        return await client.call(endpoint, payload)

    # Default behaviour: send stats_request and table/csv_text as before
    payload: Dict[str, Any] = {"request": stats_request}
    if table is not None:
        payload["table"] = table
    if csv_text is not None:
        payload["csv_text"] = csv_text
    return await client.call(endpoint, payload)
