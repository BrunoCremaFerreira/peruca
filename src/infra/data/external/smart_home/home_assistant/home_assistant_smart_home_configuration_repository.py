import asyncio
import json
from typing import List, Any
import websockets

from typing import List
from domain.interfaces.smart_home_repository import SmartHomeConfigurationRepository

class HomeAssistantSmartHomeConfigurationRepository(SmartHomeConfigurationRepository):
    """
    Implementation of SmartHomeConfigurationRepository using Home Assistant WebSocket API.
    """

    def __init__(self, websocket_url: str, token: str):
        """
        :param websocket_url: Home Assistant WebSocket URL (e.g., ws://localhost:8123/api/websocket)
        :param token: Long-Lived Access Token for authentication
        """
        self.websocket_url = websocket_url
        self.token = token
        self._message_id = 1
        self._ws = None

    async def _connect(self):
        """Establish a WebSocket connection and authenticate."""
        self._ws = await websockets.connect(self.websocket_url)
        await self._authenticate()

    async def _authenticate(self):
        """Authenticate with the provided Long-Lived Access Token."""
        auth_message = {
            "type": "auth",
            "access_token": self.token,
        }
        await self._ws.send(json.dumps(auth_message))
        response = await self._ws.recv()
        resp = json.loads(response)
        if resp.get("type") == "auth_invalid":
            raise Exception(f"Authentication failed: {resp.get('message')}")
        elif resp.get("type") != "auth_ok":
            raise Exception(f"Unexpected authentication response: {resp}")

    async def _send(self, message: dict) -> Any:
        """
        Send a message to the WebSocket and wait for the response with the same message ID.
        """
        message_id = self._message_id
        message["id"] = message_id
        self._message_id += 1

        await self._ws.send(json.dumps(message))

        # Wait until we receive a response with the same ID
        while True:
            raw = await self._ws.recv()
            resp = json.loads(raw)
            if resp.get("id") == message_id:
                return resp

    async def get_all_exposed_entities_ids(self) -> List[str]:
        """
        Return all entity IDs where attributes.options.conversation.should_expose == True.
        """
        if self._ws is None:
            await self._connect()

        # Request all entity states
        response = await self._send({
            "type": "get_states"
        })

        if "result" not in response:
            raise Exception(f"Error while fetching states: {response}")

        exposed_entity_ids = []
        for entity in response["result"]:
            options = entity.get("attributes", {}).get("options", {})
            conversation = options.get("conversation", {})
            should_expose = conversation.get("should_expose", False)
            if should_expose:
                exposed_entity_ids.append(entity["entity_id"])

        return exposed_entity_ids

    async def close(self):
        """Close the WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None