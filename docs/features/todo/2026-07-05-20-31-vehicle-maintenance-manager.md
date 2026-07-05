# Plano: Gestor de Manutenção Veicular

- **Status:** todo
- **Criado em:** 2026-07-05 20:31
- **Implementado em:** —
- **PR/commit:** —
- **Origem:** `docs/features/todo/sketch.txt`
- **Consultorias realizadas (obrigatórias):** `arquiteto`, `especialista-de-prompt`, `programador-tester`

---

## 1. Objetivo

Permitir que o Peruca gerencie a manutenção dos veículos do usuário:

1. **Cadastro de veículos exclusivamente via API REST** (add/edit/delete). Via chat,
   qualquer tentativa de escrita em veículo recebe a resposta fixa
   **"Não tenho permissão para realizar esta operação"**. Listar veículos via chat é permitido.
2. **Registro de manutenções via chat** (texto livre: troca de óleo, pneus, peças,
   fluidos, rodízio...), com campos veículo/descrição/data/quilometragem e **fluxo
   multi-turno** de coleta dos dados faltantes (um por vez: veículo → data → km).
3. **Consultas abertas** sobre o histórico ("2 últimas manutenções do Mitsubishi?",
   "quando troquei o óleo?"), com desambiguação de veículo e follow-ups contextuais
   ("E do pajero?").
4. **Edição/remoção de registros via chat**, com confirmação obrigatória antes de remover.

**Restrição crítica (sketch, item IMPORTANTE):** nem toda menção a carros é manutenção.
"Gosto muito do meu Outlander", "O Outlander dá muita manutenção?" → `only_talking`.

---

## 2. Decisões de design

### 2.1 Um único `VehicleMaintenanceGraph` (não dois graphs)

Veículo e manutenção compartilham as mesmas entidades, o mesmo resolvedor fuzzy de
nome de veículo e o mesmo estado conversacional multi-turno — separar duplicaria a
resolução e quebraria follow-ups. Precedente: `ShoppingListGraph` (um graph por
domínio de negócio, sub-intents no nó `classify`). O split dos smart-home graphs
existe por razões que não se aplicam aqui (repositórios HA e prompts de alias próprios).

Novo intent no MainGraph: **`vehicle_maintenance`** (string idêntica ao nome do node,
regra do `intent_router`).

### 2.2 Sub-intents internos do graph (= nomes dos nodes)

```
classify → list_vehicles | register_maintenance | query_maintenance
         | edit_maintenance | delete_maintenance
         | vehicle_write_forbidden | not_recognized
         → final_response → END
```

- **Uma única chamada LLM no `classify`** que classifica e extrai os slots
  (`vehicle_term`, `description`, `date_token`, `date_value`, `period`,
  `odometer_km`, `query`, `query_kind`, `query_limit`, `edit_field`, `new_value`)
  — restrição do CLAUDE.md. Contrato JSON completo em §9.2 (o LLM nunca calcula
  datas — emite tokens fechados resolvidos em Python).
- Saída **JSON parseada com `json.loads()`** (padrão dos graphs novos: smart-home e
  music). Prompt com aspas retas obrigatórias. Temperatura **0.1** no classificador.
- Desambiguação ("Mitsubishi" → 2 veículos), veículo não cadastrado e escolha de
  candidato são decididos **em Python** no classify/handlers, não pelo LLM — espelho
  do `select_player` do `MusicGraph` (`music_graph.py:109-131`): o LLM sugere
  `vehicle_term`, o código resolve.
- `vehicle_write_forbidden`: node **determinístico, sem LLM**, retorna a string fixa.
- Padrão de construção: `MusicGraph` (contexto dinâmico `{available_vehicles}` no
  prompt) + `OnlyTalkGraph` (injeção de `get_session_history` para leitura de histórico).

### 2.3 Multi-turno: short-circuit determinístico via `PendingMaintenanceFlow`

**Decisão consolidada** (o arquiteto propôs short-circuit determinístico; o
especialista-de-prompt propôs hint no prompt do MainGraph — adotamos o
**short-circuit**, que segue o precedente já existente do disambiguation do shopping
list em `llm_app_service.py:109-118`, é mais barato e determinístico. A preocupação
do especialista — usuário abandonar o fluxo — é resolvida pela regra de fallthrough
do item 3 abaixo):

1. Quando faltam slots, há ambiguidade de veículo ou delete pende de confirmação, o
   graph grava um `PendingMaintenanceFlow` (via `MaintenanceFlowService`, chave
   `maintenance_flow:{user_id}`, TTL curto — análogo a `disambiguation_ttl_seconds`)
   e retorna a pergunta do próximo slot (um por vez: veículo → data → km).
2. No turno seguinte, `LlmAppService.chat()` verifica o pending **antes** do MainGraph
   e consome a resposta **deterministicamente, sem LLM**: km = extração numérica;
   data = parser pequeno no domínio ("hoje", "ontem", `dd/mm/aaaa`); veículo =
   `find_vehicles_by_term`; confirmação = sim/não + `_CANCEL_WORDS`; escolha de
   candidato = ordinais/nome (reuso da lógica do `DisambiguationService.resolve_choice`).
3. Se a resposta **não parseia** como o slot esperado, limpa o pending e deixa a
   mensagem seguir o fluxo normal (MainGraph) — comportamento idêntico a
   `llm_app_service.py:215-218`. Isso cobre o abandono do fluxo
   ("deixa pra lá, acende a luz da sala").
4. Ordem de verificação no `chat()`: disambiguation do shopping list (existente) →
   maintenance flow. Na prática só um estará pendente (TTLs curtos).

Datas são resolvidas **deterministicamente no domínio** (`date_resolver.py`, §9.2)
— o LLM nunca faz aritmética de calendário, nem para "ontem": emite tokens fechados
(`date_token`/`period`) ou transcreve a data ditada (`date_value`). `{current_date}`
continua injetada no prompt (precedente: `OnlyTalkGraph._format_system`), mas apenas
para interpretar contexto/histórico — nunca como insumo de cálculo pelo modelo.
O "parser pequeno no domínio" do slot-filling (item 2 acima) é o **mesmo**
`date_resolver.py`, não um segundo parser.

### 2.4 Regra "escrita de veículo via chat é proibida" — defesa em 3 níveis

A garantia real é **arquitetural**, não de prompt:

1. **Estrutural (ISP):** o `VehicleMaintenanceGraph` recebe apenas
   `VehicleReadRepository`. O `VehicleRepository` completo (escrita) só é injetado no
   `VehicleAppService` pela `ioc.py`. Mesmo com prompt injection perfeito, **não
   existe código alcançável pelo chat que escreva em veículos**.
2. **Graph:** intent `vehicle_write_forbidden` → node determinístico com a string fixa
   "Não tenho permissão para realizar esta operação".
3. **Prompt:** o classificador distingue "adicione o Pajero aos meus carros"
   (forbidden) de "adicione a troca de óleo do Pajero" (register_maintenance).

### 2.5 EX3 vs EX4 do sketch — quem responde "veículo não cadastrado"

- **EX3** ("troquei o câmbio do Porsche", comentário sem pedido explícito, veículo
  não cadastrado) → o **MainGraph** classifica `only_talking`. Para isso o
  classificador precisa conhecer os veículos: `LlmAppService.chat()` carrega os nomes
  (query SQLite barata) em `context_hints["user_vehicles"]`, injetado no
  `main_graph.md` como `Contexto de veículos: {user_vehicles}` — mesmo precedente do
  probe do Music Assistant (`music_is_playing`).
