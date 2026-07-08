# Plano: Registro de Vacinas e Eventos de Saúde dos Pets

- **Status:** done (Fases 0/A/B/C/D concluídas; E verificada inline)
- **Criado em:** 2026-07-07 15:05
- **Implementado em:** 2026-07-07 (branch `feature/pet-health-events-registry`)
- **PR/commit:** branch `feature/pet-health-events-registry`

> **Progresso da implementação (2026-07-07, branch `feature/pet-health-events-registry`):**
>
> **Fase 0 (refactors) — concluída, TDD.** `find_by_term` genérico extraído para
> `text_matching.py` (com `find_vehicles_by_term` delegando); `FlowStateStore`
> genérico extraído; `PendingMaintenanceFlow` → `PendingFlow` com `flow_domain`
> (+alias de compat). +20 testes; suíte veicular verde (0 regressão).
>
> **Fase A (domínio) — concluída, TDD.** `Pet`/`PetHealthEvent`; commands;
> `PetValidator`/`PetHealthEventValidator`; `PetService` (unicidade sobre a união
> nome+apelidos, cascata filhos-primeiro, `find_pets_by_term`); `PetHealthService`
> (ownership em toda operação, regra evento-antes-do-nascimento); `PetHealthFlowService`
> (slots pet→event_name→date, choose_pet, delete_confirm, loop register_more).
> 120 testes.
>
> **Fase B (infra + REST) — concluída, TDD.** `sqlite_pet_repository` (apelidos JSON,
> ordem preservada) + `sqlite_pet_health_event_repository` (DESC+limit); wrapper ISP
> `ReadOnlyPetRepository`; `PetAppService` + ViewModels + rotas `/pet` (write REST-only);
> settings do graph; factories IoC (chat recebe só o read repo). 26 testes.
>
> **Fase C (graph + orquestração + persona) — concluída, TDD (LLM mockado).**
> `PetHealthGraph` (classify JSON + resolução de pet/data em Python; handlers
> list/register/query/edit/delete/forbidden/not_recognized; cap 20; sanitize);
> prompts `pet_health_graph.md` + `..._query_response.md`; `main_graph.md` (categoria +
> regra 11 + `{user_pets}` + few-shot); persona dinâmica (`only_talk_graph.md` sem
> hardcode + `{siblings}`); `memory_graph.md` (exclui eventos pontuais); wiring MainGraph
> (fallback `not_recognized → only_talk`) + `LlmAppService` (hints `user_pets`/
> `user_pets_persona` + dispatch por `flow_domain` + `_consume_pet_health_flow` com o
> loop register_more). IoC completa. **38 testes; 1461 unitários verdes no total.**
>
> **Fase D (integração LLM) — executada contra Ollama vivo (gemma4:12b, 2026-07-07).**
> `test_llm_app_service_chat__pet_health_graph.py`. Resultado na 1ª rodada, **sem
> iteração de prompt**: B1 positiva 10/10, B2 anti-falso-positivo 10/10 (o guard mais
> crítico, dado que os pets vivem na persona), negação de escrita 3/3, persona dinâmica
> 2/2. **25/25 em 2m31s.**
>
> **Fase E (segurança) — verificada inline** (não houve auditoria formal do
> `especialista-de-seguranca`; recomendada como follow-up). Confirmado
> estruturalmente: (i) todo caminho de chat (graph, `PetHealthService`,
> `LlmAppService`) recebe `ReadOnlyPetRepository` — o `PetRepository`/`PetService`
> completos só existem no `PetAppService` REST; (ii) `query_limit` capado em 20 no
> fetch e no render; (iii) `sanitize_for_prompt` em descrições, apelidos e no bloco de
> persona; (iv) ownership em toda operação; (v) `json.loads` (nunca `eval`);
> (vi) `pet_write_forbidden` responde string fixa sem LLM.
>
> **Divergência do plano registrada — §2.2:** a unificação numa chave única
> `pending_flow:{user_id}` foi **deferida**. Manutenção e pet usam chaves distintas
> (`maintenance_flow:` / `pet_health_flow:`) e o `LlmAppService` faz duas checagens
> sequenciais (manutenção, depois pet). Motivo: unificar a chave exigiria mexer no
> `MaintenanceFlowService` já testado e em produção, com risco desproporcional ao
> ganho; o parser conservador (mismatch → limpa o próprio pending e cai no MainGraph)
> já evita sequestro de conversa. O `flow_domain` existe no dataclass e é persistido,
> deixando a unificação como refactor trivial futuro se necessário.
- **Consultorias realizadas (obrigatórias):** `arquiteto`, `especialista-de-prompt`, `programador-tester`
- **Template arquitetural:** Gestor de Manutenção Veicular (`docs/features/done/2026-07-05-20-31-vehicle-maintenance-manager.md`) — o código é a fonte de verdade, não aquele plano.

---

## 1. Objetivo

Permitir que o Peruca registre e consulte **vacinas e eventos de saúde** (vermífugos,
antipulgas, remédios, consultas veterinárias) dos pets do usuário, via chat, com
slot-filling multi-turno. O **cadastro do pet em si (add/update/delete) é
exclusivamente REST** — nenhum caminho de código alcançável pelo chat pode escrever
um `Pet`, nem sob prompt injection.

### Requisitos do usuário (verbatim)

1. Add/remove de pet só via API; se pedido por chat, Peruca responde que não tem
   permissão.
2. Pet persiste: nome, apelidos (lista; o 1º é o principal), data de nascimento,
   sexo, tipo (cachorro, gato, peixe...), descrição (física/comportamental).
3. Registro e consulta de vacinas/eventos por chat, cobrindo os 4 exemplos:
   - **EX1 (slot-filling):** "o Caçolin tomou vacina hoje" → "qual vacina ele tomou?"
     → "DHPPI" → "Ok, registrei a vacina tomada hoje (27/07/26), DHPPI para o
     Caçolin. Ele tomou mais alguma?" → "Só esta" → "perfeito então".
   - **EX2 (registro direto):** "Adicione a vacina para o Vaniça: 22/05/26 -
     Leptospirose" → registra e confirma (note: "Vaniça" é variação fonética de um
     pet cadastrado — o fuzzy resolve).
   - **EX3 (evento não-vacina):** "o Caçolão tomou o vermifugo bravecto no dia
     12/05/26" → registra vermífugo.
   - **EX4 (consulta com período):** "O Câníça já tomou vacina de gripe canina nesse
     ano?" → "Sim, no dia 20/02/26".
