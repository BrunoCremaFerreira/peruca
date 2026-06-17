# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language Rule

**All code must be written in English.** This applies without exception to:
- Variable names, function names, class names, and all identifiers
- Inline comments (`# ...`)
- Docstrings and method summaries
- Commit messages, PR descriptions, and documentation files

The **only** exception is `infra/prompts/` — prompt files may be written in any language required by the use case (currently Portuguese).

## Git Commits — Never Automatic

**Claude Code must never create a git commit automatically.** Commits are only allowed when the user explicitly requests one. This rule applies to all agents, skills, and workflows — no automatic commit at the end of a feature implementation, test run, or any other automated step.

## Test-Driven Development (TDD) — Mandatory

**TDD must always be followed for every code change, without exception.** The cycle is strictly:

1. **Write the unit test first** — the test must fail before any implementation exists.
2. **Implement only enough code to make the test pass** — no untested logic.
3. **Refactor** — clean up while keeping all tests green.

No implementation PR or commit may be created without a corresponding unit test written beforehand. Any code change that lacks test coverage is considered incomplete and must not be merged.

## Mandatory Agent Usage

All analysis and implementation tasks **must** use the specialized agents defined in `.claude/agents/`:

| Agent | When to use |
|---|---|
| `arquiteto` | Architecture decisions, new modules, layer violations, design patterns |
| `programador` | Implementing features, fixing bugs, refactoring (requires approved test from `programador-tester`) |
| `programador-tester` | Writing unit/integration tests, reviewing coverage, creating fixtures and mocks |
| `especialista-de-prompt` | Writing/optimizing prompts in `infra/prompts/`, LangGraph node design, intent classifiers |
| `especialista-de-seguranca` | Security audits, endpoint exposure, pre-deploy reviews |

## Agent Consultation — Mandatory Before Planning

Before assembling any plan or starting any implementation, Claude Code **must**
consult the relevant specialized agents. This applies to every task — analysis,
design, implementation, testing, security review — without exception.

The consultation order for most tasks:
1. `arquiteto` — validates architectural fit and layer boundaries.
2. `especialista-de-prompt` — reviews or designs any LangGraph/prompt changes.
3. `programador-tester` — writes or approves unit tests before implementation begins.
4. `programador` — implements only after tests are approved.

Do **not** produce a final plan or write any code until the relevant agents have
been consulted and their output has been incorporated.

## Commands

All commands run from `src/`:

```bash
# Setup (run from project root)
cd scripts && bash setup.sh

# Run the API
cd src && python app.py                          # dev (port 8000)
cd src && uvicorn app:app --reload               # hot-reload mode

# Tests
python -m pytest tests/ -v                       # all tests
python -m pytest tests/unit_tests/ -v            # unit only (no external deps)
python -m pytest tests/integration_tests/ -v     # integration (requires Ollama running)
python -m pytest tests/unit_tests/test_user_service.py -v            # single file
python -m pytest tests/unit_tests/test_user_service.py::TestUserServiceAdd::test_add_valid_user_returns_uuid -v  # single test
```

Integration tests require a live Ollama instance at `LLM_PROVIDER_URL` and write to a SQLite file at `/home/<user>/tests/data/tests.db`.

## Environment Variables

Copy `.env.example` (or create `.env` in `src/`) with these keys:

```
LLM_PROVIDER_URL=http://<ollama-host>:11434
LLM_PROVIDER_TYPE=OLLAMA                        # only OLLAMA is functional
LLM_MAIN_GRAPH_CHAT_MODEL=qwen3:14b
LLM_ONLY_TALK_GRAPH_CHAT_MODEL=qwen3:14b
LLM_SHOPPING_LIST_GRAPH_CHAT_MODEL=qwen3:14b
LLM_SMART_HOME_LIGHTS_GRAPH_CHAT_MODEL=qwen3:14b
HOME_ASSISTANT_URL=http://<ha-host>:8123
HOME_ASSISTANT_TOKEN=<long-lived-token>
PERUCA_DB_CONNECTION_STRING=<path>/peruca.db
CACHE_DB_CONNECTION_STRING=<redis-url>          # Redis for conversation history; if empty, falls back to in-memory store
```

## Architecture

### Layer Dependency Rule (inviolable)

```
API (routes.py) → Application (appservices/, graphs/) → Domain ← Infra
```

`domain/` must never import from `application/` or `infra/`. There is one known minor violation: `domain/services/` imports `auto_map` and `is_null_or_whitespace` from `infra/utils.py`. Do not add new cross-layer imports in this direction.

### Layer Responsibilities

- **`routes.py`** — FastAPI router only. No business logic. Receives dependencies via `Depends()` from `ioc.py`.
- **`application/appservices/`** — Use-case orchestration. Converts domain entities to `ViewModels` via `auto_map()`. Never contains business rules.
- **`application/graphs/`** — LangGraph workflows treated as application-layer components; they orchestrate LLMs and domain services.
- **`domain/`** — Pure Python dataclasses and ABCs. No framework imports. Contains entities, commands, interfaces (ABCs), domain services, validators, and exceptions.
- **`infra/`** — All concrete implementations: SQLite repositories, Home Assistant adapters, `ioc.py`, `settings.py`, and prompt files.