- **EX4** (pedido **explícito** de registro com veículo inexistente) → roteia para o
  graph, que resolve `vehicle_term`, encontra 0 matches e responde
  "Você não tem nenhum veículo {termo} cadastrado." — decidido em Python.

### 2.6 Follow-up "E do pajero?" (MainGraph)

Regra no `main_graph.md`: follow-up curto citando um veículo cadastrado
(`{user_vehicles}`) após interação de manutenção → `vehicle_maintenance`.
Dentro do graph, o histórico injetado (últimos ~6 turnos via `get_session_history`,
**read-only** — persistência continua centralizada em `LlmAppService._persist_turn()`)
permite ao classify herdar a query anterior trocando o veículo; se o assunto anterior
não for recuperável, `query` sai vazia e o handler pergunta
"O que deseja saber sobre o Mitsubishi Pajero?".

### 2.7 "Registro em foco" para edit/delete

`edit_maintenance`/`delete_maintenance` dependem do registro citado no turno anterior
("altere a km desse registro"): quando `query_maintenance` responder sobre um registro
específico, persistir o `record_id` no `PendingMaintenanceFlow` (ou chave
`maintenance_context:{user_id}`) com TTL. Remoção sempre com `operation="delete_confirm"`
e confirmação sim/não.

### 2.8 Decisões de domínio (levantadas pelo programador-tester, resolvidas)

| Decisão | Resolução |
|---|---|
| Delete de veículo com manutenções | **Cascata implementada no `VehicleService.delete`** (não confiar no SQLite — ver §4.1) |
| Data futura em `MaintenanceRecord` | **Proibida** (`validate_performed_at`: manutenção realizada não pode estar no futuro) |
| Unicidade de nome de veículo | **Por usuário** (`UNIQUE(user_id, name)` + checagem no service, padrão `ShoppingListService.add`) |
| Quilometragem | `odometer_km > 0`; ano do veículo em faixa plausível (1950 – ano atual + 1) |
| Ownership | Toda query parte de `get_all_by_user_id(user.id)`; services validam ownership do veículo. Usuário A nunca vê veículo do usuário B |

---

## 3. Camada Domain

### 3.1 Entidades — `src/domain/entities.py`

```python
@dataclass
class Vehicle(BaseEntity):          # id UUID via BaseEntity (regra do projeto)
    user_id: str = ""
    name: str = ""
    brand: str = ""
    model: str = ""
    year: Optional[int] = None

@dataclass
class MaintenanceRecord(BaseEntity):
    vehicle_id: str = ""
    description: str = ""
    performed_at: Optional[date] = None
    odometer_km: Optional[int] = None

@dataclass
class PendingMaintenanceFlow:       # espelho do PendingDisambiguation existente
    operation: str = ""             # "register" | "edit" | "delete_confirm" | "choose_vehicle"
    slots: dict = field(default_factory=dict)
    missing_slots: List[str] = field(default_factory=list)
    candidates: List[DisambiguationCandidate] = field(default_factory=list)  # reuso
    expires_at: float = 0.0
```

### 3.2 Commands — `src/domain/commands.py`

`VehicleAdd`, `VehicleUpdate`, `MaintenanceRecordAdd`, `MaintenanceRecordUpdate`
(padrão `<Entidade><Acao>`; commands de vehicle usados diretamente como request body
nas rotas, como `UserAdd` em `routes.py:95`).

### 3.3 Interfaces — novo `src/domain/interfaces/vehicle_repository.py`

```python
class VehicleReadRepository(ABC):
    get_by_id(vehicle_id) -> Optional[Vehicle]
    get_all_by_user_id(user_id) -> List[Vehicle]

class VehicleRepository(VehicleReadRepository):   # escrita: só REST (ISP, §2.4)
    add(vehicle) / update(vehicle) / delete(vehicle_id)

class MaintenanceRecordRepository(ABC):
    add(record) / get_by_id(record_id)
    get_all_by_vehicle_id(vehicle_id, limit=None)  # ordenado por performed_at DESC
    update(record) / delete(record_id)
```

### 3.4 Domain Services — `src/domain/services/`

| Service | Responsabilidade |
|---|---|
| `vehicle_service.py` — `VehicleService` | CRUD com validação + duplicidade `user_id+name` + `find_vehicles_by_term(term, vehicles)` (§3.6) |
| `maintenance_service.py` — `MaintenanceService` | `register`, `update`, `delete`, `get_last_by_vehicle(vehicle_id, count)`; valida existência do veículo (recebe `VehicleReadRepository`) |
| `maintenance_flow_service.py` — `MaintenanceFlowService` | Persiste/resolve o `PendingMaintenanceFlow` no `ContextRepository` (`maintenance_flow:{user_id}`, TTL no payload). Cópia estrutural do `DisambiguationService` — **não** estendê-lo (é acoplado ao shopping list; SRP) |
| `text_matching.py` (refatoração) | Extrair `_normalize`/`_name_tokens` de `shopping_list_service.py:30-52` + ordinais/`_CANCEL_WORDS`/`_parse_ordinal`. Corrige o acoplamento lateral atual (`DisambiguationService` importa `_normalize` do shopping list). `shopping_list_service` mantém re-export para compat. **Inclui as guardas de comprimento de §9.3** (ordinal/cancel só em mensagem curta), com backport ao `DisambiguationService` |
| `date_resolver.py` (novo) | Resolvedor determinístico de datas/períodos (`resolve_date_token`, `parse_explicit_date`, `resolve_period`) — especificação em §9.2. Puro stdlib (`datetime`/`calendar`), sem estado |

### 3.5 Validators — `src/domain/validations/` (fluent, `.validate()` final obrigatório)

- `vehicle_validation.py` — `VehicleValidator`: `validate_id` (uuid4),
  `validate_user_id`, `validate_name`, `validate_year` (1950 – ano atual + 1).
- `maintenance_record_validation.py` — `MaintenanceRecordValidator`: `validate_id`,
  `validate_vehicle_id`, `validate_description`, `validate_performed_at` (não futura),
  `validate_odometer_km` (> 0).

Chamados nos domain services, nunca nos app services. **Não repetir o bug conhecido**
(delete/check sem `.validate()` final).

### 3.6 Resolução fuzzy de nome de veículo

Adaptar as 3 camadas de `ShoppingListService.find_items_by_name`
(`shopping_list_service.py:120-170`: exato normalizado → subset de tokens → difflib
≥ 0.8 com comprimento mínimo 4) em `VehicleService.find_vehicles_by_term`, com match
contra múltiplos campos: `name`, `brand`, `model` e `"{brand} {model}"`.

- "pajerão" → difflib ratio("pajerao", "pajero") ≈ 0.92 → match.
- "Mitsubishi" → casa `brand` de 2 veículos → `PendingMaintenanceFlow(operation="choose_vehicle")`
  + pergunta; escolha do turno seguinte reusa ordinais/nome do `resolve_choice`.
- 0 matches + pedido explícito → "Você não tem nenhum veículo {termo} cadastrado."

---

## 4. Camada Infra

### 4.1 SQLite — `src/infra/data/sqlite/`

`sqlite_vehicle_repository.py` e `sqlite_maintenance_record_repository.py`, herdando
`SqliteBaseRepository` (padrão `sqlite_shopping_list_repository.py`):

