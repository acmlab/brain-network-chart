import { createServer } from "node:http";
import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNodeHttpEndpoint,
} from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";

const serviceAdapter = new ExperimentalEmptyAdapter();

const runtime = new CopilotRuntime({
  agents: {
    root_agent: new HttpAgent({
      url: "http://localhost:8022/",
    }),
  },
});

const server = createServer((req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "http://localhost:3000");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "*");

  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.url === "/copilotkit" || req.url.startsWith("/copilotkit/")) {
    const handler = copilotRuntimeNodeHttpEndpoint({
      endpoint: "/copilotkit",
      runtime,
      serviceAdapter,
    });
    return handler(req, res);
  }

  res.writeHead(404);
  res.end("Not found");
});

server.listen(4000, () => {
  console.log("CopilotKit Runtime running at http://localhost:4000/copilotkit");
});