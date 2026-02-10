Run commands in three terminals:

Terminal 1: $env:OLLAMA_API_BASE="http://localhost:12345"; python main.py 

Terminal 2: node frontend/copilot-server.mjs 

Terminal 3: cd frontend && npm run dev

Additionally, you need to maintain the SSH tunnel:

Bash
ssh -L 12345:yukon.acm.unc.edu:11434 YourOnyen@raptor.acm.unc.edu