4. Matching de pets considera **nome E apelidos**.

### Decisões do usuário (2026-07-07, via AskUserQuestion)

| Decisão | Escolha |
|---|---|
| Escopo de posse do Pet | **Per-user, como veículos** (`user_id` + ownership validado em toda operação). Alternativa household descartada — ver §10. |
| Datas futuras (agendamento de dose) | **Rejeitar na v1**, como o veicular. "Agendamento/lembrete de reforço" fica como extensão futura. |
| `edit_health_event` na v1 | **Incluído** (espelho completo do veicular, edit sobre o registro em foco). |

### Achado crítico da consultoria de prompt + decisão de persona (2026-07-07)

**Caçolin e Caçolão hoje estão hardcoded na persona do Peruca**
(`infra/prompts/only_talk_graph.md:5-7`, seção "Seus irmãos", com apelidos
Lilo/Caçolinho/Suzu e Lyon). Decisão do usuário: **remover o hardcode e tornar a
persona dinâmica** — o prompt ganha a regra de que *todos os pets cadastrados são
irmãos do Peruca*, e nome, apelidos e descrição de cada pet são injetados no
contexto do `OnlyTalkGraph` a partir do repositório (ver §2.9). A remoção do
hardcode e a injeção dinâmica entram **no mesmo commit** (Fase C) — nunca pode
haver janela em que o Peruca "esqueça" os irmãos.

Conversa casual sobre os pets continua sendo rotina e **não pode ser roubada**
pelo novo graph. A desambiguação `pet_health` vs `only_talking` no MainGraph segue
sendo o ponto mais sensível do design (ver §9.1).

---

## 2. Decisões de design

### 2.1 Fase 0 obrigatória — três generalizações antes de qualquer código de pet

Copiar o template veicular 1:1 criaria três duplicações. Extrair **antes**, em
commits próprios, com a suíte veicular verde após cada refactor:

**(a) `find_by_term` genérico em `domain/services/text_matching.py`.**
`find_vehicles_by_term` (`vehicle_service.py`) é um algoritmo de 3 camadas
(exato normalizado → parcial por tokens → fuzzy difflib ≥ 0.8) onde só
`_searchables()` é específico. Extrair:

```python
find_by_term(term: str, items: List[T], searchables: Callable[[T], List[str]]) -> List[T]
```

`find_vehicles_by_term` vira delegador; o pet usa
`searchables=lambda p: [p.name, *p.nicknames]`. Isso resolve o requisito 4 de
graça — "Câníça"→"Caçolin" cai na normalização de acentos + camada fuzzy.

**(b) `FlowStateStore` (domain/services, Python puro).** As seções "Persistence" e
"Focused record" do `MaintenanceFlowService` são 100% mecânicas (JSON + TTL
embutido + chave por user_id). Extrair um store com construtor
`(context_repository, key_prefix, ttl_seconds)` expondo
`set_pending/get_pending/clear_pending/set_focus/get_focus/clear_focus`.
`MaintenanceFlowService` e o novo `PetHealthFlowService` **compõem** o store e
mantêm cada um seu parser determinístico. **Não generalizar os parsers** — regras
de km não têm análogo em vacina; parser genérico seria abstração especulativa.

**(c) `PendingFlow` com discriminador.** Renomear `PendingMaintenanceFlow` →
`PendingFlow` com campo novo `flow_domain: str` (`"maintenance"` | `"pet_health"`).
Os campos existentes (`operation`, `slots`, `missing_slots`, `candidates`,
`expires_at`) já são genéricos. Migração de dados em voo: TTL ≤ 600s, estados
pendentes simplesmente expiram.

### 2.2 Um único slot de pending com dispatch por domínio (não checagens sequenciais)

Hoje `LlmAppService.chat()` faz: disambiguation → maintenance flow → MainGraph.
Adicionar uma 3ª checagem sequencial criaria (i) leitura extra no ContextRepository
por turno e (ii) dois pendings simultâneos com precedência acidental pela ordem dos
`if`s. Com 2.1(b)+(c): **uma chave única** `pending_flow:{user_id}` — o `chat()` lê
uma vez e despacha pelo `flow_domain` para `_consume_maintenance_flow` ou
`_consume_pet_health_flow`. Gravar um flow novo sobrescreve qualquer outro
(exclusão mútua estrutural — comportamento correto: um flow abandonado nunca
sobrevive a um flow novo). `DisambiguationService` (shopping list) fica **fora**
desta unificação — funciona, tem testes; unificá-lo é refactor separado.

**Dívida registrada:** `llm_app_service.py` já acumula ~200 linhas de consumo de
flow. Se ao final da Fase C a classe estiver god-class, extrair os consumidores
para `application/appservices/flow_consumers/` (um por domínio, assinatura
`consume(user, pending, message) -> Optional[dict]`), injetados no `LlmAppService`.
Não bloqueia a v1.

### 2.3 Sub-intents internos do `PetHealthGraph` (= nomes dos nodes)

| Intent | Ação |
|---|---|
| `list_pets` | Lista pets cadastrados do usuário (render determinístico, sem LLM) |
| `register_health_event` | Registra vacina/vermífugo/antipulgas/remédio/consulta |
| `query_health_event` | Consulta histórico (`query_kind` "list" → render determinístico; "open" → 2ª chamada LLM) |
| `edit_health_event` | Edita o registro em foco (data/descrição) |
| `delete_health_event` | Remove o registro em foco, com turno `delete_confirm` sim/não |
| `pet_write_forbidden` | Cadastrar/editar/excluir um PET → resposta fixa, sem LLM |
| `not_recognized` | Fallback → MainGraph degrada para `only_talk` |

Intent strings devem casar **exatamente** com os nomes dos nodes (o
`intent_router` retorna `state["intent"]` como edge target).

### 2.4 Escrita de pet via chat proibida — defesa em 3 níveis (espelho do veicular)

1. **Estrutural (ISP):** o graph, o `PetHealthService` e o `LlmAppService` recebem
   apenas `PetReadRepository`; o wrapper `ReadOnlyPetRepository` (infra)
   **fisicamente não possui** `add/update/delete`. O `PetRepository` completo é
   reservado ao `PetAppService` (rotas REST).
