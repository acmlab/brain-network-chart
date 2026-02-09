import asyncio
import httpx
from a2a.client import A2AClient
from a2a.types import SendMessageRequest, MessageSendParams, TextPart
import uuid
from pprint import pprint

async def main():
    # Define the payload with a user message
    send_message_payload = {
        'message': {
            'role': 'user',
            'parts': [{'type': 'text', 'text': 'Hello, what is the capital of France?'}],
            'messageId': uuid.uuid4().hex,
        }
    }

    # Use an async httpx client for communication
    async with httpx.AsyncClient() as httpx_client:
        try:
            # Get the A2A client instance from the agent's URL
            client = await A2AClient.get_client_from_agent_card_url(
                httpx_client,
                'http://localhost:8011' # Replace with your A2A server URL
            )
            
            # Create the request object using Pydantic models
            request = SendMessageRequest(
                params=MessageSendParams(**send_message_payload)
            )

            # Send the message and get the response
            response = await client.send_message(request)
            
            print("Received response:")
            pprint(response.model_dump_json(indent=2))

        except httpx.RequestError as e:
            print(f"Connection error: {e}. Make sure the A2A server is running.")
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Run the asynchronous main function
    asyncio.run(main())
