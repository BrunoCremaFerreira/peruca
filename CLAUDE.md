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

## Feature Branches — One per Plan

**Every plan implementation must, by default, happen on its own feature branch created from `development`.** Never implement a plan directly on `development` or `main`.

Before writing any code for a plan:

1. Make sure `development` is checked out and up to date.
2. Create the branch off `development` using the pattern `feature/{plan_name}` — the same kebab-case `plan_name` used in the plan filename (e.g. plan `2026-07-04-01-51-shopping-list-fuzzy-remove-disambiguation.md` → branch `feature/shopping-list-fuzzy-remove-disambiguation`).
3. Do all the implementation work for that plan on this branch.

The only exception is when the user explicitly asks for the work to be done on the current branch. This rule does not change the "Git Commits — Never Automatic" rule: creating the branch is automatic, committing to it is not.

## Test-Driven Development (TDD) — Mandatory

**TDD must always be followed for every code change, without exception.** The cycle is strictly:

1. **Write the unit test first** — the test must fail before any implementation exists.
2. **Implement only enough code to make the test pass** — no untested logic.
3. **Refactor** — clean up while keeping all tests green.

No implementation PR or commit may be created without a corresponding unit test written beforehand. Any code change that lacks test coverage is considered incomplete and must not be merged.

## Entity IDs — Always UUID

**Whenever an entity is created in the persistence layers, its `id` must be of type UUID.** This applies without exception to every domain entity that is stored (SQLite repositories, external adapters, or any other persistence). Do not use auto-increment integers, sequential counters, or other id schemes for persisted entities — always generate a UUID.

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
LLM_VEHICLE_MAINTENANCE_GRAPH_CHAT_MODEL=gemma4:12b
LLM_PET_HEALTH_GRAPH_CHAT_MODEL=gemma4:12b
LLM_CALCULATOR_GRAPH_CHAT_MODEL=gemma4:12b
LLM_CONTEXT_SUMMARY_GRAPH_CHAT_MODEL=gemma4:12b
LLM_CONTEXT_SUMMARY_GRAPH_CHAT_TEMPERATURE=0.2  # fidelity over creativity (0.1 makes the 12b telegraphic on long text)
LLM_USER_SETTINGS_GRAPH_CHAT_MODEL=gemma4:12b
LLM_USER_SETTINGS_GRAPH_CHAT_TEMPERATURE=0.1    # classifier: the LLM only transcribes the city; Python resolves the IANA id
DEFAULT_TIMEZONE=America/Sao_Paulo               # timezone of a user with no `user_settings` row; the only timezone literal in the system
MAINTENANCE_FLOW_TTL_SECONDS=600                # TTL for the pending multi-turn maintenance flow AND the pet-health flow (shared; it is the flow mechanism's TTL, not a per-domain one) / focused record
PERUCA_API_KEY=                                 # X-API-Key required on every route except /health; empty = migration mode (open, logs a warning)
PERUCA_DB_CONNECTION_STRING=<path>/peruca.db
CACHE_DB_CONNECTION_STRING=<redis-url>          # Redis for conversation history; if empty, falls back to in-memory store
CHAT_HISTORY_TTL_SECONDS=                        # empty or <=0 means no expiry; the compaction summary shares this TTL and is renewed every turn
CHAT_COMPACTION_ENABLED=true                     # background summarization of the old part of a long conversation
CHAT_COMPACTION_TRIGGER_MESSAGES=30              # fires when the history reaches this many messages
CHAT_COMPACTION_TRIGGER_CHARS=24000              # secondary trigger (~6k tokens), whichever comes first
CHAT_COMPACTION_KEEP_TAIL_MESSAGES=16            # recent messages kept verbatim (8 turns; even = turn boundary)
CHAT_COMPACTION_MAX_SUMMARY_CHARS=2500           # summary cap, truncated at a whole-bullet boundary
```

**Single worker required.** The compaction swap is guarded by in-process
`threading` locks (`infra/user_lock_registry.py`), so the API must run with one
worker. With multiple workers a compaction in one worker can overwrite turns
appended by another (silent history loss). Moving the swap to a Redis Lua script
is the prerequisite for multi-worker.

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
              ├─► VehicleMaintenanceGraph.invoke() ← vehicle maintenance records (LLM call); vehicle CRUD is REST-only
              ├─► PetHealthGraph.invoke()      ← pet vaccines/health events (LLM call); pet CRUD is REST-only
              ├─► CalculatorGraph.invoke()     ← sequential/scientific/symbolic math (LLM only transcribes; Decimal + SymPy compute)
              ├─► UserSettingsGraph.invoke()   ← per-user preferences: get/set the timezone (LLM only transcribes the city; Python resolves the IANA id)
              ├─► OnlyTalkGraph.invoke()        ← free conversation (chain, not StateGraph); pets are injected as "siblings" via context_hints
              └─► [final_response]              ← merges multiple outputs (LLM call #2, if needed)

# After the response, as FastAPI BackgroundTasks (in this order):
MemoryAppService.learn_from_message() ─► MemoryGraph.invoke()   ← extracts durable facts → SQLite
ContextCompactionAppService.compact_if_needed() ─► ContextSummaryGraph.invoke()  ← summarizes the OLD turns → Redis
```

