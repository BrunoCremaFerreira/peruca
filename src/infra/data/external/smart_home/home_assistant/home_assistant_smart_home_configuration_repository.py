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

    #=======================
    # Private Methods
    #=======================

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
        ws_url = self.websocket_url \
            .replace("https", "ws") \
            .replace("http", "ws")
        
        if not ws_url.startswith("ws://"):
            ws_url = f"ws://{ws_url}"

        ws_url = f"{ws_url.rstrip("/")}/api/websocket"
        self._ws = await websockets.connect(ws_url)
        await self._authenticate()

    async def _authenticate(self):
        """Authenticate with the provided Long-Lived Access Token."""
        # Step 1: Wait for 'auth_required' message
        initial_msg = await self._ws.recv()
        initial_data = json.loads(initial_msg)
        if initial_data.get("type") != "auth_required":
            raise Exception(f"Expected 'auth_required', got: {initial_data}")

        # Step 2: Send authentication token
        auth_message = {
            "type": "auth",
            "access_token": self.token,
        }
        await self._ws.send(json.dumps(auth_message))

        # Step 3: Wait for authentication response
        auth_result_msg = await self._ws.recv()
        auth_result = json.loads(auth_result_msg)
        if auth_result.get("type") == "auth_invalid":
            raise Exception(f"Authentication failed: {auth_result.get('message')}")
        elif auth_result.get("type") != "auth_ok":
            raise Exception(f"Unexpected authentication response: {auth_result}")

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

    #=======================
    # Public Methods
    #=======================

    async def get_all_exposed_entities_ids(self) -> List[str]:
        """
        Return all entity IDs where attributes.options.conversation.should_expose == True.
        """

        if self._ws is None:
            await self._connect()

        # Request all entity states
        response = await self._send({
            "type": "config/entity_registry/list"
        })

        if "result" not in response:
            raise Exception(f"Error while fetching states: {response}")

        exposed_entity_ids = []
        for entity in response["result"]:
            options = entity.get("options", {})
            conversation = options.get("conversation", {})
            should_expose = conversation.get("should_expose", False)
            if should_expose:
                exposed_entity_ids.append(entity["entity_id"])

        return exposed_entity_ids
    
    async def get_aliases_by_entity_id(self, entity_id: str) -> List[str]:
        """
        Get entity aliases
        """

        if self._ws is None:
            await self._connect()

        # Request all entity states
        response = await self._send({
            "type": "config/entity_registry/get",
            "entity_id": entity_id
        })

        if "result" not in response:
            raise Exception(f"Error while fetching states: {response}")
        
        return response.get("result", {}).get("aliases", [])

    async def close(self):
        """Close the WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None