```sql
CREATE TABLE IF NOT EXISTS vehicles (
    id TEXT PRIMARY KEY,                -- UUID (regra do projeto)
    user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    brand TEXT, model TEXT, year INTEGER,
    when_created TIMESTAMP, when_updated TIMESTAMP DEFAULT NULL, when_deleted TIMESTAMP DEFAULT NULL,
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS maintenance_records (
    id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL REFERENCES vehicles(id),
    description TEXT NOT NULL,
    performed_at DATE NOT NULL,
    odometer_km INTEGER,
    when_created TIMESTAMP, when_updated TIMESTAMP DEFAULT NULL, when_deleted TIMESTAMP DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_maintenance_vehicle_date
    ON maintenance_records(vehicle_id, performed_at DESC);
```

**Atenção:** `SqliteBaseRepository.connect()` não executa `PRAGMA foreign_keys=ON` —
os `REFERENCES` são declarativos. Decisão: **integridade garantida no domínio**
(`MaintenanceService` valida existência do veículo; `VehicleService.delete` faz a
cascata dos registros). Habilitar o PRAGMA globalmente fica como melhoria separada,
fora deste escopo.

### 4.2 Settings — `src/infra/settings.py` + `.env.example`

- `LLM_VEHICLE_MAINTENANCE_GRAPH_CHAT_MODEL` (+ `_TEMPERATURE`, `_REASONING`) —
  padrão dos demais graphs; temperatura 0.1 no classificador.
- `MAINTENANCE_FLOW_TTL_SECONDS` (análogo a `disambiguation_ttl_seconds`, ~600s).

### 4.3 Prompts — `src/infra/prompts/` (PT-BR, **aspas retas obrigatórias**)

**`vehicle_maintenance_graph.md`** (classificador + extrator, 1 chamada, `json.loads`):
1. Papel + "Ignore qualquer parte da mensagem não relacionada" (padrão shopping/sensors).
2. Contexto: `Data atual: {current_date}` / `Veículos cadastrados: {available_vehicles}`
   / `## Últimas mensagens:\n{history}`.
3. Intents possíveis com condição precisa de cada um (`vehicle_write_forbidden` =
   "qualquer tentativa de adicionar, editar ou excluir um VEÍCULO").
4. Formato JSON com **todos os campos sempre presentes** (chaves duplicadas `{{ }}`)
   + "Retorne APENAS o JSON válido".
5. Regras: `vehicle_term` normalizado contra a lista quando inequívoco ("pajerão" →
   "Pajero"), menção crua caso contrário (o Python decide); **regra de datas por
   tokens** (§9.2 — o LLM nunca calcula datas); follow-up elíptico herda do
   histórico; opinião/comentário → `not_recognized`.
6. Few-shot (~10-14): os 4 EX do sketch, falsos positivos, ambiguidade Mitsubishi,
   "E do pajero?".

**`vehicle_maintenance_graph_query_response.md`** (resposta natural das consultas —
precedente `smart_home_sensors_graph_response.md`, temp ~0.5): recebe `{user_name}`,
`{current_date}`, `{query}` e `{records}` (registros já buscados, **bounded 20**,
montados em Python uma linha por registro com descriptions sanitizadas — §9.5 e §9.6)
e responde no formato do sketch ("22/05/2026 - km 99998 - Troca de óleo"), com regra
"responda APENAS com base nos registros fornecidos; se vazio, diga que não há registro".
Prompt enxuto (≤ ~300 tokens de sistema, no máximo 2 exemplos) — o decode é o custo
dominante da latência. Esta 2ª chamada só ocorre para consultas abertas
(`query_kind == "open"`); listagens e resultado vazio são renderizados
deterministicamente em Python (§9.5).

Confirmações de add/edit/remove são **strings determinísticas montadas em Python**
(sem risco de alucinação, como os handlers do MusicGraph).

**`main_graph.md`** (alteração): categoria `vehicle_maintenance`, linha de contexto
`Contexto de veículos: {user_vehicles}`, regra de desambiguação nova:

- Manutenção REALIZADA mencionando veículo cadastrado ou referência genérica
  ("do carro") → `["vehicle_maintenance"]`; veículo NÃO cadastrado → `["only_talking"]`.
