import contextlib
import logging
import json
import base64
from collections.abc import AsyncIterator
from typing import Any

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

# Import existing analysis functions and helpers from the original MCP server
from mcp_server import (
    run_cfc_wavelet_analysis,
    run_hub_detection,
    get_growth_curve,
    run_normative_analysis,
    save_uploaded_file,
    list_uploaded_files,
    delete_uploaded_file,
)

logger = logging.getLogger(__name__)


def create_mcp_server():
    """Create and configure the MCP server using ADK Server abstraction."""
    app = Server("adk-mcp-streamable-server")

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.ContentBlock]:
        """Handle tool calls from MCP clients by delegating to existing functions.

        All results are returned as a single TextContent block containing JSON.
        """
        try:
            if name == "run_cfc_wavelet_analysis":
                # Map arguments and call the blocking function in a thread
                params = {
                    k: arguments[k]
                    for k in (
                        "data_path",
                        "window_size",
                        "step_size",
                        "padding",
                        "ratio",
                        "wavelets_num",
                        "beta",
                        "gamma",
                        "max_iter",
                        "node_select",
                    )
                    if k in arguments
                }
                result = await anyio.to_thread.run_sync(lambda: run_cfc_wavelet_analysis(**params))
                return [types.TextContent(type="text", text=json.dumps(result))]

            if name == "run_hub_detection":
                params = {
                    k: arguments[k]
                    for k in (
                        "data_path",
                        "window_size",
                        "step_size",
                        "padding",
                        "ratio",
                        "k",
                        "hub_num",
                        "use_group",
                    )
                    if k in arguments
                }
                result = await anyio.to_thread.run_sync(lambda: run_hub_detection(**params))
                return [types.TextContent(type="text", text=json.dumps(result))]

            if name == "get_growth_curve":
                phenotype = arguments.get("phenotype", "Global mean of FC")
                result = await anyio.to_thread.run_sync(lambda: get_growth_curve(phenotype))
                return [types.TextContent(type="text", text=json.dumps(result))]

            if name == "run_normative_analysis":
                params = {
                    k: arguments[k]
                    for k in ("x_phenotype", "y_path", "age_col", "val_col")
                    if k in arguments
                }
                result = await anyio.to_thread.run_sync(lambda: run_normative_analysis(**params))
                return [types.TextContent(type="text", text=json.dumps(result))]

            if name == "upload_file":
                # Expect `filename` and base64-encoded `content` in arguments
                filename = arguments.get("filename")
                content_b64 = arguments.get("content")
                if not filename or not content_b64:
                    raise ValueError("upload_file requires 'filename' and base64 'content'")
                file_bytes = base64.b64decode(content_b64)
                # save_uploaded_file returns (file_path, file_info)
                result = await anyio.to_thread.run_sync(lambda: save_uploaded_file(file_bytes, filename))
                return [types.TextContent(type="text", text=json.dumps({"file_info": result[1]}))]

            if name == "list_files":
                result = await anyio.to_thread.run_sync(lambda: list_uploaded_files())
                return [types.TextContent(type="text", text=json.dumps({"files": result}))]

            if name == "delete_file":
                filename = arguments.get("filename")
                if not filename:
                    raise ValueError("delete_file requires 'filename'")
                result = await anyio.to_thread.run_sync(lambda: delete_uploaded_file(filename))
                return [types.TextContent(type="text", text=json.dumps({"result": result}))]

            if name == "health":
                return [types.TextContent(type="text", text=json.dumps({"status": "healthy"}))]

            if name == "api_schema":
                # Provide a lightweight schema description
                schema = {
                    "title": "Brain Network Analysis ADK API",
                    "tools": [t.name for t in await list_tools()],
                }
                return [types.TextContent(type="text", text=json.dumps(schema))]

            raise ValueError(f"Unknown tool: {name}")

        except Exception as e:
            logger.exception("Error in call_tool")
            # Return an error payload
            return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        """Return tool metadata for clients to discover available tools."""
        tools: list[types.Tool] = [
            types.Tool(
                name="run_cfc_wavelet_analysis",
                description="Run cross-frequency coupling wavelet analysis",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "data_path": {"type": "string"},
                        "window_size": {"type": "integer"},
                        "step_size": {"type": "integer"},
                        "padding": {"type": "boolean"},
                        "ratio": {"type": "number"},
                        "wavelets_num": {"type": "integer"},
                        "beta": {"type": "number"},
                        "gamma": {"type": "number"},
                        "max_iter": {"type": "integer"},
                        "node_select": {"type": "integer"},
                    },
                },
            ),
            types.Tool(
                name="run_hub_detection",
                description="Detect hub nodes in brain networks",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "data_path": {"type": "string"},
                        "window_size": {"type": "integer"},
                        "step_size": {"type": "integer"},
                        "padding": {"type": "boolean"},
                        "ratio": {"type": "number"},
                        "k": {"type": "integer"},
                        "hub_num": {"type": "integer"},
                        "use_group": {"type": "boolean"},
                    },
                },
            ),
            types.Tool(
                name="get_growth_curve",
                description="Load growth curve data for a phenotype",
                inputSchema={
                    "type": "object",
                    "properties": {"phenotype": {"type": "string"}},
                    "required": ["phenotype"],
                },
            ),
            types.Tool(
                name="run_normative_analysis",
                description="Run normative developmental trajectory analysis",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "x_phenotype": {"type": "string"},
                        "y_path": {"type": "string"},
                        "age_col": {"type": "string"},
                        "val_col": {"type": "string"},
                    },
                    "required": ["x_phenotype", "y_path", "age_col", "val_col"],
                },
            ),
            types.Tool(
                name="upload_file",
                description="Upload a file (base64 content + filename)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"},
                        "content": {"type": "string", "description": "Base64-encoded file contents"},
                    },
                    "required": ["filename", "content"],
                },
            ),
            types.Tool(
                name="list_files",
                description="List uploaded files",
                inputSchema={"type": "object"},
            ),
            types.Tool(
                name="delete_file",
                description="Delete an uploaded file",
                inputSchema={
                    "type": "object",
                    "properties": {"filename": {"type": "string"}},
                    "required": ["filename"],
                },
            ),
            types.Tool(
                name="health",
                description="Health check",
                inputSchema={"type": "object"},
            ),
            types.Tool(
                name="api_schema",
                description="API schema discovery",
                inputSchema={"type": "object"},
            ),
        ]
        return tools

    return app


def main(port: int = 8080, json_response: bool = False):
    """Main server function to run the ADK-style streamable HTTP server."""
    logging.basicConfig(level=logging.INFO)

    app = create_mcp_server()

    session_manager = StreamableHTTPSessionManager(
        app=app,
        event_store=None,
        json_response=json_response,
        stateless=True,
    )

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(starlette_app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            logger.info("MCP Streamable HTTP server started!")
            try:
                yield
            finally:
                logger.info("MCP server shutting down...")

    starlette_app = Starlette(
        debug=False,
        routes=[
            Mount("/mcp", app=handle_streamable_http),
        ],
        lifespan=lifespan,
    )

    import uvicorn
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    import sys
    main(port=int(sys.argv[1]) if len(sys.argv) > 1 else 8010)