All graphs inherit from `Graph` (ABC at `application/graphs/graph.py`) and implement `invoke(GraphInvokeRequest) -> dict`. `GraphInvokeRequest` carries `message: str`, `user: User`, `memories: list[str]`, `context_hints: dict` (e.g. `music_is_playing`), and `user_timezone: str` (resolved once per request by `LlmAppService.chat()`) through the whole chain. `LlmAppService.chat()` returns `{"intents": [...], "output": "..."}`, not a bare string.

**Key design constraints for graphs:**
- The `classify` node in each graph both classifies intent **and** extracts structured data in a single LLM call. Downstream action nodes consume what's already in the state — they do not re-call the LLM.
- Intent strings returned by the LLM must match the node names in the `StateGraph` exactly. The `intent_router` function returns `state["intent"]` directly as edge targets.
- Every `classify` node first runs the shared `Graph._extract_structured_output()` (strips `<think>` blocks, normalizes curly quotes, extracts the first balanced `[...]`/`{...}` literal). It then parses that literal: `MainGraph` and `ShoppingListGraph` use `ast.literal_eval()` (their prompts emit single-quoted Python literals — never `eval()`, which would execute injected expressions); the smart-home graphs (lights/climate/sensors/cameras), `MusicGraph`, `VehicleMaintenanceGraph`, `PetHealthGraph`, and `UserSettingsGraph` use `json.loads()`; `MemoryGraph` uses `json.loads()` directly. Do not change a graph's parser without updating its corresponding prompt to match.
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

Prompts live in `infra/prompts/` as `.md` files, loaded (and cached) by name via `Graph.load_prompt(name)`. Classifier prompts must use **straight quotes** — their output is parsed by `ast.literal_eval()`/`json.loads()`, and curly quotes break parsing (the extractor normalizes them defensively, but prompts should not rely on that). `load_prompt` strips the `/no_think` directive automatically for non-Ollama providers or when `strip_think_directive` is set. Any stray `<think>…</think>` block a model still emits is removed by `Graph._remove_thinking_tag()` before parsing.

### Home Assistant Integration

Adapters live in `infra/data/external/smart_home/home_assistant/`. Per-domain REST/HTTP repositories (via `aiohttp`) handle control and queries — `HomeAssistantSmartHomeLightRepository`, `...ClimateRepository`, `...SensorRepository`, `...CameraRepository` — while `HomeAssistantSmartHomeConfigurationRepository` uses WebSocket (via `websockets`) for entity discovery.

The WebSocket adapter has auto-reconnect logic. Its `close()` must be called explicitly; `SmartHomeService.update_entity_aliases()` does this in a `finally` block. SSL verification is disabled for `wss://` connections (flagged with a `TODO`).

### Music Assistant Integration

`MusicAssistantMusicRepository` (`infra/data/external/music/music_assistant/`) talks to a Music Assistant server over HTTP (`aiohttp`). It is **optional**: `ioc.py` only wires the music service and `MusicGraph` when `MUSIC_ASSISTANT_URL`/`MUSIC_ASSISTANT_TOKEN` are set. On each request `LlmAppService.chat()` probes it (with a short timeout) to set the `music_is_playing` hint in `context_hints`.

### Vehicle Maintenance

Lets the user register/query/edit/remove **maintenance records** for their vehicles via chat, while **vehicle CRUD itself is REST-only**. Key pieces:

- **Domain**: `Vehicle`/`MaintenanceRecord` entities, `VehicleService` (per-user name uniqueness; delete cascades children-first) and `MaintenanceService` (validates `vehicle.user_id == user_id` on **every** operation). `date_resolver.py` resolves closed date tokens/periods in Python — **the LLM never does calendar arithmetic**; it only emits tokens like `today`/`yesterday`/`this_week` and explicit `YYYY-MM-DD`. `text_matching.py` (shared with shopping-list disambiguation) fuzzy-matches vehicle terms.
- **REST-only writes, enforced structurally (ISP)**: the vehicle interface is split into `VehicleReadRepository` (read) and `VehicleRepository` (read+write) in `domain/interfaces/vehicle_repository.py`. The chat path (graph, `MaintenanceService`, `LlmAppService`) is wired with `ReadOnlyVehicleRepository` (`infra/data/read_only_vehicle_repository.py`), which **physically lacks** `add`/`update`/`delete`. The full repo is reserved for `VehicleAppService` (the `/vehicle` REST routes). So even under prompt injection, no chat-reachable code can mutate a vehicle. Chat attempts to write a vehicle hit the `vehicle_write_forbidden` node → fixed reply "Não tenho permissão para realizar esta operação".
- **Multi-turn slot-filling + focused record**: `MaintenanceFlowService` (backed by `ContextRepository`, keyed by `user_id` with embedded TTL) persists a `PendingMaintenanceFlow` for register slot collection (vehicle→date→km) and a "focused record" (the record a query last reported on) so a follow-up "altere a km desse registro" / "remova este registro" knows its target. `LlmAppService` short-circuits a pending flow **before** `MainGraph` (mirrors the shopping-list `DisambiguationService` pattern); deletes go through a `delete_confirm` yes/no turn.
- **Prompt-injection hardening**: free-text reinjected into prompts (record descriptions, history) is passed through `sanitize_for_prompt` (`application/appservices/prompt_sanitizer.py`); `query_limit` from the LLM is hard-capped at `_QUERY_RECORD_LIMIT` (20).

### Pet Health

Lets the user register/query/edit/remove **health events** (vaccines, dewormers, antiparasitics, medications, vet visits) for their pets via chat, while **pet CRUD itself is REST-only**. It is a near 1:1 mirror of Vehicle Maintenance; the shared refactors from that work power it (`text_matching.find_by_term`, `flow_state_store.FlowStateStore`, `PendingFlow` with a `flow_domain` discriminator). Key differences:

- **Domain**: `Pet` (name + `nicknames` list — 1st is primary; `birth_date`, `sex` closed set `male|female|unknown`, `species` free text, `description`) / `PetHealthEvent` (`event_type` closed set, `description`, `occurred_at`). `PetService` enforces per-user uniqueness over the **union** of every pet's name+nicknames (so the chat matcher never stays ambiguous) and cascades delete children-first. `PetHealthService` validates `pet.user_id == user_id` on **every** op and rejects an event dated **before** the pet's `birth_date` (only when set). `find_pets_by_term` matches on name AND nicknames.
- **Nicknames persistence**: a JSON array in a TEXT column (`sqlite_pet_repository.py`) — a value object of the Pet aggregate, order-preserving (index 0 = primary), matched only in Python.
- **REST-only writes, enforced structurally (ISP)**: `PetReadRepository` vs `PetRepository` in `domain/interfaces/pet_repository.py`; the chat path (graph, `PetHealthService`, `LlmAppService`) gets `ReadOnlyPetRepository` (`infra/data/read_only_pet_repository.py`), which physically lacks writes. Full repo reserved for `PetAppService` (`/pet` routes). Chat write attempts hit `pet_write_forbidden` → same fixed reply.
- **Multi-turn slot-filling + focused record + the "tomou mais alguma?" loop**: `PetHealthFlowService` collects `pet → event_name → date`; after a **vaccine** registers via the flow it arms a `register_more` operation so the next reply ("sim, a raiva" registers another; "só esta"/"não" ends). All deterministic (no LLM), short-circuited in `LlmAppService` before `MainGraph`, dispatched by `flow_domain`. Reuses the `MAINTENANCE_FLOW_TTL_SECONDS` TTL.
- **Dynamic persona (§2.9)**: the pets registered by the user are injected into the `OnlyTalkGraph` system prompt as Peruca's "siblings" via `context_hints["user_pets_persona"]` (the old hardcoded Caçolin/Caçolão block was removed from `only_talk_graph.md`). `MemoryGraph` was told not to re-extract dated pet-health events as durable memories.