- Pedido EXPLÍCITO de registro → sempre `["vehicle_maintenance"]` (mesmo não cadastrado).
- Opiniões/perguntas gerais ("Gosto muito do meu Outlander", "O Outlander dá muita
  manutenção?", "Quanto custa a revisão do Pajero?") → `["only_talking"]`.
- Tentativa de cadastrar/editar/excluir veículo → `["vehicle_maintenance"]` (o
  subgraph nega — não resolver a negação no MainGraph).
- Follow-up curto citando veículo cadastrado após interação de manutenção →
  `["vehicle_maintenance"]`.

Few-shot com os pares críticos (entrada → saída), como faz o `shopping_list_graph.md`.

---

## 5. Camada Application

### 5.1 `src/application/graphs/vehicle_maintenance_graph.py`

```python
def __init__(self, llm_chat,
             vehicle_read_repository: VehicleReadRepository,   # nunca o de escrita
             maintenance_service: MaintenanceService,
             maintenance_flow_service: MaintenanceFlowService,
             vehicle_service: VehicleService,                  # find_vehicles_by_term
             get_session_history=None,                         # leitura, p/ follow-ups
             provider="OLLAMA", strip_think_directive=False)
```

- Compilação cacheada em `self._compiled_graph`; `invoke(GraphInvokeRequest) -> dict`.
- Acesso async via `infra.async_runner.run` (como `ShoppingListGraph._store_disambiguation`)
  — **nunca** novos `asyncio.run()` em nós de graph.
- `query_maintenance`: resolve veículo → carrega registros (bounded) → 2ª chamada LLM
  com o prompt de resposta.

### 5.2 `src/application/graphs/main_graph.py`

Campo `output_vehicle` no `MainGraphState`, node `"vehicle_maintenance"`, handler
`_handle_vehicle_maintenance`, parâmetro no construtor (opcional `=None` como
`music_graph` — mas wired sempre, não é integração externa opcional) e inclusão nos
`outputs` do `_handle_final_response` — espelho de `_handle_shopping_list`.

### 5.3 `src/application/appservices/`

- `vehicle_app_service.py` — `VehicleAppService`: CRUD de veículos + leitura de
  manutenções por veículo (auditoria via REST). `auto_map(entity, VehicleResponse)`,
  padrão `ShoppingListAppService`.
- `llm_app_service.py` — duas mudanças:
  1. `context_hints["user_vehicles"]` (nomes dos veículos do usuário, query barata).
  2. Short-circuit do `MaintenanceFlowService` antes do MainGraph (§2.3), após o
     disambiguation existente.
- `view_models.py` — `VehicleResponse`, `MaintenanceRecordResponse`.

---

## 6. Camada API — `src/routes.py`

```
GET    /user/{id}/vehicle             → veículos do usuário (precedente: /user/{id}/memory)
GET    /vehicle/{id}
POST   /vehicle                       → body: VehicleAdd    → {"vehicle_id": uuid}
PUT    /vehicle                       → body: VehicleUpdate
DELETE /vehicle/{id}
GET    /vehicle/{id}/maintenance      → List[MaintenanceRecordResponse]
```

Rotas só delegam; dependências via `Depends(get_vehicle_app_service)`.

**Todas as rotas (novas e existentes, exceto `/health`) passam a exigir API key via
header `X-API-Key`** — resolução do débito SEC-001 nesta feature, com modo de
migração (key vazia = aberto + warning). Especificação completa em §9.6.

### IoC — `src/infra/ioc.py`

Factories novas (com cache `_repo_cache` como as demais): `get_vehicle_repository`,
`get_maintenance_record_repository`, `get_vehicle_service`, `get_maintenance_service`,
`get_maintenance_flow_service`, `get_vehicle_maintenance_graph`, `get_vehicle_app_service`;
wiring no `get_main_graph` e no `get_llm_app_service`.

---

## 7. Estratégia de testes (TDD estrito — testes antes de qualquer implementação)

Padrões obrigatórios: `unittest.mock` puro; sem `pytest-asyncio`
(`run_until_complete`); helpers `_make_repo()`/`_sample_*()`/`_make_graph()`;
nomenclatura `test_<unidade>__<cenário>__<resultado>`; Arrange/Act/Assert.

### Fase 1 — Domain (RED primeiro)

| Arquivo de teste | Template | Casos críticos |
|---|---|---|
| `test_vehicle_validation.py` | `test_shopping_list_item_validation.py` | id/user_id uuid; name vazio/whitespace; year fora da faixa (1950 – atual+1) |
| `test_maintenance_record_validation.py` | idem | description vazia; km ≤ 0/não-numérico; **data futura → erro** |
| `test_text_matching.py` | novo | normalize/tokens/ordinais extraídos; regressão do shopping list intacta; **guardas de comprimento** (ordinal em mensagem longa → None; cancel word em mensagem longa → não cancela) |
| `test_date_resolver.py` | novo | referências fixas forçando borrows: `ref=2026-07-05` (semana cruzando mês), `ref=2026-01-01` (borrow de ano), `ref=2024-03-01` (bissexto), `ref=2026-03-01` (não bissexto); `parse_explicit_date` com "21/12" + ref jul/2026 → 2025-12-21 (never-future); "31/02" → None; tokens desconhecidos → None (§9.2) |
| `test_vehicle_service.py` | `test_user_service.py` | UUID no add (`uuid.UUID(added.id)`); duplicado por user raise / mesmo nome outro user passa; update/delete not-found; **delete com manutenções → cascata**; `find_vehicles_by_term`: "outlander" match, "mitsubishi" → 2 candidatos, "Porche" → vazio sem raise |
| `test_maintenance_service.py` | idem | vehicle_id inexistente raise; km/data inválidos; `get_last_by_vehicle` ordenado desc + limit; ownership |
| `test_maintenance_flow_service.py` | `test_disambiguation_service` (padrão) | set/get/consume/TTL; `parse_slot_reply` por tipo de slot com as regras conservadoras de §9.3 (lista completa de ~21 testes nomeados lá): km com filler/`"98 mil"`/dois números → none/"coloca 3 leites na lista" → none; data futura → invalid (mantém pending); correção "na verdade foi ontem"; confirmação mista → none; pending expirado limpo |

### Fase 2 — Application (app service + rotas)

| Arquivo | Template | Casos críticos |
|---|---|---|
| `test_vehicle_app_service.py` | `test_shopping_list_app_service.py` | mapeamento `VehicleResponse`; `EmptyParamValidationError`; **isolamento por user_id** (`assert_called_once_with(user_id=...)`) |
| `test_vehicle_routes.py` | `test_routes_chat_schedules_memory.py` (chamada direta com mocks) | delegação correta; 404-path quando None |
| `test_llm_app_service_maintenance_flow.py` | testes existentes do disambiguation short-circuit | pending consumido antes do MainGraph (`main_graph.invoke` `assert_not_called`); fallthrough preserva a mensagem original intacta ao MainGraph; delete_confirm com mensagem mista → registro NÃO deletado; pending expirado → nenhum registro criado; turno consumido persiste em `_persist_turn`; `context_hints["user_vehicles"]` populado (lista de testes em §9.3) |
| `test_api_key_security.py` + `test_routes_require_api_key.py` | novo (TestClient + `dependency_overrides`) | key vazia → passa (migração); header ausente/errado → 401; key certa → 200; `/health` sempre público; cada rota `/vehicle` pina o 401 (§9.6) |
| `test_prompt_sanitizer.py` | novo (extração do M-01) | colapso de newlines/whitespace; truncamento; payload de injection vira uma linha inerte; `{records}` montado uma linha por registro (§9.6) |

### Fase 3 — Graph (unit, LLM mockado)

| Arquivo | Template | Casos críticos |
|---|---|---|
| `test_vehicle_maintenance_graph_classify_intent.py` | `test_smart_home_sensors_graph_classify_intent.py` (com `skipif` de import p/ RED limpo) | cada intent; slots extraídos em 1 chamada; JSON inválido/vazio/markdown fences → `not_recognized`; mock via `graph._remove_thinking_tag` ou `llm_chat.return_value = MagicMock(content=...)`; `load_prompt` patchado com `"{input}"` |
| `test_vehicle_maintenance_graph_handlers.py` | `test_shopping_list_graph_handlers.py` | list 2/0 veículos; add com veículo inexistente → "Você não tem nenhum veículo Porche cadastrado" **e `add` não chamado**; ambíguo → pergunta **e `add` não chamado**; `vehicle_write_forbidden` → string fixa **e `vehicle_service` de escrita nunca chamado** (`assert_not_called`); delete pede confirmação |
| `test_main_graph_classify_intent.py` (estender) | `test_main_graph_music.py` | `'["vehicle_maintenance"]'` roteia para o sub-graph mock; wiring no `final_response`; **fallback**: sub-graph retorna `intent == ["not_recognized"]` → `only_talk_graph.invoke` chamado e output do fallback usado; intent real → OnlyTalk `assert_not_called` (§9.1) |

### Fase 4 — Infra (integração sem Ollama) + IoC

| Arquivo | Template | Casos críticos |
|---|---|---|
| `test_sqlite_vehicle_repositories.py` (integração) | `test_sqlite_repositories.py` + fixture `integration_db_path` | roundtrip; **user A não vê veículo de user B**; `UNIQUE(user_id,name)`; ordenação por data desc; delete cascata (comportamento pinado) |
| `test_ioc_vehicle.py` | `test_ioc_sqlite_repo_cache.py` | factories cacheadas; graph recebe **apenas** o read repository |

### Fase 5 — Integração com LLM real (última; requer Ollama; validação de prompt, não gate de TDD)

`test_llm_app_service_chat__vehicle_maintenance_graph.py` (template
`test_llm_app_service_chat__main_graph.py`):
- Fixture `integration_vehicles` (Outlander + Pajero para o `integration_user`) +
  `LLM_VEHICLE_MAINTENANCE_GRAPH_CHAT_MODEL` no `INTEGRATION_ENV`.
- **Baterias B1/B2/B3 com critério de aceite mensurável** — especificação completa,
  frases e processo de iteração em §9.1.
- Sub-bateria de datas (~8 frases) assertando os campos `date_token`/`date_value`/
  `period` do JSON do classify — §9.2.
- Negação de escrita: "cadastre meu carro novo", "apague o Pajero" → output contém
  "Não tenho permissão".
- Medições de latência por cenário com alvos e gatilho de otimização — §9.5.

---

## 8. Fases de implementação (cada fase: testes RED → implementação → verde → refactor)

| Fase | Escopo | Agentes |
|---|---|---|
| **A** | Domain completo: entidades, commands, validators (com os limites de §9.6), `text_matching.py` (refatoração com regressão + guardas de §9.3, backport ao `DisambiguationService`), `date_resolver.py` (§9.2), `VehicleService`, `MaintenanceService`, `MaintenanceFlowService` (com `parse_slot_reply`, §9.3), interfaces | `programador-tester` → `programador` |
| **B** | Infra + API: **B.0** `peruca_api_key: SecretStr` em settings + `.env.example`; **B.1** `infra/security.py` (`require_api_key`); **B.2** split `public_router`/`router` no `app.py` + warning no lifespan + fix CORS `allow_credentials` (§9.6); **B.3+** repositórios SQLite, IoC, `VehicleAppService`, ViewModels, rotas `/vehicle` (herdam a auth automaticamente) | idem |
| **C** | Graph + prompts: `VehicleMaintenanceGraph`, `vehicle_maintenance_graph.md` (contrato de datas por tokens, §9.2), `..._query_response.md` (render determinístico p/ list/vazio, §9.5), wiring no MainGraph **com fallback `not_recognized` → OnlyTalk** (§9.1), `main_graph.md` (regra 10 + few-shot, §9.1), hints e short-circuit no `LlmAppService`, `prompt_sanitizer.py` extraído do M-01 (§9.6) | `especialista-de-prompt` + `programador-tester` → `programador` |
| **D** | Integração LLM real: baterias B1/B2/B3 com gates de aceite (§9.1), sub-bateria de datas (§9.2), medições de latência com alvos (§9.5); ajuste fino de prompts contra o Ollama pelo processo de iteração de §9.1 | `especialista-de-prompt` |
| **E** | Revisão de segurança com checklist objetivo: 401 em todas as rotas não públicas, ownership no caminho do chat, `assert_not_called` do repositório de escrita, sanitização na injeção de prompt (§9.6) | `especialista-de-seguranca` |

**Branch:** a implementação será feita em um **novo feature branch a partir de
`development`** (ex.: `feature/vehicle-maintenance-manager`), conforme o sketch.
Sem commits automáticos — somente quando solicitado.

---

## 9. Riscos e plano de mitigação (detalhado)

Cada risco tem mitigação implementável, com fase de implementação e critério de
aceite. Consultorias: `especialista-de-prompt` (9.1, 9.2), `arquiteto` (9.3–9.5),
`especialista-de-seguranca` (9.6).

Fatos verificados no código que ancoram as decisões:
- `llm_main_graph_chat_temperature` já é **0.1** (`settings.py:52`) — temperatura não
  é alavanca de iteração.
- O MainGraph já tem fallback para `["only_talking"]` em falha de parse
  (`main_graph.py:106,115`); subgraphs retornam o state dict completo (incluindo
  `intent`) no `invoke()`.
- O fallthrough do disambiguation existente **nunca perde a mensagem**: `kind ==
  "none"` limpa o pending, retorna `None` e a mesma `chat_request.message` segue ao
  MainGraph (`llm_app_service.py:215-218`) — comportamento a replicar.
- Todos os deletes SQLite são **hard deletes** (`DELETE FROM`); as colunas
  `when_deleted` são vestigiais (nunca escritas nem filtradas). A "cascata" é
  hard-delete.
- Dois bugs latentes no `DisambiguationService` que **não** devem ser copiados:
  dígito solto em mensagem longa seleciona candidato ("coloca 3 leites na lista" →
  3º candidato); `"para"` em `_CANCEL_WORDS` cancela pendings em frases legítimas.

### 9.1 Risco 1 — Falsos positivos do classificador do MainGraph (Fases C + D)

**Alterações no `main_graph.md`:**

a) Linha de contexto após a de música — `Contexto de veículos cadastrados do
   usuário: {user_vehicles}`, preenchida pelo `LlmAppService.chat()` com lista
   legível (`"Mitsubishi Outlander, Mitsubishi Pajero"`) ou o literal `"nenhum"`
   (nunca string vazia/`[]`).