2. **Comportamental:** intent `pet_write_forbidden` → node com string fixa
   `"Não tenho permissão para realizar esta operação"` (idêntica à veicular), sem
   passar pelo LLM.
3. **Sem porta lateral:** `register_health_event` com pet não encontrado responde
   "você não tem nenhum pet chamado X" — **nunca** oferece criar o pet nem inicia
   flow que colete dados de pet novo. O slot-filling só coleta slots de *evento*.

### 2.5 Multi-turno: slots `pet → event_name → date`, short-circuit determinístico

Mesmo mecanismo do maintenance flow: pending persistido com TTL, consumido no
`LlmAppService.chat()` **antes** do MainGraph, parser conservador — a mensagem
inteira precisa SER a resposta do slot, senão `kind="none"` → limpa o pending e a
mensagem segue o roteamento normal (comando legítimo nunca é engolido).

No EX1, pet e data vêm no 1º turno; falta só `event_name` → "Qual vacina ele tomou?".
Perguntas por slot (geradas em Python, tom do Peruca, formas neutras de gênero —
`sex` existe na entidade, flexionar é extensão): `pet` → "De qual pet estamos
falando?"; `event_name` (vaccine) → "Qual vacina ele tomou?" / (genérico) → "O que
foi aplicado exatamente?"; `date` → "Quando foi?".

**Parser do slot `event_name`** (único slot de texto aberto — km/data eram fechados;
o conservadorismo vem do formato):
1. `is_cancel(message)` → cancela.
2. Normaliza e remove fillers (`a, de, vacina, foi, ele, ela, tomou, o`).
3. Sobram **1–6 tokens** sem cara de comando → `kind="value"` com o texto original
   limpo (preserva "DHPPI").
4. Mais de 6 tokens ou vazio → `kind="none"` → fallthrough ao MainGraph.

### 2.6 O loop "Tomou mais alguma?" (operação nova `register_more`)

Sem análogo veicular. Regra: após registrar com sucesso um evento
`event_type == "vaccine"` **cuja coleta passou pelo flow multi-turno** (EX1), o
node grava `operation="register_more"` com `pet_id/pet_name/date/event_type`
pré-preenchidos e anexa à confirmação: `"Ok, registrei a vacina DHPPI para o
Caçolin, tomada hoje (27/07/2026). Tomou mais alguma?"`. Registro direto e completo
(EX2/EX3) confirma e **encerra** — exatamente como nos exemplos do usuário.

O turno seguinte é resolvido **deterministicamente** (zero LLM) por
`_parse_register_more(message)`:

- **Negativa/limitadora** — tokens ⊆ `{nao, so, esta, essa, apenas, somente, isso,
  nada, obrigado, por, enquanto}` contendo ao menos um de `{nao, so, apenas,
  somente}` (cobre "só esta", "não", "apenas essa", "por enquanto não") →
  `kind="cancel"` → limpa pending, responde `"Perfeito então."`
- **Afirmativa nua** ("sim", "tomou", "aham") → novo flow `register` com pet+data+
  tipo preservados e `missing=["event_name"]` → "Qual outra vacina?" → volta ao
  parser do §2.5. **É assim que o loop itera** — re-arma `register_more` após cada
  registro, até a negativa encerrar.
- **Afirmativa com conteúdo** ("sim, a raiva também", "a de raiva") → remove
  yes-tokens/fillers; o resto (1–6 tokens) é o `event_name` → registra com mesmo
  pet+data → "Anotado. Mais alguma?". (Múltiplas numa resposta — "raiva e giárdia"
  — fica para v1.1; registrar aqui.)
- **`kind="none"`** (mudou de assunto: "liga a luz da sala") → limpa pending,
  mensagem segue ao MainGraph. O TTL cobre abandono.

Racional de "só vacina re-pergunta": vacinas vêm em lote (V8+raiva+gripe no mesmo
dia); vermífugo/remédio confirmam e encerram.

### 2.7 "Registro em foco" para edit/delete

