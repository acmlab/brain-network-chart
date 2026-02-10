# def main():
#     print("Hello from backend!")


# if __name__ == "__main__":
#     main()

from fastapi import FastAPI
from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint
from brain_network_chart.agent import root_agent
import uvicorn

adk_agent = ADKAgent(
    adk_agent=root_agent,
    app_name="brain_network_chart",
    user_id="demo_user",
    session_timeout_seconds=3600,
    use_in_memory_services=True
)

app = FastAPI()
add_adk_fastapi_endpoint(app, adk_agent, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8022)