b) Categoria nova enfatizando **AGIR sobre o histórico**: registrar manutenção
   realizada, consultar/editar/apagar registros, listar veículos, ou tentar
   cadastrar/editar/excluir um veículo.

c) Regra de desambiguação (nova instrução numerada, estilo das regras 2/3/4):
   - RELATO de manutenção REALIZADA em veículo do contexto, ou referência genérica
     ("troquei o óleo do carro") → `["vehicle_maintenance"]`.
   - PEDIDO EXPLÍCITO de registrar/consultar/editar/apagar → `["vehicle_maintenance"]`,
     mesmo com veículo fora do contexto.
   - Tentativa de cadastrar/editar/excluir VEÍCULO → `["vehicle_maintenance"]`.
   - RELATO sobre veículo fora do contexto, sem pedido explícito ("troquei o câmbio
     do Porsche") → `["only_talking"]`.
   - Opiniões, custos hipotéticos, notícias, memórias ("Gosto muito do meu
     Outlander", "O Outlander dá muita manutenção?", "Quanto custa a revisão do
     Pajero?") → `["only_talking"]`. Pergunta hipotética não é consulta ao histórico.
   - Follow-up curto citando veículo do contexto após interação de manutenção
     ("E do Pajero?") → `["vehicle_maintenance"]`.

d) Exemplos inline na regra (estilo das regras 3 e 7), incluindo o contraste crítico
   lado a lado: "O Outlander dá muita manutenção?" (`only_talking`) vs "Quantas
   manutenções do Outlander eu registrei?" (`vehicle_maintenance`), e o multi-intent
   "Acende a luz da garagem e registra a troca de pneus do Pajero" →
   `["smart_home_lights", "vehicle_maintenance"]`.

e) `["vehicle_maintenance"]` na lista do bloco "Formato de saída obrigatório".

**Fallback `not_recognized` → OnlyTalk (torna o falso positivo inofensivo).** No
`_handle_vehicle_maintenance` do MainGraph (não no `LlmAppService` — o app service
não conhece sub-intents, e no node o fallback reaproveita o merge do
`final_response` para multi-intent):

```python
def _handle_vehicle_maintenance(self, data):
    result = self.vehicle_maintenance_graph.invoke(data["input"])
    if result.get("intent") == ["not_recognized"]:
        # Main classifier false positive: degrade to free conversation
        # instead of replying "I did not understand".
        fallback = self.only_talk_graph.invoke(data["input"])
        return {"output_vehicle": fallback.get("output")}
    return {"output_vehicle": result.get("output")}
```

Restrições: só para `== ["not_recognized"]` puro; +1 chamada LLM apenas no caminho
do falso positivo; caminho feliz inalterado; loop impossível (OnlyTalk não
reclassifica). Testes na Fase 3 (§7).

**Critério de aceite mensurável (Fase D)** — três baterias parametrizadas (assert
exato por frase, padrão do `test_llm_app_service_chat__main_graph.py`):

| Bateria | N | Assert | Gate |
|---|---|---|---|
| B1 positiva (registro, consulta, edição, remoção, listagem, negação de escrita; ≥5 frases "com ruído conversacional": "não esquece de anotar que troquei o filtro de ar do Pajero") | 20 | `intents == ["vehicle_maintenance"]` | 100% |
| B2 anti-falso-positivo (opinião, custo hipotético, notícia, memória, veículo não cadastrado sem pedido; incluir de propósito os casos duros "Qual é o intervalo recomendado para troca de óleo?" e "Será que o Outlander aguenta uma viagem de 2 mil km?") | 20 | `intents == ["only_talking"]` | 100% |
| B3 regressão (baterias `only_talking` existentes continuam verdes com `{user_vehicles}` no prompt) | — | — | 100% |

