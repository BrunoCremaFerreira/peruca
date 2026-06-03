# Peruca — LLM Virtual Assistant

<img src="docs/peruca.webp" alt="Peruca" height="400px">

Peruca is a self-hosted virtual assistant powered by local large language models (LLMs) via [Ollama](https://ollama.com) or [OpenAI](https://openai.com). It exposes a REST API that accepts natural-language messages and routes them through a hierarchy of [LangGraph](https://github.com/langchain-ai/langgraph) workflows, each specialised in a distinct capability: smart home control, shopping list management, free conversation, and more.

> **Status:** Active development. Some sub-graph nodes are stubs (see [Known Limitations](#known-limitations)).

---

## Table of Contents

1. [Features](#features)
2. [Architecture Overview](#architecture-overview)
3. [Layer Diagram](#layer-diagram)
4. [LangGraph Hierarchy](#langgraph-hierarchy)
5. [Sub-graphs](#sub-graphs)
6. [REST API](#rest-api)
7. [Data Storage](#data-storage)
8. [Home Assistant Integration](#home-assistant-integration)
9. [Prerequisites](#prerequisites)
10. [Setup](#setup)
11. [Docker](#docker)
12. [Environment Variables](#environment-variables)
13. [Running the API](#running-the-api)
14. [Running the Tests](#running-the-tests)
15. [Project Structure](#project-structure)
16. [Known Limitations](#known-limitations)

---

## Features

| Capability | Description |
|---|---|
| **Free conversation** | Context-aware chat with per-user in-memory history |
| **Persistent memory** | Facts extracted from conversations are stored per user (ChatGPT-style) and injected into every subsequent request |
| **Shopping list** | Add, remove, list, check, uncheck, and clear items via natural language |
| **Smart home lights** | Turn on/off and adjust brightness of Home Assistant light entities |
| **Smart home climate** | Turn on/off, set temperature, set HVAC mode, and query state of climate entities |
| **Smart home sensors** | Query current state and recent history of temperature, door, motion, and other sensors |
| **Security cameras** | Retrieve live snapshots and check the status of camera entities |

---

## Architecture Overview

Peruca follows a **Clean Architecture** approach with strict layer separation:

```
┌─────────────────────────────────────────────────────────────┐
│  API  (routes.py)                                           │
│  FastAPI router — no business logic                         │
└───────────────────────┬─────────────────────────────────────┘
                        │ Depends()
┌───────────────────────▼─────────────────────────────────────┐
│  Application                                                │
│  ├── appservices/   Use-case orchestration, ViewModels      │
│  └── graphs/        LangGraph workflows (intent routing)    │
└───────────────────────┬────────────────┬────────────────────┘
                        │                │
          ┌─────────────▼──┐   ┌─────────▼──────────────────┐
          │  Domain         │   │  Infrastructure             │
          │  entities,      │   │  SQLite repos,              │
          │  interfaces,    │   │  Home Assistant adapters,   │
          │  domain svcs,   │   │  ioc.py, settings.py,       │
          │  validators,    │   │  prompt files               │
          │  exceptions     │   │                             │
          └─────────────────┘   └────────────────────────────┘
```

**Dependency rule:** `domain/` never imports from `application/` or `infra/`. `infra/ioc.py` is the single place where concrete implementations are instantiated and wired together.

---

## Layer Diagram

```
src/
├── app.py                        ← FastAPI entry point
├── routes.py                     ← API router (delegates to appservices)
│
├── application/
│   ├── appservices/              ← Use-case orchestration
│   │   ├── llm_app_service.py    ← Chat entry point → MainGraph
│   │   ├── memory_app_service.py ← Background memory extraction → MemoryGraph
│   │   ├── shopping_list_app_service.py
│   │   ├── smart_home_app_service.py
│   │   ├── user_app_service.py
│   │   ├── user_memory_app_service.py ← CRUD for user memories
│   │   └── view_models.py        ← Request/response DTOs
│   └── graphs/                   ← LangGraph workflows
│       ├── graph.py              ← Abstract base class
│       ├── main_graph.py         ← Intent classifier + dispatcher
│       ├── memory_graph.py       ← Fact extraction (background, post-response)
│       ├── only_talk_graph.py    ← Free conversation (RunnableWithMessageHistory)
│       ├── shopping_list_graph.py
│       ├── smart_home_lights_graph.py
│       ├── smart_home_climate_graph.py
│       ├── smart_home_sensors_graph.py
│       └── smart_home_cameras_graph.py
│
├── domain/
│   ├── entities.py               ← Pure Python dataclasses
│   ├── commands.py               ← Command objects (input DTOs for domain services)
│   ├── exceptions.py             ← Domain exceptions
│   ├── interfaces/               ← ABCs for repositories and services
│   ├── services/                 ← Domain business logic
│   └── validations/              ← Fluent validator chain
│
└── infra/
    ├── ioc.py                    ← Dependency injection factory functions
    ├── settings.py               ← Pydantic settings (reads .env)
    ├── utils.py                  ← Shared utilities (auto_map, is_null_or_whitespace)
    ├── utils_nlp.py              ← NLP utilities (spaCy)
    ├── prompts/                  ← LLM prompt files (.md)
    └── data/
        ├── sqlite/               ← SQLite repository implementations
        └── external/smart_home/  ← Home Assistant HTTP & WebSocket adapters
```

---

## LangGraph Hierarchy

Every chat request follows this flow:

```
POST /llm/chat
      │
      ▼
LlmAppService.chat()              ← loads existing memories from SQLite
      │
      ▼
MainGraph.invoke()                    ← LLM call #1: classifies intent(s)
      │                               (memories injected into context)
      ├──► ShoppingListGraph.invoke()     ← LLM call: shopping list CRUD
      │
      ├──► SmartHomeLightsGraph.invoke()  ← LLM call: light control
      │
      ├──► SmartHomeClimateGraph.invoke() ← LLM call: climate control
      │
      ├──► SmartHomeSensorsGraph.invoke() ← LLM call: sensor queries
      │
      ├──► SmartHomeCamerasGraph.invoke() ← LLM call: camera snapshots/status
      │
      └──► OnlyTalkGraph.invoke()         ← chain (no StateGraph): free conversation
                │
                ▼
      final_response node             ← LLM call #2 (only when multiple intents)
                │
                ▼ (FastAPI BackgroundTask)
      MemoryAppService.learn_from_message()
                │
                ▼
      MemoryGraph.invoke()            ← extracts facts; persists to SQLite
```

`MainGraph` may activate **multiple sub-graphs in parallel** when a single message spans several intents (e.g. "turn off the lights and add milk to the shopping list"). The `final_response` node merges the sub-graph outputs into a single, coherent reply.

**Key design invariants:**
- The `classify` node in each sub-graph both classifies the intent **and** extracts structured action data in a single LLM call. Downstream action nodes do not make additional LLM calls.
- Intent strings returned by the LLM must match the `StateGraph` node names exactly. The `intent_router` function returns `state["intent"]` directly as edge targets.
- Every `StateGraph` is recompiled on each `invoke()` call.
- `MemoryGraph` runs as a FastAPI `BackgroundTask` after every response — failures are silently swallowed so they never affect the user response.

---

## Sub-graphs

### MainGraph

Classifies the user message into one or more intents and routes to the appropriate sub-graphs.

```
START → classify → [smart_home_lights | smart_home_climate | smart_home_sensors
                    | smart_home_security_cams | shopping_list | only_talking]
                                             → final_response → END
```

### MemoryGraph

Extracts persistent facts from the conversation (user message + assistant reply) and stores them per user in SQLite. Runs in the background after every chat response.

```
prompt | llm  →  json.loads()  →  persist facts via UserMemoryService
```

Stored memories are loaded on every subsequent `chat()` call and injected into `GraphInvokeRequest`, making them available as context across all sub-graphs.

### ShoppingListGraph

Manages a persistent shopping list backed by SQLite.

```
START → classify → [add_item | edit_item | delete_item | check_item
                    | uncheck_item | list_items | clear_items | not_recognized]
                                             → final_response → END
```

| Intent | Action |
|---|---|
| `add_item` | Parses `name,quantity` pairs and persists each item |
| `delete_item` | Matches by name and removes from the database |
| `check_item` / `uncheck_item` | Toggles the checked flag |
| `list_items` | Returns all items |
| `clear_items` | Deletes all items |
| `edit_item` | **Stub** — not yet implemented |

### SmartHomeLightsGraph

Controls Home Assistant light entities via REST.

```
START → classify → [turn_on | turn_off | change_bright | change_color
                    | change_mode | not_recognized]
                                             → final_response → END
```

A secondary LLM call resolves human-readable device aliases to `light.*` entity IDs before issuing the Home Assistant command.

| Intent | Action |
|---|---|
| `turn_on` / `turn_off` | Toggles lights (supports area-based commands) |
| `change_bright` | Sets brightness (0–100 %) |
| `change_color` | **Stub** |
| `change_mode` | **Stub** |

### SmartHomeClimateGraph

Controls Home Assistant `climate.*` entities.

```
START → classify → [turn_on | turn_off | set_temperature | set_hvac_mode
                    | query_state | not_recognized]
                                             → final_response → END
```

| Intent | Action |
|---|---|
| `turn_on` / `turn_off` | Activates/deactivates the AC unit |
| `set_temperature` | Sets the target temperature |
| `set_hvac_mode` | Maps mode names to HA HVAC modes (`frio→cool`, `calor→heat`, …) |
| `query_state` | Returns current temperature, target, and mode |

### SmartHomeSensorsGraph

Queries `sensor.*` and `binary_sensor.*` entities.

```
START → classify → [query_current_state | query_history | not_recognized]
                                             → final_response → END
```

The `final_response` node issues an additional LLM call to compose a human-friendly answer from the raw sensor readings.

### SmartHomeCamerasGraph

Handles `camera.*` entities.

```
START → classify → [show_snapshot | check_status | not_recognized]
                                             → final_response → END
```

| Intent | Action |
|---|---|
| `show_snapshot` | Fetches a JPEG snapshot and returns it as a Base64 data URI |
| `check_status` | Returns the camera state (streaming/idle/unavailable) |

### OnlyTalkGraph

Free-form conversational graph. Does **not** use `StateGraph` — it uses `RunnableWithMessageHistory` with per-user in-memory history keyed by `user.id`.

> Conversation history is held in memory and is lost on process restart. Persistent facts are handled separately by `MemoryGraph`.

---

## REST API

The API runs on port **8000** by default. Interactive docs are available at `/docs` (Swagger UI) and `/redoc`.

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check — returns `200 OK` |

### LLM

| Method | Path | Description |
|---|---|---|
| `POST` | `/llm/chat` | Send a message; returns the assistant's response |

**Request body:**
```json
{
  "message": "Turn off the kitchen lights",
  "chat_id": "optional-thread-id",
  "external_user_id": "user-123"
}
```

### Users

| Method | Path | Description |
|---|---|---|
| `GET` | `/user` | List all users |
| `GET` | `/user/{id}` | Get user by internal ID |
| `GET` | `/user/external-id/{external_id}` | Get user by external ID |
| `POST` | `/user` | Create a user |
| `PUT` | `/user` | Update a user |

### User Memory

| Method | Path | Description |
|---|---|---|
| `GET` | `/user/{id}/memory` | List all memories for a user |
| `DELETE` | `/user/{id}/memory/{memory_id}` | Delete a specific memory |
| `DELETE` | `/user/{id}/memory` | Clear all memories for a user |

### Shopping List

| Method | Path | Description |
|---|---|---|
| `GET` | `/shopping-list` | List all items |
| `GET` | `/shopping-list/{id}` | Get item by ID |
| `POST` | `/shopping-list` | Add an item |
| `PUT` | `/shopping-list` | Update item quantity |
| `DELETE` | `/shopping-list/{id}` | Delete an item |
| `POST` | `/shopping-list/clear/{clean_type}` | Clear list (all or checked) |
| `PUT` | `/shopping-list/{id}/check` | Mark item as bought |
| `PUT` | `/shopping-list/{id}/uncheck` | Unmark item |

### Smart Home

| Method | Path | Description |
|---|---|---|
| `GET` | `/smart-home/backend/entity/aliases` | List all entity aliases |
| `PUT` | `/smart-home/backend/update-aliases` | Synchronise aliases from Home Assistant via WebSocket |

---

## Data Storage

| Store | Technology | Purpose |
|---|---|---|
| Main database | SQLite | Users, shopping list items, entity aliases, user memories |
| Conversation history | In-memory (`dict`) | Per-user chat history for `OnlyTalkGraph` (lost on restart) |
| Context repository | Redis (wired but unused) | Reserved for future persistent session store |

The SQLite file path is controlled by `PERUCA_DB_CONNECTION_STRING` (defaults to `src/peruca.db`; Docker mounts it at `/data/peruca.db`).

---

## Home Assistant Integration

Two separate adapters communicate with Home Assistant:

| Adapter | Protocol | Entities |
|---|---|---|
| `HomeAssistantSmartHomeLightRepository` | REST / HTTP (`aiohttp`) | `light.*` |
| `HomeAssistantSmartHomeClimateRepository` | REST / HTTP (`aiohttp`) | `climate.*` |
| `HomeAssistantSmartHomeSensorRepository` | REST / HTTP (`aiohttp`) | `sensor.*`, `binary_sensor.*` |
| `HomeAssistantSmartHomeCameraRepository` | REST / HTTP (`aiohttp`) | `camera.*` |
| `HomeAssistantSmartHomeConfigurationRepository` | WebSocket (`websockets`) | Entity discovery (all domains) |

The WebSocket adapter has auto-reconnect logic and must be closed explicitly. `SmartHomeService.update_entity_aliases()` handles this in a `finally` block.

> SSL verification is disabled for `wss://` connections — this is a known issue flagged with a `TODO` in the source.

---

## Prerequisites

- Python 3.12+
- [Ollama](https://ollama.com) running and accessible **or** an OpenAI API key
- [Home Assistant](https://www.home-assistant.io/) with a long-lived access token
- SQLite (bundled with Python)

---

## Setup

```bash
# Clone the repository
git clone <repo-url>
cd peruca

# Run the setup script (creates venv, installs deps, initialises SQLite)
cd scripts && bash setup.sh
```

---

## Docker

Docker is the recommended way to run Peruca in production.

### Production

```bash
# Copy and fill in your environment variables
cp .env.example .env   # edit .env

# Build and start
docker compose up -d
```

The container exposes port `8000` and persists the SQLite database in the `peruca_data` named volume.

### Development (hot-reload)

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up
```

The override mounts `./src` into the container so code changes reload automatically.

---

## Environment Variables

Create a `.env` file in the project root (or `src/` when running without Docker):

```env
# LLM Provider — "OLLAMA" or "OPENAI"
LLM_PROVIDER_TYPE=OLLAMA
LLM_PROVIDER_URL=http://<ollama-host>:11434
LLM_PROVIDER_API_KEY=                        # required for OPENAI

# Models (all default to qwen3:14b; use gpt-4o or similar for OpenAI)
LLM_MAIN_GRAPH_CHAT_MODEL=qwen3:14b
LLM_ONLY_TALK_GRAPH_CHAT_MODEL=qwen3:14b
LLM_SHOPPING_LIST_GRAPH_CHAT_MODEL=qwen3:14b
LLM_SMART_HOME_LIGHTS_GRAPH_CHAT_MODEL=qwen3:14b
LLM_SMART_HOME_CLIMATE_GRAPH_CHAT_MODEL=qwen3:14b
LLM_SMART_HOME_SENSORS_GRAPH_CHAT_MODEL=qwen3:14b
LLM_SMART_HOME_CAMERAS_GRAPH_CHAT_MODEL=qwen3:14b
LLM_MEMORY_GRAPH_CHAT_MODEL=qwen3:14b

# Home Assistant
HOME_ASSISTANT_URL=http://<ha-host>:8123
HOME_ASSISTANT_TOKEN=<long-lived-token>

# Databases
PERUCA_DB_CONNECTION_STRING=sqlite:///path/to/peruca.db
CACHE_DB_CONNECTION_STRING=redis://localhost:6379   # unused at runtime

# NLP (spaCy model for Portuguese)
NLP_SPACY_MODEL=pt_core_news_sm
```

**OpenAI example:**
```env
LLM_PROVIDER_TYPE=OPENAI
LLM_PROVIDER_URL=https://api.openai.com/v1
LLM_PROVIDER_API_KEY=sk-...
LLM_MAIN_GRAPH_CHAT_MODEL=gpt-4o
```

---

## Running the API

All commands are run from the `src/` directory.

```bash
# Standard
python app.py

# Hot-reload mode (recommended for development)
uvicorn app:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## Running the Tests

```bash
# All tests
python -m pytest tests/ -v

# Unit tests only (no external dependencies required)
python -m pytest tests/unit_tests/ -v

# Integration tests (requires a live Ollama instance)
python -m pytest tests/integration_tests/ -v

# Single file
python -m pytest tests/unit_tests/test_user_service.py -v

# Single test
python -m pytest tests/unit_tests/test_user_service.py::TestUserServiceAdd::test_add_valid_user_returns_uuid -v
```

Integration tests write to a SQLite file at `~/tests/data/tests.db` and require `LLM_PROVIDER_URL` to be set.

---

## Project Structure

```
peruca/
├── Dockerfile
├── docker-compose.yml
├── docker-compose.override.yml   ← dev: hot-reload + src bind-mount
├── docs/
│   ├── peruca.webp               ← Project mascot
│   └── diagrams/                 ← Architecture diagrams (drawio, SVG)
├── scripts/
│   └── setup.sh                  ← Environment bootstrap script
├── src/
│   ├── app.py                    ← FastAPI application factory
│   ├── routes.py                 ← API router
│   ├── application/              ← Use cases and LangGraph workflows
│   ├── domain/                   ← Entities, interfaces, domain services
│   ├── infra/                    ← Concrete implementations and configuration
│   └── tests/
│       ├── unit_tests/           ← Fast, no external dependencies
│       └── integration_tests/    ← Require Ollama running
├── CLAUDE.md                     ← AI coding assistant instructions
└── README.md
```

---

## Known Limitations

| Area | Detail |
|---|---|
| Shopping list | `edit_item` node is a stub — returns the payload unchanged |
| Lights | `change_color` and `change_mode` nodes are stubs |
| Conversation history | Held in-memory in `OnlyTalkGraph`; lost on process restart |
| Persistent memory | Memory extraction may occasionally miss or duplicate facts depending on LLM output quality |
| Context repository | Redis wired in `LlmAppService` constructor but never consumed |
| Async/sync mixing | `SmartHomeLightsGraph` and other sync graphs call `asyncio.run()` per action, creating a new event loop each time — may conflict with an async FastAPI context |
| Prompt inconsistency | `main_graph.md` uses `/no_think`; other prompts use `/no_thinking` — the model may emit `<think>` blocks that break parsing |
| SSL | WebSocket adapter disables SSL verification for `wss://` connections |
| Validator bug | `ShoppingListService.delete()`, `.check()`, and `.uncheck()` omit the mandatory `.validate()` call at the end of the fluent chain |