### IoC and Dependency Injection

`infra/ioc.py` is the **only place where concrete dependencies are instantiated**. It exposes factory functions consumed by FastAPI's `Depends()`. Every new component needs a corresponding factory function here.

Current caveat: `Settings()` is instantiated multiple times per request (once per factory function). Do not optimize this unless profiling confirms it's a bottleneck.

### LangGraph Graph Hierarchy

```
LlmAppService.chat()
      └─► MainGraph.invoke()                   ← classifies intent (LLM call #1)
              ├─► ShoppingListGraph.invoke()   ← CRUD for shopping list (LLM call)
              ├─► SmartHomeLightsGraph.invoke() ← Home Assistant lights (LLM call)
              ├─► OnlyTalkGraph.invoke()        ← free conversation (chain, not StateGraph)
              └─► [final_response]              ← merges multiple outputs (LLM call #2, if needed)
```

All graphs inherit from `Graph` (ABC at `application/graphs/graph.py`) and implement `invoke(GraphInvokeRequest) -> dict`. `GraphInvokeRequest` carries `message: str` and `user: User` through the whole chain.

**Key design constraints for graphs:**
- The `classify` node in each graph both classifies intent **and** extracts structured data in a single LLM call. Downstream action nodes consume what's already in the state — they do not re-call the LLM.
- Intent strings returned by the LLM must match the node names in the `StateGraph` exactly. The `intent_router` function returns `state["intent"]` directly as edge targets.
- `MainGraph` and the list/lights subgraphs use `eval()` to parse LLM output (a Python literal). `SmartHomeLightsGraph._classify_intent` uses `json.loads()`. Do not change this inconsistency without updating both the node code and the corresponding prompt.
- `OnlyTalkGraph` does not use `StateGraph`. It is a plain `prompt | llm` chain that **reads** conversation history (read-only): it loads `get_session_history(user.id).messages` and injects them into the `MessagesPlaceholder("history")`. It does **not** write history. The turn is persisted once, centrally, in `LlmAppService.chat()` (see below) — so reads and writes share the same `session_id = user.id` key.
- All graphs call `self._compile()` inside `invoke()`, recompiling the `StateGraph` on every request. This is known overhead; do not "fix" it without testing for thread-safety implications.

### Fluent Validation Pattern

All domain validators follow a chain pattern that **requires `.validate()` at the end**:

```python
UserValidator()
    .validate_id(user.id)
    .validate_name(user.name)
    .validate()   # ← mandatory; without this, errors are silently swallowed
```

Known bug: `ShoppingListService.delete()` and `.check()`/`.uncheck()` omit the final `.validate()`.

### Prompt Files

Prompts live in `infra/prompts/` as `.md` files, loaded by name via `Graph.load_prompt(name)`. The `main_graph.md` uses `/no_think` (correct Qwen3 directive). The other prompts use `/no_thinking` — this inconsistency means the model may generate internal `<think>` blocks that break parsing.

### Home Assistant Integration

Two separate adapter classes handle two protocols:
- `HomeAssistantSmartHomeLightRepository` — REST/HTTP via `aiohttp` for light control
- `HomeAssistantSmartHomeConfigurationRepository` — WebSocket via `websockets` for entity discovery

The WebSocket adapter has auto-reconnect logic. Its `close()` must be called explicitly; `SmartHomeService.update_entity_aliases()` does this in a `finally` block. SSL verification is disabled for `wss://` connections (flagged with a `TODO`).

### Async / Sync Mixing

`SmartHomeLightsGraph` is synchronous (LangGraph node constraint) but calls async methods on `SmartHomeService`. It uses `asyncio.run()` for each call, which creates a new event loop per invocation. This works but conflicts with running inside an async FastAPI context. Do not introduce additional `asyncio.run()` calls inside graph nodes.

## Test Patterns

Unit tests use `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`). No `pytest-asyncio` — async tests are driven with `asyncio.get_event_loop().run_until_complete(...)`.

Conventions in unit test files:
- `_make_repo()` — returns a `MagicMock` repository with pre-configured return values
- `_sample_*()` — returns a pre-built domain entity
- Test class names: `TestXxxYyy` grouping related scenarios
- Async calls via `asyncio.get_event_loop().run_until_complete(coro)`

## Known Stubs (not implemented)

These nodes exist in code but perform no real action:
- `ShoppingListGraph`: `edit_item`, `check_item`, `uncheck_item`
- `SmartHomeLightsGraph`: `change_color`, `change_bright`, `change_mode`
- `LlmAppService`: still receives `ContextRepository` in its constructor but never uses it — conversation persistence now goes through the injected `get_session_history` factory, not this field. The param is dead and can be removed when convenient.