**Processo de iteração quando falhar** (um passo por iteração, bateria completa a
cada passo): 1) ajustar o bullet da regra que cobre o caso falho; 2) adicionar a
frase falha como exemplo inline em contraste par a par; 3) reescrever a descrição da
categoria. **Válvula de escape:** frase que continuar flaky após 1–3 pode ir para
lista `AMBIGUOUS_EXCLUDED` comentada no teste, com justificativa — limite de **2 por
bateria (10%)**; acima disso a Fase D não é aceita e volta para redesenho da regra.
Não mexer em temperatura nem modelo (variáveis globais dos outros domínios).

**Equilíbrio com o falso negativo:** com o fallback, o falso positivo custa apenas
+1 chamada LLM; o falso negativo custa um comando perdido. Regra de desempate ao
escrever o prompt: na dúvida entre relato-com-veículo-cadastrado e opinião,
**preferir `vehicle_maintenance`** — o fallback corrige o excesso; nada corrige a
falta.

### 9.2 Risco 2 — Aritmética de datas no modelo 12b (Fases A + C + D)

**Princípio: o LLM nunca faz aritmética de calendário — nem "ontem"** ("ontem" em
01/07 exige borrow de mês; é exatamente o erro de um 12b). Divisão de
responsabilidade:

| Expressão do usuário | LLM emite | Python resolve |
|---|---|---|
| "hoje" / "ontem" / "anteontem" | `date_token` (enum fechado) | `reference − 0/1/2d` |
| "dia 21/07/2026", "21/07" | `date_value` (**transcrição**, sem aritmética; sem ano → `"--07-21"`) | valida/completa ano (never-future) |
| "semana passada", "neste mês"... | `period` (enum fechado) | `resolve_period()` |
| qualquer outra ("sábado retrasado", "faz umas 3 semanas") | tudo vazio | slot faltante → fluxo multi-turno pergunta a data |

**Contrato JSON do classify** (todos os campos sempre presentes, `json.loads`):

```json
{
  "intents": ["register_maintenance"],
  "vehicle_term": "pajero",
  "description": "troca de oleo",
  "date_token": "",
  "date_value": "2026-07-21",
  "period": "",
  "odometer_km": 100232,
  "query": "",
  "query_kind": "",
  "query_limit": 0,
  "edit_field": "",
  "new_value": ""
}
```

- `date_token` ∈ `{"", "today", "yesterday", "day_before_yesterday"}`; mutuamente
  exclusivo com `date_value` (se o modelo preencher os dois, Python prioriza o token).
- `period` ∈ `{"", "today", "yesterday", "this_week", "last_week", "this_month",
  "last_month", "this_year", "last_year"}`. Valor fora do enum → tratado como `""`
  (nunca propagar string livre do LLM ao resolvedor).
- Range explícito ("entre 01/05 e 30/06") fica fora do escopo: `period: ""`, query
  sem filtro de período — registrar como melhoria futura.
- `query_kind` ∈ `{"", "list", "open"}` — usado pelo skip de latência (§9.5).

**Resolvedor — `src/domain/services/date_resolver.py`** (puro stdlib, módulo de
funções, consumido pelo graph e pelo `MaintenanceFlowService` — parser único):

```python
def resolve_date_token(token: str, reference: date) -> Optional[date]
def parse_explicit_date(text: str, reference: date) -> Optional[date]
    # "dd/mm/yyyy", "dd/mm/aa", "dd/mm" (ano de reference; se resultar futura,
    # recua um ano), "yyyy-mm-dd", "--mm-dd"; None se inválida (ex. 31/02)
def resolve_period(token: str, reference: date) -> Optional[tuple[date, date]]
```

Semântica pinada de `resolve_period` (semana ISO, segunda-feira; `end` dos tokens
`this_*` capado em `reference` — nunca futuro, coerente com `validate_performed_at`):
`this_week` = segunda da semana → reference; `last_week` = segunda−7d → domingo
anterior; `last_month` = dia 1 → último dia do mês anterior; etc. Testes com
referências fixas forçando borrows em §7 (Fase 1).

**Regra e few-shot no `vehicle_maintenance_graph.md`:**

```
⚠️ REGRA DE DATAS: você NUNCA calcula datas. NUNCA converta "ontem", "semana
passada" ou "mês passado" em uma data YYYY-MM-DD — o sistema faz isso.
```

Exemplos essenciais: "Troquei o óleo do Pajero ontem" → `date_token: "yesterday"`;
"dia 21/07/2026" → `date_value: "2026-07-21"`; "dia 12/06" → `date_value: "--06-12"`;
"semana passada" → `period: "last_week"`; **"Troquei o filtro sábado retrasado" →
tudo vazio** (ensina o modelo a não inventar — o sistema perguntará a data).

**Validação (Fase D):** sub-bateria de ~8 frases assertando os campos de data do
JSON do classify (único ponto onde "preferiu o token" é observável; a correção do
calendário já está garantida pelos testes unitários). Gate 100%, mesmo processo de
iteração de §9.1.

### 9.3 Risco 3 — Fallthrough do slot-filling (Fase A)

**Contrato do parser determinístico** (puro, síncrono, sem LLM):

```python
@dataclass
class SlotReplyResult:
    kind: str            # "value" | "skip" | "cancel" | "invalid" | "correction" | "none"
    value: object = None
    corrected_slot: str = ""
    error_message: str = ""   # re-pergunta determinística (kind="invalid")
```

`MaintenanceFlowService.parse_slot_reply(pending, message) -> SlotReplyResult`, com
precedência **cancel > slot esperado > correção de slot já preenchido > none**.

| Cenário | `kind` | Efeito |
|---|---|---|
| Resposta correta do slot | `value` | preenche; re-grava pending + próxima pergunta, ou executa. MainGraph não é invocado |
| Abandono ("acende a luz da sala") | `none` | `clear_pending` + mensagem original segue **intacta** ao MainGraph (idêntico a `llm_app_service.py:215-218`). Slots parciais se perdem — aceito |
| Parece slot mas não é ("coloca 3 leites na lista" com pending de km) | `none` | regras conservadoras abaixo impedem extrair o "3"; item vai para a lista de compras |
| Correção ("na verdade foi ontem" com pending de km) | `correction` | atualiza a data já preenchida, re-pergunta o slot atual |
| TTL expirado | — | `get_pending` purga e retorna `None`; nenhum registro criado com slots velhos |
| Válido sintaticamente, inválido semanticamente (data futura) | `invalid` | **mantém o pending** + `error_message` ("Essa data está no futuro. Quando foi a manutenção?") |
| "não sei/não lembro" no km (opcional) | `skip` | grava sem `odometer_km` |

**Regras conservadoras por slot** — princípio único: *a mensagem inteira deve ser a
resposta do slot*. Tokeniza normalizado, remove filler específico do slot; qualquer
token restante fora do padrão ⇒ `none`:

- **km** (filler: `km, quilometragem, com, a, estava, esta, foi, em, uns, cerca, de,
  mil, o, carro`): exatamente 1 token numérico após remover filler e separadores de
  milhar; mensagem ≤ 6 tokens; `0 < km ≤ 2_000_000`; `"N mil"` → `N*1000`. Aceita
  "estava com 100.232 km", "uns 98 mil"; rejeita "coloca 3 leites na lista", "acho
  que era 100 ou 110".
- **data** (filler: `foi, em, no, dia, na, verdade`): full-match de
  `hoje|ontem|anteontem`, `dd/mm/aaaa`, `dd/mm/aa`, `dd/mm`, `dia N`, `YYYY-MM-DD`
  — via `date_resolver`. Nada de linguagem natural além disso (coerente com §9.2).
  Futura → `invalid`; "amanhã"/"faz umas 3 semanas" → `none`.