Espelho do veicular: `query_health_event` grava como focus (via `FlowStateStore`)
o registro mais recente reportado; "altere a data desse registro" / "remova este
registro" atuam sobre o focus. `delete_health_event` sempre passa por um turno
`delete_confirm` sim/não (`_parse_confirmation` reusado; "sim, mas antes acende a
luz" → `kind="none"`, **não deleta**). Sem focus válido → resposta pedindo que o
usuário consulte primeiro.

### 2.8 Decisões de domínio consolidadas

- **Data futura rejeitada** em register/edit (decisão do usuário), mensagem própria
  ("ainda não registro doses agendadas"). `date_resolver` reusado **sem mudanças**.
- **Evento antes do nascimento do pet** → `ValidationError` no `PetHealthService`
  (regra cross-entity nova; só se aplica quando `birth_date` existe).
- **Unicidade na origem (REST):** o `PetService` valida colisão normalizada sobre a
  **união** nome+apelidos de todos os pets do usuário — se "Vaniça" for apelido do
  pet A e nome do pet B, o matching do chat fica permanentemente ambíguo. Rejeitar
  no cadastro é barato; desambiguar a cada turno é caro. Mesma colisão entre users
  diferentes → OK.
- **Apelido duplicado dentro do mesmo pet** ou colidindo com o próprio `name` →
  `ValidationError` (não dedup silencioso). Lista de apelidos vazia é válida.
- **`sex`** conjunto fechado `{"male", "female", "unknown"}`; **`species`** texto
  livre não-vazio (o "peixe..." do requisito indica conjunto aberto — Enum forçaria
  migração a cada espécie); **`event_type`** conjunto fechado
  `{"vaccine", "dewormer", "antiparasitic", "medication", "vet_visit", "other"}` +
  `description` livre (permite "já tomou **vacina** de gripe?" filtrar por tipo
  antes do match de descrição).

### 2.9 Persona dinâmica: pets cadastrados = irmãos do Peruca (`only_talk_graph.md`)

Decisão do usuário (2026-07-07):

1. **Remover** de `infra/prompts/only_talk_graph.md` a seção hardcoded "Seus
   irmãos" (Caçolin, Caçolão e apelidos).
2. **Adicionar** ao prompt a regra fixa: *todos os pets cadastrados do usuário são
   seus irmãos* — o Peruca fala deles com o mesmo carinho de antes.
3. **Injetar** dinamicamente no contexto do `OnlyTalkGraph` um bloco `{siblings}`
   com **nome, apelidos e descrição** de cada pet, para que a personalidade tenha
   ciência deles. Formato (uma linha por pet, cada campo via `sanitize_for_prompt`
   — a `description` é texto livre controlável via REST e entra no prompt de
   persona, portanto cap agressivo, ~200 chars):

   ```
   - **Caçolin** (apelidos: Lilo, Caçolinho, Suzu): vira-lata caramelo, preguiçoso, adora sofá e odeia gatos.
   - **Caçolão** (apelidos: Lyon): grandão, preto e branco, esfomeado, vive no quintal.
   ```

   Sem pets cadastrados → bloco vazio com texto neutro ("nenhum pet cadastrado no
   momento") — o prompt não pode quebrar com placeholder órfão.

**Fluxo de dados:** o `OnlyTalkGraph` continua sem repositórios (é um chain
`prompt | llm`). O `LlmAppService.chat()` — que já carrega os pets para o hint
`user_pets` (§5.3) — passa a montar também as linhas de persona e propagá-las via
`context_hints` no `GraphInvokeRequest`; o `OnlyTalkGraph` só renderiza o bloco no
`MessagesPlaceholder`/template, como já faz com memórias e datetime. Uma única
leitura do repositório por turno alimenta os três consumidores (hint do MainGraph,
persona do OnlyTalk e classificador do PetHealthGraph).

**Operacional (deploy):** registrar Caçolin e Caçolão (com apelidos e descrições
atuais do prompt) via REST **antes** de subir a versão com o prompt novo — a
fixture de integração usa exatamente esses dois pets, mantendo as baterias fiéis
ao ambiente real.

---

## 3. Camada Domain

### 3.1 Entidades — `src/domain/entities.py`

```python
@dataclass
class Pet(BaseEntity):
    user_id: str = ""
    name: str = ""
    nicknames: List[str] = field(default_factory=list)  # first is the primary nickname
    birth_date: Optional[date] = None
    sex: str = ""          # "male" | "female" | "unknown" (closed set)
    species: str = ""      # free text: "dog", "cat", "fish", ...
    description: str = ""  # physical/behavioral notes

@dataclass
class PetHealthEvent(BaseEntity):
    pet_id: str = ""
    event_type: str = ""   # closed set, see §2.8
    description: str = ""  # e.g. "DHPPI", "Leptospirose", "vermifugo Bravecto"
    occurred_at: Optional[date] = None
```

IDs sempre UUID (regra do projeto). `PendingFlow` (renomeado, §2.1c) ganha
`flow_domain: str`.

### 3.2 Commands — `src/domain/commands.py`

`PetAdd`, `PetUpdate`, `PetHealthEventAdd`, `PetHealthEventUpdate` — padrão
`<Entidade><Acao>`, compatíveis com `auto_map` (a lista `nicknames` passa por
cópia rasa; aceitável, commands são descartáveis).

### 3.3 Interfaces — novo `src/domain/interfaces/pet_repository.py`

Espelho exato do ISP veicular:

- `PetReadRepository(ABC)`: `get_by_id(pet_id)`, `get_all_by_user_id(user_id)` —
  **única** interface injetada no caminho do chat.
- `PetRepository(PetReadRepository)`: `add`, `update`, `delete` — só no
  `PetAppService` REST.
- `PetHealthEventRepository(ABC)`: `add`, `get_by_id`,
  `get_all_by_pet_id(pet_id, limit=None)` (ordenado `occurred_at DESC`), `update`,
  `delete`, `delete_all_by_pet_id` (helper de cascade).

### 3.4 Domain Services — `src/domain/services/`

| Serviço | Responsabilidade | Espelho de |
|---|---|---|
| `PetService` | CRUD REST-side; unicidade household de nomes+apelidos por user (§2.8); cascade delete filhos-primeiro; `find_pets_by_term` delegando ao `find_by_term` genérico | `VehicleService` |
| `PetHealthService` | register/update/delete/get_by_pet; **valida `pet.user_id == user_id` em TODA operação** (um `pet_id` vindo do LLM ou de flow stale nunca toca dado de outro user); recebe `PetReadRepository` | `MaintenanceService` |
| `PetHealthFlowService` | `parse_slot_reply` (slots pet/event_name/date), `_parse_register_more` (§2.6), `delete_confirm`, `choose_pet` (ordinal/nome/apelido); compõe o `FlowStateStore` | `MaintenanceFlowService` |

Reusar sem tocar: `date_resolver.py`, `sanitize_for_prompt`,
`DisambiguationCandidate`.

### 3.5 Validators — `src/domain/validations/` (fluent, `.validate()` final obrigatório)

- `PetValidator`: id, user_id, name (não-vazio, limite de tamanho), nicknames
  (cada item não-blank e ≤ limite; sem duplicatas normalizadas; sem colidir com
  `name`), birth_date (não-futura), sex (conjunto fechado), species (não-vazia,
  limite), description (limite).
- `PetHealthEventValidator`: id, pet_id, event_type (conjunto fechado),
  description (não-vazia, limite), occurred_at (não-futura, não anterior a 1980).

**Não repetir o bug conhecido** do `ShoppingListService.delete()/check()`: todo
caminho de service termina em `.validate()` (teste de cadeia completa incluído).

---

## 4. Camada Infra

### 4.1 SQLite — `src/infra/data/sqlite/`

- `sqlite_pet_repository.py` — tabela `pets`. **Apelidos: coluna `TEXT` com array
  JSON** (`json.dumps`/`json.loads` no add/update/_map). Decisão (ver §10 para a
  alternativa): apelidos são value object do agregado (sem identidade/ciclo de
  vida próprios); todo matching já é em Python (o `normalize()` remove acentos,
  coisa que `WHERE` do SQLite não faz); a ordem "1º = principal" é o índice 0 do
  array de graça; escala household (unidades, não milhares). A unicidade fica
  inteiramente no domain service — já é assim com veículos hoje.
- `sqlite_pet_health_event_repository.py` — tabela `pet_health_events`,
  `occurred_at` ISO, índice DESC, `limit` opcional.
- `read_only_pet_repository.py` — wrapper que **fisicamente não possui** métodos
  de escrita (cópia do `ReadOnlyVehicleRepository`).

### 4.2 Settings — `src/infra/settings.py` + `.env.example`

- `LLM_PET_HEALTH_GRAPH_CHAT_MODEL` (default `gemma4:12b`) + temperatura (0.1 no
  classificador, padrão do projeto) + reasoning herdado de `LLM_REASONING`.
- **TTL: reutilizar `MAINTENANCE_FLOW_TTL_SECONDS`** para ambos os domínios (é o
  TTL do *mecanismo* de flow, não do domínio; var separada seria configuração
  especulativa). Documentar no `.env.example` e no CLAUDE.md que a var vale para
  os dois flows.

### 4.3 Prompts — `src/infra/prompts/` (PT-BR, **aspas retas obrigatórias**, parse `json.loads`)

**`pet_health_graph.md`** (classificador — 1 chamada LLM classifica E extrai; o
esboço completo validado pelo `especialista-de-prompt` segue abaixo e deve ser o
ponto de partida da Fase C):

- Cabeçalho: papel, "APENAS um objeto JSON válido", `{current_date}`,
  `{available_pets}` (uma linha por pet: `- Caçolin (apelidos: Lilo, Caçolinho,
  Suzu)` — cada termo passado por `sanitize_for_prompt` com cap ~40 chars/termo e
  teto ~20 pets), `{history}` (`_recent_history` copiado do veicular: sanitize por
  linha, 200 chars, máx. 6 mensagens).
- **REGRA DE DATAS idêntica à veicular**: o LLM NUNCA calcula datas — só
  `date_token` (`today`/`yesterday`/`day_before_yesterday`), `date_value`
  (`YYYY-MM-DD` ou `--MM-DD`), `period` (conjunto fechado com `this_year` etc.).
  EX2 "22/05/26" é transcrição (`2026-05-22`), não aritmética; `parse_explicit_date`
  aceita `dd/mm/yy` como fallback se o LLM copiar cru.
- `pet_term`: menção que casa inequivocamente com nome/apelido da lista → **nome
  canônico** ("Suzu" → "Caçolin"); senão a menção crua ("Vaniça"). O valor é sempre
  tratado como *termo de busca* — o `find_pets_by_term` em Python é a autoridade,
  nunca o LLM.
- `event_type` (conjunto do §2.8), `event_name` (como o usuário disse; vazio se
  só "tomou vacina"), `query`, `query_kind` (`list`/`open`), `query_limit`,
  `edit_field`, `new_value`.
- Formato de saída com **todos os campos sempre presentes** (o modelo 12b erra
  menos com esqueleto fixo).
- Few-shots obrigatórios: os 4 exemplos do usuário; "Levei o Lilo no veterinário
  ontem" (normalização apelido→canônico + vet_visit); "Cadastre minha nova
  cachorra, a Mel" → `pet_write_forbidden`; "Remova este registro" →
  `delete_health_event`; e **negativos da persona**: "O Caçolin está dormindo no
  sofá de novo" e "Será que o Bravecto funciona mesmo?" → `not_recognized`.

**`pet_health_graph_query_response.md`** (2ª chamada, só para `query_kind="open"`):
recebe `{user_name}`, `{pet_name}`, `{current_date}`, `{records}` (uma linha por
registro: `data | tipo | nome`, descrições via `sanitize_for_prompt`) e `{input}`;
instruções: responder curto, só com os registros fornecidos, datas dd/mm/aaaa, "se
nenhum registro corresponder, diga que não encontrou". EX4 resolve-se assim: Python
filtra `period=this_year` + teto 20; o LLM localiza "gripe canina" na lista curta
(sem fuzzy de nome de vacina em Python na v1). Fallback determinístico
`_render_records` se a chamada falhar.

**`only_talk_graph.md`** — mudança de persona (§2.9): remover a seção "Seus
irmãos" hardcoded (linhas 5-7 atuais); adicionar a regra "todos os pets
cadastrados do usuário são seus irmãos — você os conhece pela lista abaixo e fala
deles com carinho" + placeholder `{siblings}` renderizado pelo `OnlyTalkGraph`.
Mesmo commit da injeção dinâmica — sem janela de amnésia.

**`main_graph.md`** — 4 mudanças (ver §5.2). **`memory_graph.md`** — 1 linha nova:
não extrair eventos pontuais de saúde dos pets (vacina/vermífugo/consulta com data)
como memória durável — agora têm storage estruturado; fatos duráveis ("o Caçolin é
alérgico a frango") continuam válidos.

---

## 5. Camada Application

### 5.1 `src/application/graphs/pet_health_graph.py`

Herda de `Graph` (cache `self._compiled_graph` — não recompilar por request).
Estado (`total=False`): `input`, `intent`, `pet_term`, `event_type`, `event_name`,
`resolved_occurred_at`, `resolved_period`, `query`, `query_kind`, `query_limit`,
`edit_field`, `new_value`, `matched_pets`, e um `output_*` por node + `output`.

```
START → classify → (conditional_edges via intent_router)
   ├→ list_pets ──────────────┐
   ├→ register_health_event ──┤
   ├→ query_health_event ─────┤
   ├→ edit_health_event ──────┼→ final_response → END
   ├→ delete_health_event ────┤
   ├→ pet_write_forbidden ────┤
   └→ not_recognized ─────────┘
```

- `classify`: 1 chamada LLM → `_extract_structured_output()` → `json.loads()`
  (**nunca `eval`**; JSON malformado/None → `["not_recognized"]`, jamais exceção).
  Resolve data/período em Python (`resolve_date_token`/`parse_explicit_date`/
  `resolve_period`) e pets via `find_pets_by_term`.
- `register_health_event`: pet 0 matches → "você não tem nenhum pet chamado X"
  (sem oferecer cadastro, §2.4); >1 → flow `choose_pet`; slots faltantes → grava
  `PendingFlow(flow_domain="pet_health")` e pergunta; completo → registra; se
  vacina via flow → `register_more` (§2.6).
- `query_health_event`: fetch com teto duro `_QUERY_RECORD_LIMIT = 20` (aplicado
  ANTES do fetch e no render), filtro por `resolved_period` em Python, grava focus
  do registro mais recente; `list` → render determinístico (sem LLM); `open` → 2ª
  chamada com o prompt de resposta.
- `edit_health_event` / `delete_health_event`: operam sobre o focus (§2.7).
- `pet_write_forbidden` / `not_recognized`: strings fixas, sem LLM.
- **Sem `asyncio.run()` novo em nodes** — o caminho SQLite é síncrono; se surgir
  I/O async, usar o `async_runner` existente.

### 5.2 `src/application/graphs/main_graph.py` + `infra/prompts/main_graph.md`

- Node `pet_health` wired **incondicionalmente** (diferente do MusicGraph — não há
  backend externo opcional), com fallback `not_recognized → only_talk` idêntico ao
  `_handle_vehicle_maintenance`.
- `main_graph.md`: (a) linha de contexto `{user_pets}` (formato compacto
  `Caçolin (Lilo, Caçolinho, Suzu), Caçolão (Lyon)` — sem os apelidos, "o Suzu
  tomou vacina" roteia errado); (b) categoria `pet_health` (AGIR sobre a saúde dos
  pets: registrar/consultar/apagar evento, listar pets, ou tentar cadastrar/editar/
  excluir um PET); (c) **nova regra de desambiguação** espelhando a regra 10 dos
  veículos — item crítico dada a persona (§1): relato de evento REALIZADO em pet do
  contexto → `pet_health`; pedido explícito de registrar/consultar → `pet_health`
  mesmo com pet fora do contexto; tentativa de escrita de pet → `pet_health` (o
  subsistema nega); histórias/carinho/travessuras ("o Caçolão comeu meu chinelo")
  → `only_talking`; hipotéticas/conhecimento geral ("cachorro pode tomar
  dipirona?") → `only_talking`; pet de terceiros sem pedido explícito ("o cachorro
  da vizinha tomou vacina") → `only_talking`; follow-up curto pós-interação de
  saúde ("E o Caçolão?") → `pet_health`; (d) `["pet_health"]` nos exemplos de
  saída.

### 5.3 `src/application/appservices/`

- `pet_app_service.py` — CRUD REST via `PetService`/`PetHealthService`, converte
  para ViewModels via `auto_map()`; zero regra de negócio. `view_models.py` ganha
  `PetResponse` (expõe `nicknames` como lista) e `PetHealthEventResponse`.
- `llm_app_service.py` — (i) hint `user_pets` no `context_hints` (nomes E
  apelidos, do `PetReadRepository`; a fonte de verdade de pets é a tabela, nunca
  as memórias) + `user_pets_persona` (linhas nome/apelidos/descrição sanitizadas
  para o bloco `{siblings}` do OnlyTalk, §2.9 — **uma** leitura do repo alimenta
  os dois hints); (ii) dispatch único de pending por `flow_domain` (§2.2);
  (iii) `_consume_pet_health_flow` espelhando `_consume_maintenance_flow`
  (short-circuit ANTES do MainGraph, fallthrough com a mensagem original).
- `only_talk_graph.py` — renderiza `{siblings}` a partir de
  `context_hints["user_pets_persona"]` (com fallback neutro quando vazio/ausente),
  ao lado das memórias e do datetime já injetados. Continua chain `prompt | llm`,
  sem repositórios e sem escrita de histórico.

---

## 6. Camada API — `src/routes.py`

Tag `"Pet"`, todas atrás do `router` autenticado (nunca no `public_router`);
paridade com as rotas de veículo:

```
GET    /user/{id}/pet            → pets do usuário
GET    /pet/{id}                 → detalhe
POST   /pet                      → PetAdd    → {"pet_id": ...}
PUT    /pet                      → PetUpdate
DELETE /pet/{id}                 → cascade: delete_all_by_pet_id primeiro, pet depois
GET    /pet/{id}/health-event    → histórico de eventos
```

Escrita de **eventos** permanece chat-only na v1 (REST expõe só leitura do
histórico, paridade com `/vehicle/{id}/maintenance`); POST REST de evento é adição
barata futura.

### IoC — `src/infra/ioc.py`

Factories novas (com cache, padrão `_repo_cache`): `get_pet_repository`,
`get_pet_read_repository`, `get_pet_health_event_repository`, `get_pet_service`,
`get_pet_health_service` (recebe o repo **read-only**), `get_pet_health_flow_service`
(compondo o `FlowStateStore`), `get_pet_app_service` (**único** lugar que recebe o
`PetRepository` completo), `get_pet_health_graph`; ajustar `get_main_graph` e
`get_llm_app_service`.

---

## 7. Estratégia de testes (TDD estrito — testes antes de qualquer implementação)

Inventário validado pelo `programador-tester` (espelho arquivo-a-arquivo da suíte
veicular, ~15 arquivos unit + 1 integration, ~200-220 casos unit + ~26 integration).
Convenções: `unittest.mock`, sem pytest-asyncio (`_run(coro)` com
`run_until_complete`), helpers `_make_repo()`/`_sample_*()`, `FakeContextRepository`
copiado de `test_maintenance_flow_service.py`, TTL testado com `ttl_seconds=-10`
(nunca sleep), graphs com `patch.object(..., "load_prompt", return_value="{input}")`
e `_classify` via `patch.object(graph, "_extract_structured_output")`.

### Fase 0 — Refactors (regressão, não RED)

Suíte veicular + shopping list **verde após cada um** dos refactors §2.1(a)-(c).
Testes novos só para o contrato do `find_by_term` genérico e do `FlowStateStore`.

### Fase A — Domain (RED primeiro)

| Arquivo | Espelha | Casos est. |
|---|---|---|
| `test_pet_validation.py` | `test_vehicle_validation.py` | ~26 — inclui apelidos: item blank na lista, duplicata normalizada, colisão com name, lista vazia OK |
| `test_pet_health_event_validation.py` | `test_maintenance_record_validation.py` | ~18 |
| `test_text_matching.py` (estender) | — | +4-6 — match por apelido secundário, acento-insensível, diminutivo fuzzy |
| `test_pet_service.py` | `test_vehicle_service.py` | ~16 — unicidade união nome+apelidos, mesma colisão entre users OK, cascade ordenado via `parent.mock_calls` |
| `test_pet_health_service.py` | `test_maintenance_service.py` | ~15 — **ownership em toda operação** (pet de outro user + `assert_not_called`), data futura, evento antes do nascimento, birth_date ausente → regra não se aplica |
| `test_pet_health_flow_service.py` | `test_maintenance_flow_service.py` | ~35 — roundtrip/TTL expirado limpa store, parsers por slot (pet único/ambíguo/none; event_name 1-6 tokens/longo→none; data futura→invalid/amanhã→none), delete_confirm (sim/não/misto→none), choose_pet por ordinal/nome/**apelido**, focus, **loop register_more completo** (§2.6: negativa, sim nu, sim+conteúdo, none, iteração, TTL no meio) |

`test_date_resolver.py`: **nenhuma mudança**.

### Fase B — Infra + REST

| Arquivo | Casos est. |
|---|---|
| `test_sqlite_pet_repository.py` | ~7 — roundtrip, **JSON de nicknames com ordem preservada** (1º = principal), lista vazia, isolamento por user |
| `test_sqlite_pet_health_event_repository.py` | ~8 — roundtrip `date`, DESC + limit, `delete_all_by_pet_id` |
| `test_read_only_pet_repository.py` | 3 — delega reads, `not hasattr` escrita, `not isinstance(repo, PetRepository)` |
| `test_pet_app_service.py` | ~9 — user inexistente raises + não delega, mapeamento ViewModels, delete cascade |

Rotas cobertas pelos guards genéricos existentes (`test_routes_require_api_key.py`
é global); +1 caso `/pet` explícito é opcional.

### Fase C — Graph + orquestração (LLM sempre mockado)

| Arquivo | Casos est. |
|---|---|
| `test_pet_health_graph_classify_intent.py` | ~10 — date_token resolvido, data explícita, **JSON malformado→not_recognized**, extract None→not_recognized, `matched_pets` por apelido |
| `test_pet_health_graph_handlers.py` | ~24 — write_forbidden string fixa + **repo de escrita nunca tocado**, register (não cadastrado/ambíguo/slot faltante→pergunta/completo→registra), **vacina via flow → "tomou mais alguma?" + pending register_more; registro direto NÃO re-pergunta**, query (vazia→msg fixa sem LLM, render determinístico, seta focus, **cap 20 no fetch e no render**, `sanitize_for_prompt` na descrição), edit/delete com/sem focus, delete pede confirmação |
| `test_main_graph_pet_health.py` | 3 — roteia, not_recognized→fallback only_talk, intent real não chama only_talk |
| `test_only_talk_graph_siblings.py` (ou estender o existente) | ~5 — bloco `{siblings}` renderizado com nome/apelidos/descrição, sem pets → fallback neutro (prompt não quebra), `context_hints` ausente → fallback neutro, descrição maliciosa passa por `sanitize_for_prompt` (cap ~200), seção hardcoded removida do prompt (assert de conteúdo do arquivo) |
| `test_llm_app_service_pet_health_flow.py` | ~10 — pending consumido **antes** do MainGraph (`main_graph.invoke.assert_not_called()`), fallthrough chama 1x com msg original, **dispatch por flow_domain** (pending maintenance não é consumido pelo pet e vice-versa), delete_confirm misto não deleta, loop sim/não, hint `user_pets` com nomes E apelidos |

### Fase D — Integração LLM real (última; requer Ollama; validação de prompt, não gate de TDD)

`test_llm_app_service_chat__pet_health_graph.py` (~26 casos parametrizados,
`pytestmark = pytest.mark.integration`, fixture `integration_pets` com 2 pets via
`get_pet_app_service()` — **Caçolin** (Lilo, Caçolinho, Suzu) e **Caçolão**
(Lyon), com as descrições da persona atual, mantendo as baterias fiéis ao
ambiente real §2.9):
- **B1 positiva** (~10): os 4 exemplos do usuário + variações com apelidos →
  `["pet_health"]`.
- **B2 anti-falso-positivo** (~10): "meu cachorro é lindo", "o Caçolin está
  latindo", "qual vacina é recomendada para filhotes?", "quanto custa a
  antirrábica?", "cachorro pode tomar dipirona?", vacina de pet **não cadastrado**
  sem pedido explícito → `["only_talking"]`.
- **Negação de escrita** (~4): "cadastre minha nova gata", "apaga o Caçolão dos
  meus pets", "muda o apelido do Caçolin" → resposta contendo "permissão".
- **Persona dinâmica** (~3): conversa livre sobre pet cadastrado ("quem é o
  Caçolin?", "o Suzu está dormindo no sofá") → `["only_talking"]` **e** a resposta
  demonstra conhecer o pet (reconhece o apelido, cita algo da descrição) — valida
  que o bloco `{siblings}` §2.9 substituiu o hardcode sem perda de persona.

Critério de aceite: 100% por bateria; até 2 frases flaky documentadas em
`AMBIGUOUS_EXCLUDED`. **Escrever as baterias ANTES de calibrar o prompt** — as
frases são a especificação do classificador.

### Fase E — Segurança (transversal + auditoria)

Asserts já embutidos nas fases anteriores (write nunca tocado, sanitize, cap,
ownership) + auditoria final pelo `especialista-de-seguranca` antes do merge
(precedente: a auditoria veicular achou 2 Médias, incluindo ISP só nominal na IoC
— conferir que `get_pet_health_graph`/`get_pet_health_service` recebem de fato o
`ReadOnlyPetRepository`).

---

## 8. Fases de implementação (cada fase: testes RED → implementação → verde → refactor)

| Fase | Conteúdo | Gate |
|---|---|---|
| **0** | Refactors §2.1(a)-(c) + dispatch único §2.2, commits próprios | Suíte inteira verde após cada refactor |
| **A** | Entidades, commands, interfaces, validators, `PetService`, `PetHealthService`, `PetHealthFlowService` | Unit A verde |
| **B** | Repos SQLite + wrapper read-only, `PetAppService` + ViewModels + rotas, settings, factories IoC, `.env.example` | Unit A+B verde |
| **C** | `PetHealthGraph` + prompts novos, `main_graph.md` + `memory_graph.md`, **persona dinâmica §2.9** (`only_talk_graph.md` + `{siblings}` no `OnlyTalkGraph`, mesmo commit), wiring MainGraph + `LlmAppService` (hints + consumer) | Unit A+B+C verde; smoke de build da IoC |
| **D** | Baterias de integração contra Ollama vivo; iteração de prompt até 100%/bateria | B1+B2+negação no critério |
| **E** | Auditoria `especialista-de-seguranca`; correções | Achados Média+ corrigidos |

Atualizar CLAUDE.md ao final (nova var de modelo, TTL compartilhado, hierarquia de
graphs, seção Pet Health). Mover este arquivo para `doing/` ao iniciar e `done/` ao
concluir, preenchendo o cabeçalho.

---

## 9. Riscos e mitigação

### 9.1 Falsos positivos do classificador do MainGraph (o risco nº 1)

Os pets do usuário **vivem na persona do Peruca** — hoje hardcoded, e após §2.9
injetados dinamicamente como "irmãos" no `OnlyTalkGraph`. Conversa casual sobre
eles é rotina; roubo de turno por `pet_health` degradaria a experiência cotidiana.
A persona dinâmica **agrava levemente** o risco (todo pet cadastrado passa a
existir nos dois mundos: persona E registro de saúde), o que torna a regra de
desambiguação ainda mais importante. Mitigação em 3 camadas: (i) regra de
desambiguação detalhada no `main_graph.md` (§5.2c) com negativos explícitos;
(ii) fallback `not_recognized → only_talk` dentro do próprio `PetHealthGraph`
(rede de segurança para o que passar); (iii) bateria B2 na Fase D como
especificação executável, com iteração de prompt até 100%.

### 9.2 Aritmética de datas no modelo 12b

Idêntico ao veicular: o LLM só emite tokens fechados; `date_resolver` (já testado)
resolve em Python. EX4 "nesse ano" → `period: "this_year"` → `resolve_period`.
Risco residual: o modelo transcrever "22/05/26" cru no `date_value` —
`parse_explicit_date` já aceita `dd/mm/yy` como fallback.

### 9.3 Fallthrough do slot-filling / loop register_more

Invariante conservador herdado: a mensagem inteira precisa SER a resposta do slot;
qualquer dúvida → `kind="none"` → limpa pending e roteia normal. O slot novo de
texto aberto (`event_name`) é o ponto frágil — mitigado pelo limite de 1–6 tokens
pós-fillers e cap de chars (§2.5). O loop `register_more` nunca pode sequestrar a
conversa: "liga a luz" durante o loop → MainGraph (testado na Fase A/C).

### 9.4 Prompt injection

| Vetor | Mitigação |
|---|---|
| `description` de eventos reinjetada (query response, confirmações, focus) | `sanitize_for_prompt(..., 120)` em todo ponto de reinjeção |
| Nomes/apelidos (controláveis via REST) injetados no classificador e no main_graph | `sanitize_for_prompt` por termo, cap ~40 chars, teto ~20 pets |
| **`Pet.description` injetada no prompt de PERSONA** (`{siblings}` do OnlyTalk, §2.9) — vetor novo: um "pet" com descrição maliciosa reprograma o Peruca em toda conversa livre | `sanitize_for_prompt` com cap ~200 chars por descrição + teto de pets; descrição nunca entra no classificador do MainGraph (só nome/apelidos) |
| `{history}` | Padrão `_recent_history` copiado (sanitize/linha, 200 chars, máx. 6) |
| `query_limit` do LLM | Teto duro 20 ANTES do fetch e no render |
| Escrita de pet sob injection | **Estrutural** (ISP, §2.4) — não depende de prompt |
| Saída do classificador | `json.loads` sobre `_extract_structured_output`; nunca `eval` |

### 9.5 Duplicação com o MemoryGraph

"o Caçolin tomou DHPPI hoje" viraria também memória durável, poluindo
`{user_memories}` com fatos que agora têm storage estruturado. Mitigação: linha no
`memory_graph.md` (§4.3) excluindo eventos pontuais de saúde; fatos duráveis do pet
continuam válidos como memória. A fonte de verdade de pets/eventos é o SQLite,
nunca as memórias.

### 9.6 Regressão do flow veicular pelos refactors da Fase 0

Refactors em commits próprios com a suíte inteira verde entre cada um; nenhuma
mudança de comportamento — só extração. Se um refactor quebrar o flow veicular,
descobrimos antes de existirem duas features em cima dele.

---

## 10. Alternativas descartadas

- **Escopo household do Pet (recomendação do arquiteto, estilo lista de compras).**
  Descartado por decisão do usuário (2026-07-07): pets são per-user como veículos,
  com `user_id` e ownership validado em toda operação. Consequência aceita: um
  morador não vê/registra nos pets de outro; o hint `user_pets` e as rotas seguem
  o padrão `/user/{id}/pet`.
- **Aceitar datas futuras (agendamento de dose).** Adiado: bifurcaria a semântica
  de consulta ("já tomou X?" precisaria distinguir ocorrido de agendado). Extensão
  futura: "agendamento de dose/lembrete de reforço".
- **Adiar `edit_health_event` para v1.1 (recomendação do especialista-de-prompt).**
  Descartado por decisão do usuário: edit entra na v1, espelho completo do veicular.
- **Tabela filha para apelidos.** Descartado (§4.1): apelidos são value object sem
  identidade; matching é 100% em Python; ordem de graça no array JSON; tabela filha
  compraria capacidade SQL que o design nunca usa.
- **`PendingPetHealthFlow` separado + checagens sequenciais de pending.** Descartado
  (§2.2): dois pendings simultâneos com precedência acidental; o dataclass unificado
  + chave única dá exclusão mútua estrutural.
- **Parser de slots genérico.** Descartado: regras de km não têm análogo em vacina;
  abstração especulativa (YAGNI). Só a *persistência* (`FlowStateStore`) é genérica.
- **Múltiplas vacinas numa resposta do loop ("raiva e giárdia").** v1.1.
- **POST REST de evento de saúde.** v1 mantém paridade com o veicular (escrita de
  evento é chat-only; REST lê o histórico). Adição barata depois, se necessária.
- **Fuzzy match de nome de vacina em Python na consulta.** Desnecessário na v1: a
  lista curta (≤20) vai no prompt e o LLM localiza; com filtro vazio a negativa é
  determinística.