### User Timezone

Every "now"/"today" the chat reasons about is the user's local one, not the server's. The preference is a `UserSettings` entity (1:1 with a user, unique `user_id` in the `user_settings` table); absence of a row means "use `DEFAULT_TIMEZONE`" — a read never writes a ghost record.

- **Writing it via chat is allowed** (the damage is trivial and reversible, unlike a vehicle/pet write): the `UserSettingsGraph` (intent `user_settings` in `MainGraph`, wired unconditionally) gets the full `UserSettingsRepository`. It still has **no write access whatsoever to `UserRepository`** — that is exactly why the timezone is a separate entity instead of a column on `User`.
- **The LLM never does timezone or calendar arithmetic.** `user_settings_graph.md` only transcribes what was said (`location`) and, when it is sure, suggests an identifier (`timezone_iana`) — the key rule being "no certainty → leave it empty". Python is the authority: `domain/services/timezone_resolver.py` accepts the suggestion only if it exists in the tz database, otherwise resolves the spoken city through a curated pt-BR dictionary + fuzzy `text_matching`; nothing resolves → a friendly, example-anchored answer and no write. `domain/services/clock.py` (pure `zoneinfo`, determinism by injecting `now_utc` — the `date_resolver` pattern) does all the conversion.
- **Single resolution point**: `LlmAppService.chat()` reads the timezone once per request and injects it into `GraphInvokeRequest.user_timezone` (a typed field, not a `context_hint`). Graphs never touch the settings repository. The field defaults to `""` — an unresolved timezone raises a `ValidationError` in the clock instead of silently pretending a zone.
- **Datetimes are persisted in UTC and converted only for presentation** (`format_local` / `to_local`; naive values from SQLite are assumed UTC). The visible case is `smart_home_sensors_graph`'s `last_changed`. `application/appservices/datetime_presenter.py` is the single formatting point for the pt-BR wording (weekday spelled out — the models get it wrong when they must derive it) fed to `only_talk_graph.md`, whose rule forbids inventing any other time, **including for other timezones**.
- **Civil dates never convert.** `performed_at` / `occurred_at` / `birth_date` are timezone-less event dates: converting them would move the day. What the user's timezone changes for them is only the **reference** ("hoje"/"esta semana") handed to `date_resolver` — in the graphs and, through `parse_slot_reply(..., reference=...)`, in the multi-turn flows.
- **`max_civil_date_on_earth()`** (UTC today + 1 day, the local date at UTC+14) is the ceiling used by the future-date guards in the validators, instead of the server's `date.today()`. A civil date carries no timezone, so comparing it against one arbitrary server timezone would reject a legitimate "today" from a user living ahead of the server. `VehicleValidator`'s year ceiling is anchored on the **UTC** year for the same reason.
- **REST stays UTC ISO-8601** (`tests/unit_tests/test_rest_utc_contract.py` freezes this): localization is a chat-presentation concern; the API client formats.

### Chat Context Compaction

Keeps a long conversation from forgetting how it started. `OnlyTalkGraph` windows
the history to the last `llm_only_talk_history_max_messages` (30) messages;
anything past that used to be dropped. Now a background task summarizes the
**old** part and the graph reads `[summary + recent tail]` instead.

- **Off the request path**: `ContextCompactionAppService.compact_if_needed()` is a
  second `BackgroundTask` on `/llm/chat` (after `learn_from_message`). It mirrors
  `MemoryAppService`: synchronous, whole body in try/except, never propagates. Its
  gate is a cheap early-exit (one read + a `len()`), so the common turn pays ~nothing.
- **`ContextSummaryGraph`** (`context_summary_graph.md`) is a plain `prompt | llm`
  chain (no `StateGraph`), like `OnlyTalkGraph`/`MemoryGraph`. Output is **markdown
  with fixed `###` headers, not JSON** — the consumer is another prompt, not a
  parser. The graph is the **sole owner of output validation**: empty → `None`;
  does not start with `###` → `None` (catches "Claro! Aqui está o resumo:" and
  in-persona answers); over the cap → truncated at a **whole-bullet** boundary.
  Invalid output is discarded silently and retried on the next trigger.
- **Storage**: a separate key `chat_summary:{user_id}` (JSON: `summary`, `covers`,
  `updated_at`), sharing `chat_history`'s TTL, renewed on every turn. The summary is
  **not** put inside the `chat_history` array — the window takes the *last* N, so it
  would be sliced off, and the serializer round-trips an unknown type as
  `HumanMessage`.