- **veículo**: sem regex — `find_vehicles_by_term(message)` com guarda ≤ 5 tokens.
  1 match → `value`; N → re-grava como `choose_vehicle`; 0 → `none` (naturalmente
  seguro para "põe leite na lista").
- **confirmação (`delete_confirm`)** — a mais restritiva (destrutiva): cancela só
  com `não`/cancel-word em mensagem ≤ 3 tokens; confirma só se **todos** os tokens ⊆
  `{sim, pode, apagar, remover, excluir, confirmo, confirmar, ok, claro, isso,
  mesmo, s}` e ≥1 ∈ `{sim, pode, confirmo, ok, claro, s}`. "sim, mas antes acende a
  luz" → `none` → fallthrough **sem deletar** (fallthrough jamais executa operação
  destrutiva).
- **escolha de candidato**: reusa `resolve_choice` via `text_matching.py` **com duas
  guardas novas**: ordinal só em mensagem ≤ 3 tokens de conteúdo; cancel-word só em
  mensagem ≤ 3 tokens. Fecham os dois bugs latentes do `DisambiguationService`
  (dígito em frase longa; `"para"` cancelando). **Backport ao `DisambiguationService`
  no mesmo refactor do `text_matching.py`**, com testes de regressão pinando o novo
  comportamento — é correção de bug real do shopping list, não mudança gratuita
  (pode ser extraído para plano próprio se o escopo mínimo for preferido).

Testes: lista completa (~21 unit no parser + 9 de wiring no `LlmAppService`) mapeada
em §7 — os nomes canônicos incluem
`test_parse_slot_reply__km_shopping_message_with_digit__returns_none`,
`test_chat__pending_delete_confirm_unrelated_message__record_not_deleted`,
`test_chat__pending_expired__message_routes_to_main_graph_and_no_record_created`,
`test_chat__shopping_disambiguation_pending__checked_before_maintenance_flow`.

### 9.4 Risco 4 — FKs SQLite não impostas (Fase A + follow-up separado)

**Fato-base:** não existe soft delete no projeto (todos os repositórios fazem
`DELETE FROM`; `when_deleted` é vestigial). A cascata é **hard-delete, filhos
primeiro**. Não introduzir soft delete nesta feature.

**Ordem de operações** (transação cross-repositório é inviável — cada repositório
tem sua própria connection):

```python
def delete(self, vehicle_id: str, user_id: str) -> None:
    VehicleValidator().validate_id(vehicle_id).validate()
    vehicle = self.vehicle_repository.get_by_id(vehicle_id)
    if not vehicle or vehicle.user_id != user_id:
        raise NofFoundValidationError(...)
    self.maintenance_record_repository.delete_all_by_vehicle_id(vehicle_id)  # children first
    self.vehicle_repository.delete(vehicle_id)                               # then parent
```

- Novo método de interface: `MaintenanceRecordRepository.delete_all_by_vehicle_id`
  (um único `DELETE ... WHERE vehicle_id = ?`, atômico em `with self.conn:`).
- **Invariante:** nunca existir registro sem veículo. Falha entre os passos deixa
  "veículo sem registros" (íntegro; reexecutar o DELETE conclui). Ordem inversa
  criaria órfãos irreparáveis — proibida. Teste verifica a **ordem** via
  `MagicMock.mock_calls`.
- `MaintenanceService.register/update` valida existência + ownership antes do add.
  Race residual (delete REST entre checagem e insert): janela minúscula,
  single-process, e órfão eventual é inalcançável (toda leitura parte do veículo);
  o PRAGMA fecha definitivamente.
- **Pending flow vs delete REST:** consumação re-valida a existência; em NotFound →
  "Esse veículo não está mais cadastrado." + `clear_pending`
  (`test_chat__pending_register_vehicle_deleted_meanwhile__clears_pending_and_informs`).

**Follow-up separado (`PRAGMA foreign_keys=ON`)** — por que não agora: o PRAGMA é
por conexão e ligaria a imposição para todas as tabelas; `SqliteUserRepository.delete`
passaria a falhar (`IntegrityError`) para usuários com `user_memories`/`vehicles` —
mudança de comportamento fora do escopo, sem testes pinando. Plano da melhoria
(novo arquivo em `todo/` quando priorizada): 1) `PRAGMA foreign_key_check` no banco
de produção + limpeza de órfãos; 2) mapear `REFERENCES` e decidir política por FK
(mudar exige table-rebuild); 3) cascatas de domínio faltantes (`UserService.delete`
→ memories → vehicles → records); 4) uma linha no `SqliteBaseRepository.connect()`;
5) testes de integração pinando `IntegrityError`.

### 9.5 Risco 5 — Latência do `query_maintenance` (Fases C + D)

**Baseline:** o sensors gasta até **4** chamadas LLM (MainGraph + classify +
id-parser LLM + response); o vehicle graph resolve veículo em Python, então o pior
caso é **3**. Com gemma4 sem thinking (~1,5–2,5s/chamada, modelo residente):
expectativa ~6–8s pior caso, alvo ≤ sensors atual.

**Mitigações (Fase C):**

1. **Skip determinístico da 2ª chamada** em `_handle_query_maintenance`:
   `records == []` → string fixa em Python (0 chamadas extras);
   `query_kind == "list"` (já emitido no MESMO JSON do classify) → render
   determinístico no formato do sketch (`"{dd/mm/yyyy} - km {km} - {description}"`)
   — cobre "as 2 últimas manutenções?" com **2 chamadas totais**;
   `query_kind == "open"` ("quando troquei o óleo?") → única rota com a 2ª chamada.
2. **Bounded records = 20** com limit no SQL (índice `idx_maintenance_vehicle_date`);
   filtros de período aplicados no SQL, não pós-carga; serialização 1 linha/registro
   (~400 tokens de prefill).
3. **Prompt de resposta enxuto** (≤ ~300 tokens de sistema, ≤ 2 exemplos, instrução
   de resposta curta — decode é o custo dominante).
4. **Reuso da infra de perf** (nada a implementar, pinar):
   `keep_alive=-1`/`num_ctx=8192` já globais;
   `LLM_VEHICLE_MAINTENANCE_GRAPH_CHAT_MODEL` **deve defaultar para o mesmo modelo
   dos demais graphs** (modelo diferente força swap de VRAM a cada mensagem).
5. MainGraph já pula o merge com ≤1 output — consulta single-intent não paga o
   LLM call #2 do MainGraph.

**Medição (Fase D)** — `time.perf_counter` + `logger.info` por nó e end-to-end,
mediana de ≥5 execuções, modelo residente:

| Cenário | Caminho | Alvo |
|---|---|---|
| "quais as 2 últimas manutenções do pajero?" | list → 2 chamadas | ≈ comando de shopping list |
| "quando troquei o óleo?" | open → 3 chamadas | ≤ consulta equivalente do sensors, medida na mesma sessão |
| turno de slot-filling ("100232") | 0 chamadas | < 100 ms |
| registro completo em 1 turno | 2 chamadas | ≈ shopping list add |

**Gatilho de otimização adicional:** mediana do caminho "open" > 8s ou > 1,5× o
baseline do sensors. Próximas alavancas (documentar, não implementar): responder
"quando troquei X" deterministicamente via match de tokens na description; fundir
resposta no classify. Fora disso, aceitar e fechar o risco.

