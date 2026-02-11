# Frontend CopilotKit Integration Setup

This document describes how to run the Brain Suite frontend with CopilotKit integration for AI-powered chat features.

## Architecture Overview

```
Vite Frontend (port 3000)
    ↓
CopilotKit Runtime (port 4000)
    ↓
ADK Backend (port 8022)
    ↓
Ollama LLM (via SSH tunnel to yukon.acm.unc.edu:11434)
```

## Prerequisites

### Required Software
- **Node.js** 20+
- **Python** 3.13
- **Conda** (for Python environment management)
- **SSH access** to `raptor.acm.unc.edu` (for Ollama connection)

### Network Requirements
- Campus VPN or on-campus network access for SSH tunnel to work

## Installation

### 1. Backend Setup

#### Create Conda Environment
```bash
conda create -n adk-backend python=3.13
conda activate adk-backend
```

#### Install Python Dependencies
```bash
pip install ag-ui-adk google-adk uvicorn fastapi a2a-sdk
pip install "google-adk[extensions]"
```

### 2. Frontend Setup

#### Install Node Dependencies
```bash
cd frontend
npm install
```

**Required packages:**
- `@copilotkit/react-ui`
- `@copilotkit/react-core`
- `@copilotkit/runtime`
- `@ag-ui/client`

These should already be in `package.json` if you pulled the latest code.

## Running the Application

You need **4 separate terminals** running simultaneously:

### Terminal 1: SSH Tunnel (for Ollama access)
```bash
ssh -L 12345:yukon.acm.unc.edu:11434 YOUR_ONYEN@raptor.acm.unc.edu
```

Keep this terminal open. This creates a tunnel that maps the remote Ollama server to `localhost:12345`.

### Terminal 2: ADK Backend
```bash
conda activate adk-backend
$env:OLLAMA_API_BASE = "http://localhost:12345"  # Windows PowerShell
# export OLLAMA_API_BASE="http://localhost:12345"  # macOS/Linux
python main.py
```

The backend will start on `http://localhost:8022`.

### Terminal 3: CopilotKit Runtime
```bash
node frontend/copilot-server.mjs
```

The runtime will start on `http://localhost:4000/copilotkit`.

### Terminal 4: Frontend Dev Server
```bash
cd frontend
npm run dev
```

The frontend will be available at `http://localhost:3000`.

## Verification

1. Open `http://localhost:3000` in your browser
2. Click the **AI Assistant** button in the top-right corner
3. Type a message (e.g., "hello") and press Enter
4. You should see a response from the AI agent

## Troubleshooting

### Port Already in Use
If you see errors about ports being in use, make sure no other instances are running:
- Backend: port 8022
- Runtime: port 4000
- Frontend: port 3000

### SSH Tunnel Connection Issues
**Symptom:** Backend shows `Cannot connect to host yukon.acm.unc.edu:11434`

**Solution:** Make sure Terminal 1 (SSH tunnel) is still running and connected. You may need to:
- Connect to campus VPN
- Re-establish the SSH connection if it timed out

### CORS Errors
**Symptom:** Browser console shows CORS errors

**Solution:** Check that `copilot-server.mjs` has the correct origin:
```javascript
res.setHeader("Access-Control-Allow-Origin", "http://localhost:3000");
```

### Empty Chat Messages
**Symptom:** Messages send but don't appear in chat

**Solution:** This was an issue with older hook usage. Current code uses `useAgent` from `@copilotkit/react-core/v2`, which should work correctly.

## Key Files

### Backend
- `main.py` - FastAPI server that exposes `root_agent` via AG-UI
- `brain_network_chart/agent.py` - Defines `root_agent` and sub-agents

### Frontend
- `frontend/copilot-server.mjs` - Standalone Node.js server running CopilotKit Runtime
- `frontend/src/main.jsx` - Wraps app with `CopilotKit` provider
- `frontend/src/App_test1.jsx` - Main app component, uses `useAgent` hook for chat
- `frontend/vite.config.js` - Vite config with CORS and file access settings

## Implementation Details

### Chat Integration
The chat feature is implemented in `UnifiedBrainApp` component using:

```jsx
import { useAgent } from '@copilotkit/react-core/v2'

const { agent } = useAgent({ agentId: 'root_agent' });
const chatMessages = agent?.messages ?? [];
const isProcessing = agent?.isRunning ?? false;

const handleSendChat = async () => {
  agent.addMessage({ id: crypto.randomUUID(), role: 'user', content });
  await agent.runAgent();
};
```

### Why CopilotKit Runtime?
Since the frontend uses Vite (not Next.js), we can't use Next.js API Routes. Instead, `copilot-server.mjs` runs a standalone Node.js HTTP server that:
1. Receives requests from the React frontend
2. Forwards them to the ADK backend via AG-UI protocol
3. Streams responses back to the frontend

## Development Notes

- The current setup uses Ollama's `qwen3:latest` model
- Agent configuration is in `brain_network_chart/agent.py`
- To change the model, modify the `HOST_MODEL` variable in `agent.py`

## Production Considerations

For production deployment:
1. Replace SSH tunnel with direct Ollama access or use a different LLM provider
2. Set proper CORS origins in `copilot-server.mjs`
3. Use environment variables for all configuration
4. Consider using a process manager (PM2, systemd) for the Runtime server
5. Set up proper logging and monitoring
