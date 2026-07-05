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

## Plan Files

Plans live under `docs/features/` in a `todo` → `doing` → `done` kanban:

- **`todo/`** — planned but not started.
- **`doing/`** — implementation in progress.
- **`done/`** — implemented; kept as a historical record of the rationale and
  discarded alternatives.

**Whenever a plan is requested, it MUST be saved into `docs/features/todo/`** with
the filename pattern:

```
{YYYY-MM-DD-HH-mm}-{plan_name}.md
```

Example: `2026-07-04-01-51-shopping-list-fuzzy-remove-disambiguation.md`. Use the
current local date/time (zero-padded) for the timestamp and a short kebab-case
`plan_name`.

Each plan starts with a status header (`Status`, `Criado em`, `Implementado em`,
`PR/commit`). Move the file to the matching folder as work progresses and fill in
those fields on completion.

**`done/` is a historical archive, not the current state of the system.** A plan
describes intent *before* implementation and may have diverged from what was
actually built. When reading any plan — especially in `done/` — treat the code as
the source of truth. Only `todo/` and `doing/` plans are "active"; do not use
`done/` plans as a specification of current behavior.

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
LOG_LEVEL=INFO                                  # DEBUG|INFO|WARNING|ERROR|CRITICAL; controls root logger verbosity
LLM_PROVIDER_URL=http://<ollama-host>:11434
LLM_PROVIDER_TYPE=OLLAMA                        # only OLLAMA is functional
LLM_REASONING=false                             # thinking off by default (gemma4 is a thinking model); per-graph overrides like LLM_MAIN_GRAPH_CHAT_REASONING=true
LLM_MAIN_GRAPH_CHAT_MODEL=gemma4:12b            # all graph models default to gemma4:12b
LLM_ONLY_TALK_GRAPH_CHAT_MODEL=gemma4:12b
LLM_SHOPPING_LIST_GRAPH_CHAT_MODEL=gemma4:12b
LLM_SMART_HOME_LIGHTS_GRAPH_CHAT_MODEL=gemma4:12b
LLM_SMART_HOME_CLIMATE_GRAPH_CHAT_MODEL=gemma4:12b
LLM_SMART_HOME_SENSORS_GRAPH_CHAT_MODEL=gemma4:12b
LLM_SMART_HOME_CAMERAS_GRAPH_CHAT_MODEL=gemma4:12b
LLM_MEMORY_GRAPH_CHAT_MODEL=gemma4:12b
NLP_SPACY_MODEL=pt_core_news_sm
HOME_ASSISTANT_URL=http://<ha-host>:8123
HOME_ASSISTANT_TOKEN=<long-lived-token>
MUSIC_ASSISTANT_URL=http://<music-assistant-host>:8095   # optional; unset disables the music graph
MUSIC_ASSISTANT_TOKEN=
LLM_MUSIC_GRAPH_CHAT_MODEL=gemma4:12b
PERUCA_DB_CONNECTION_STRING=<path>/peruca.db
CACHE_DB_CONNECTION_STRING=<redis-url>          # Redis for conversation history; if empty, falls back to in-memory store
CHAT_HISTORY_TTL_SECONDS=                        # empty or <=0 means no expiry
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
LlmAppService.chat()                           ← loads user memories; probes Music Assistant → context_hints
      └─► MainGraph.invoke()                   ← classifies intent(s) (LLM call #1)
              ├─► ShoppingListGraph.invoke()   ← CRUD for shopping list (LLM call)
              ├─► SmartHomeLightsGraph.invoke() ← Home Assistant lights (LLM call)
              ├─► SmartHomeClimateGraph.invoke() ← Home Assistant climate (LLM call)
              ├─► SmartHomeSensorsGraph.invoke() ← Home Assistant sensors (LLM call)
              ├─► SmartHomeCamerasGraph.invoke() ← Home Assistant cameras (LLM call)
              ├─► MusicGraph.invoke()          ← Music Assistant control (optional; only wired when MA is configured)
              ├─► OnlyTalkGraph.invoke()        ← free conversation (chain, not StateGraph)
              └─► [final_response]              ← merges multiple outputs (LLM call #2, if needed)

# After the response, as a FastAPI BackgroundTask:
MemoryAppService.learn_from_message() ─► MemoryGraph.invoke()   ← extracts durable facts → SQLite
```

All graphs inherit from `Graph` (ABC at `application/graphs/graph.py`) and implement `invoke(GraphInvokeRequest) -> dict`. `GraphInvokeRequest` carries `message: str`, `user: User`, `memories: list[str]`, and `context_hints: dict` (e.g. `music_is_playing`) through the whole chain. `LlmAppService.chat()` returns `{"intents": [...], "output": "..."}`, not a bare string.

**Key design constraints for graphs:**
- The `classify` node in each graph both classifies intent **and** extracts structured data in a single LLM call. Downstream action nodes consume what's already in the state — they do not re-call the LLM.
- Intent strings returned by the LLM must match the node names in the `StateGraph` exactly. The `intent_router` function returns `state["intent"]` directly as edge targets.
- Every `classify` node first runs the shared `Graph._extract_structured_output()` (strips `<think>` blocks, normalizes curly quotes, extracts the first balanced `[...]`/`{...}` literal). It then parses that literal: `MainGraph` and `ShoppingListGraph` use `eval()`; the smart-home graphs (lights/climate/sensors/cameras) and `MusicGraph` use `json.loads()`; `MemoryGraph` uses `json.loads()` directly. Do not change a graph's parser without updating its corresponding prompt to match.
- `OnlyTalkGraph` does not use `StateGraph`. It is a plain `prompt | llm` chain that **reads** conversation history (read-only): it loads `get_session_history(user.id).messages` and injects them into the `MessagesPlaceholder("history")` (alongside the user's memories and the current datetime). It does **not** write history. The turn is persisted once, centrally, in `LlmAppService._persist_turn()` for **every** intent — so reads and writes share the same `session_id = user.id` key.
- Each graph compiles its `StateGraph` on the first `invoke()` and caches it on `self._compiled_graph` (see `Graph.__init__`); subsequent calls reuse the compiled graph. Do not reintroduce per-request recompilation.

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

Prompts live in `infra/prompts/` as `.md` files, loaded (and cached) by name via `Graph.load_prompt(name)`. Classifier prompts must use **straight quotes** — their output is parsed by `eval()`/`json.loads()`, and curly quotes break parsing (the extractor normalizes them defensively, but prompts should not rely on that). `load_prompt` strips the `/no_think` directive automatically for non-Ollama providers or when `strip_think_directive` is set. Any stray `<think>…</think>` block a model still emits is removed by `Graph._remove_thinking_tag()` before parsing.

### Home Assistant Integration

Adapters live in `infra/data/external/smart_home/home_assistant/`. Per-domain REST/HTTP repositories (via `aiohttp`) handle control and queries — `HomeAssistantSmartHomeLightRepository`, `...ClimateRepository`, `...SensorRepository`, `...CameraRepository` — while `HomeAssistantSmartHomeConfigurationRepository` uses WebSocket (via `websockets`) for entity discovery.

The WebSocket adapter has auto-reconnect logic. Its `close()` must be called explicitly; `SmartHomeService.update_entity_aliases()` does this in a `finally` block. SSL verification is disabled for `wss://` connections (flagged with a `TODO`).

### Music Assistant Integration

`MusicAssistantMusicRepository` (`infra/data/external/music/music_assistant/`) talks to a Music Assistant server over HTTP (`aiohttp`). It is **optional**: `ioc.py` only wires the music service and `MusicGraph` when `MUSIC_ASSISTANT_URL`/`MUSIC_ASSISTANT_TOKEN` are set. On each request `LlmAppService.chat()` probes it (with a short timeout) to set the `music_is_playing` hint in `context_hints`.

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
- `ShoppingListGraph`: `edit_item` (`check_item`/`uncheck_item` are now implemented)
- `SmartHomeLightsGraph`: `change_color`, `change_mode` (`change_bright` is now implemented)
- `LlmAppService`: still receives `ContextRepository` in its constructor but never uses it — conversation persistence now goes through the injected `get_session_history` factory, not this field. The param is dead and can be removed when convenient.