### 9.6 Risco 6 — Segurança: SEC-001 e correlatos (Fases A + B + C + E)

**Escopo: resolver o SEC-001 inteiro nesta feature, não só as rotas novas.**
Proteger apenas `/vehicle` seria incoerente e daria segurança ~zero (o atacante
leria os mesmos veículos via `POST /llm/chat` aberto). Como a proteção é uma única
dependência no nível do router, o custo é idêntico.

**M-SEC-1 — API key estática `X-API-Key`** (adequada ao contexto doméstico;
OAuth/JWT seria overengineering). Wiring em 3 arquivos:

1. `settings.py`: `peruca_api_key: SecretStr = SecretStr("")` (env `PERUCA_API_KEY`;
   `SecretStr` evita vazar em logs/repr).
2. Novo `src/infra/security.py`:

```python
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def require_api_key(provided: str | None = Security(_api_key_header)) -> None:
    expected = Settings().peruca_api_key.get_secret_value()
    if not expected:
        return  # migration mode: auth not configured (warning at startup)
    if provided is None or not secrets.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
```

   (`APIKeyHeader` dá o cadeado no Swagger; `compare_digest` sobre bytes evita
   timing attack; `Settings()` por request segue o caveat existente da IoC.)
3. `app.py`: split de routers — `public_router` (apenas `GET /health`, sem auth) e
   `app.include_router(router, dependencies=[Depends(require_api_key)])` cobrindo
   todo o resto, incluindo as rotas novas, sem tocar assinatura de função. Warning
   único no `lifespan` quando a key está vazia.

**Migração em 3 passos:** (1) nesta feature, key opcional — vazia = comportamento
atual + WARNING; preenchida = 401 em tudo exceto `/health`; zero quebra para as
automações HA. (2) Operador gera a key (`secrets.token_urlsafe(32)`), define no
`.env` e adiciona o header nos `rest_command` do HA / Node-RED (`PERUCA_API_KEY=`
documentada no `.env.example`). (3) Follow-up separado: tornar obrigatória (falha
no startup se vazia) — não agora, para não acoplar o deploy à reconfiguração do HA.

**Correlato incluído (SEC-003, 1 linha):** `allow_origins=["*"]` +
`allow_credentials=True` anula a proteção para clientes browser →
`allow_credentials=settings.cors_origin != "*"` em `app.py`.

**M-SEC-2 — IDOR/ownership.** Com key única, quem tem a key é **admin do
household** — modelo de confiança documentado. O ownership por `user_id` continua
obrigatório como fronteira de autorização **no caminho do chat** (entrada não
confiável): `MaintenanceService.register/update/delete/get_last_by_vehicle` validam
`vehicle.user_id == user.id` antes de qualquer operação; nunca confiar em
`vehicle_id`/`record_id` vindos de saída de LLM ou de `PendingMaintenanceFlow` sem
revalidar no consumo (o pending pode ter sido gravado em turno anterior); o
`record_id` do "registro em foco" (§2.7) é revalidado ao ser consumido. No REST:
validar formato UUID do path (400) e 404 uniforme; **não** adicionar header de
identidade por usuário (teatro de segurança sem auth por usuário real).

**M-SEC-3 — Prompt injection em campos livres.** Superfície: não é só
`description` — `name`/`brand`/`model` entram **via REST** e são reinjetados em
`{available_vehicles}`/`{user_vehicles}` (injection persistente no classificador).
Duas camadas, precedente M-01:

- **Na gravação (validators, Fase A):** limites de tamanho, não sanitização
  destrutiva — `description` ≤ 500 chars; `name`/`brand`/`model` ≤ 60 chars.
- **Na injeção (Fase C):** extrair `_sanitize_description` de
  `llm_app_service.py:315` para `sanitize_for_prompt(text, max_chars=500)` em
  `src/application/appservices/prompt_sanitizer.py` (o `llm_app_service` delega).
  Aplicar a cada description ao formatar `{records}` (**truncada em 200 chars na
  injeção** — o dado completo fica no banco; 20 registros × 200 chars mantém o
  prompt dentro do `num_ctx`) e a cada nome em `{available_vehicles}`/
  `{user_vehicles}` (max 60). Whitespace/newlines colapsados ⇒ a injection fica
  confinada a um campo de uma linha, sem forjar registros ou blocos de instrução.
  `{records}` montado em Python, determinístico, uma linha por registro, bloco
  delimitado (`## Registros:`).
- Defesa estrutural já garantida (§2.4): o teste `assert_not_called` do repositório
  de escrita é teste de **segurança**, não só funcional.

**M-SEC-4 — Validação de entrada nas rotas.** Nos validators (padrão do projeto;
erro vira 4xx via handler de `ValidationError` em `app.py:48`): `year` 1950–atual+1;
`odometer_km` > 0 **e ≤ 2_000_000**; `performed_at` não futura **e ≥ 1950-01-01**;
limites de M-SEC-3; `user_id` em `VehicleAdd` deve existir no `UserRepository`
(senão cria veículo órfão invisível); path params UUID validados cedo.

**Ordem e testes:** passos B.0–B.2 no início da Fase B (tabela do §8), rotas
`/vehicle` herdam a auth em B.3+; cada rota nova pina o 401 contra regressão.
Fase E ganha checklist objetivo (tabela do §8).

**Débitos correlatos registrados, fora do escopo:** rate limiting (SEC-005); docs
Swagger expostos (SEC-008 — com key, o Swagger documenta mas não autoriza);
`home_assistant_token`/`llm_provider_api_key` como `str` simples → migrar para
`SecretStr` no follow-up; `max_length` no `ChatRequest.message` (SEC-010).

---

## 10. Alternativas descartadas

- **Dois graphs (vehicle + maintenance):** duplicaria fuzzy matching e estado
  multi-turno; sem os motivos que justificam o split dos smart-home graphs.
- **Slot-filling via hint no prompt do MainGraph** (proposta inicial do
  especialista-de-prompt): mais flexível para abandono de fluxo, mas menos
  determinístico e mais caro (toda resposta de slot passaria por 2+ chamadas LLM);
  o precedente do disambiguation short-circuit já resolve o abandono via fallthrough.
- **Negação de escrita só por prompt:** insuficiente (prompt injection); a garantia é
  estrutural (ISP — graph sem acesso ao repositório de escrita).
- **Estender `DisambiguationService`:** acoplado ao `ShoppingListService`; SRP manda
  criar `MaintenanceFlowService` próprio (reusando `text_matching`).
- **`PRAGMA foreign_keys=ON` agora:** mudança de comportamento global do
  `SqliteBaseRepository`; fica como melhoria separada (plano em §9.4).
- **LLM calculando datas relativas ("ontem" → YYYY-MM-DD):** modelo 12b erra borrow
  de mês/ano; substituído pelo esquema de tokens + `date_resolver.py` (§9.2).
- **Soft delete na cascata de veículo:** o projeto inteiro usa hard delete
  (`when_deleted` é vestigial); introduzir soft delete aqui mudaria o padrão global.
- **OAuth/JWT para a API:** overengineering para rede doméstica com chamadores
  conhecidos; API key estática com `compare_digest` resolve (§9.6).
- **Proteger só as rotas `/vehicle`:** incoerente — os mesmos dados vazariam pelo
  `/llm/chat` aberto; a dependência router-level cobre tudo pelo mesmo custo (§9.6).
- **Header de identidade por usuário no REST:** teatro de segurança sem autenticação
  por usuário real; o modelo de confiança é "key = admin do household" (§9.6).