- **Presentation**: injected as a `HumanMessage` `[Resumo da conversa anterior: ...]`
  at position 0 **after** the windowing (so it costs no window slot), never in the
  system prompt — putting user-derived text into the `system` role would be a
  prompt-injection privilege escalation. On the read path it goes through
  `sanitize_summary_for_prompt` (`prompt_sanitizer.py`), which — unlike
  `sanitize_for_prompt` — **preserves newlines** (the bullets are the format) while
  neutralizing `[`/`]` and `<<<...>>>` sentinels, so a summary can never forge an
  `[Imagem #N ...]` line or a `<<<DESC_IMAGEM>>>` marker. `Imagem #N` *bare*
  survives on purpose: that is what keeps `has_prior_image` (the re-vision gate) working.
- **Concurrency — verify-before-swap (logical CAS)**: `_persist_turn` is
  append-only, so the prefix being summarized is immutable except by
  `reset_context` or another compaction. The app service snapshots
  `(count, conversation_digest(prefix))` **before** the LLM call; `apply_compaction`
  re-reads under a per-user lock and swaps only if they still match. The LLM call
  (seconds) runs **outside** the lock; the lock is held for microseconds. A mismatch
  aborts and discards — the failure mode is always "did not compact yet", never
  "lost history". `UserLockRegistry` (`infra/user_lock_registry.py`) is shared by
  the store, `RedisChatMessageHistory` and `LockedInMemoryChatMessageHistory`, so
  the in-memory fallback is guarded too (a raw `InMemoryChatMessageHistory` takes no
  lock and would lose a turn appended mid-swap).
- `conversation_digest` lives in `domain/services/` — it defines the semantics of
  the `expected_digest` parameter that the `ConversationContextStore` ABC (a domain
  port) publishes, and both application and infra must compute it identically.

### API Authentication

Every route except `/health` requires the `X-API-Key` header. `infra/security.py::require_api_key` compares it against `PERUCA_API_KEY` with `secrets.compare_digest` (constant-time). `app.py` splits the routers: `public_router` (holds `/health`) is mounted openly, while `router` (everything else) is mounted behind `Depends(require_api_key)`. **Migration mode**: when `PERUCA_API_KEY` is empty the check is a no-op and the app logs a startup warning — so existing deployments keep working until an operator sets the key. CORS `allow_credentials` is disabled when `CORS_ORIGIN` is `*`.

### Async / Sync Mixing

`SmartHomeLightsGraph` is synchronous (LangGraph node constraint) but calls async methods on `SmartHomeService`. It uses `asyncio.run()` for each call, which creates a new event loop per invocation. This works but conflicts with running inside an async FastAPI context. Do not introduce additional `asyncio.run()` calls inside graph nodes.

## Test Patterns

Unit tests use `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`). No `pytest-asyncio` — async tests are driven with `asyncio.get_event_loop().run_until_complete(...)`.

Conventions in unit test files:
- `_make_repo()` — returns a `MagicMock` repository with pre-configured return values
- `_sample_*()` — returns a pre-built domain entity
- Test class names: `TestXxxYyy` grouping related scenarios
- Async calls via `asyncio.get_event_loop().run_until_complete(coro)`

Integration tests (`-m integration`) require a live Ollama and write to a SQLite file in `/dev/shm` (per-xdist-worker). Batteries that need an external backend **skip gracefully** when it is unreachable, so the suite stays green without the hardware: `redis_backed_env` (Redis history/image store), and `home_assistant_available` / `music_assistant_available` (the four smart-home batteries and the music battery) probe the configured URL with a short cached HTTP check and `pytest.skip` if it does not answer. `test_llm_app_service_chat__main_graph.py` is a mixed file — its smart-home/camera-routing cases still execute the sub-graph and thus need Home Assistant.

## Known Stubs (not implemented)

These nodes exist in code but perform no real action:
- `ShoppingListGraph`: `edit_item` (`check_item`/`uncheck_item` are now implemented)
- `SmartHomeLightsGraph`: `change_color`, `change_mode` (`change_bright` is now implemented)
- `LlmAppService`: still receives `ContextRepository` in its constructor but never uses it — conversation persistence now goes through the injected `get_session_history` factory, not this field. The param is dead and can be removed when convenient.
