# Plano — Remoção/marcação inteligente de itens da lista de compras (matching não-literal + desambiguação com estado)

> **Status:** todo — ainda não implementado
> **Criado em:** 2026-07-04 01:51
> **Implementado em:** —
> **PR/commit:** —
>
> _Documento de intenção. Ao concluir, mover para `docs/features/done/`, preencher os campos acima e lembrar: **o código é a fonte da verdade**, não este plano._

## Context

Hoje, ao pedir "Remova papel crepom da lista", o Peruca responde "Removido: papel crepom" mas **não remove nada** se o item foi salvo como "papel grepom" (typo). Os handlers `_handle_delete_item`, `_handle_check_item` e `_handle_uncheck_item` em `ShoppingListGraph` casam item por **igualdade exata** (`e.name.lower() == name.lower()`), então:

- typos não casam ("grepom" ≠ "crepom");
- nome parcial não casa ("carne" ≠ "Carne de panela");
- pior: `_handle_delete_item` **sempre** responde `"Removido: {payload}"` mesmo sem casar nada (mente).

**Resultado desejado:** o Peruca deve resolver o item mesmo quando o texto não é literal (typo ou nome parcial). Quando o termo casar **mais de um** item (ex.: "carne" → "Carne de panela" e "Carne seca"), ele deve **perguntar** qual, e — decisão do usuário — **lembrar a pergunta pendente** para que a resposta seguinte ("a primeira", "Carne de panela" ou "cancelar") seja aplicada corretamente, mesmo sendo uma frase que sozinha não voltaria à lista de compras.

Escopo: operações **remover, marcar e desmarcar** (compartilham o mesmo bug de match exato). `add_item` fica de fora (semântica diferente).

Design validado pelos agentes `arquiteto`, `especialista-de-prompt` e `programador-tester` (mandatório por CLAUDE.md). **Sem alteração no prompt classificador** — o classificador continua extraindo o termo cru ("carne"); toda a inteligência é determinística no domínio.

---

## Abordagem

Duas peças determinísticas (sem chamada de LLM), seguindo o precedente `SmartHomeService.find_entity_ids_by_alias` (`src/domain/services/smart_home_service.py:279`):

### 1. Resolvedor de itens (domínio, puro)
Novo método em `ShoppingListService` (`src/domain/services/shopping_list_service.py`):

```python
def find_items_by_name(self, query: str, items: List[ShoppingListItem]) -> List[ShoppingListItem]
```

Recebe os itens já carregados (o handler já chama `get_all()` uma vez) — mantém puro/testável, evita N acessos ao repo. Camadas em ordem de prioridade (a **primeira** que casar vence):

1. **Exato normalizado** — `_normalize` (NFD/NFKD, sem acento, minúsculo, trim). Curto-circuita: "carne" com "Carne" na lista casa **só** "Carne", nunca ambíguo.
2. **Parcial** — token/substring: `tokens(query) ⊆ tokens(name)` ("carne"→"Carne de panela"; "panela"→idem). Tokenizador próprio removendo só stopwords PT genéricas (`a/o/de/da/do/…`) — **não** reusar `_location_tokens` do smart_home (remove termos de clima).
3. **Typo** — `difflib.SequenceMatcher(...).ratio() >= 0.8` ("grepom"→"Crepom"). Guard de comprimento mínimo p/ palavras curtas evitar falso-positivo.
4. Nada casa → `[]`.

Retorno `0 / 1 / vários` dirige os handlers. **Apenas stdlib** (`difflib`, `unicodedata`) — não importar `infra/utils_nlp.py` (violaria Domain ← Infra; e `pt_core_news_sm` não tem vetores, similaridade fraca).

Corrigir junto (bug conhecido): `ShoppingListService.delete()` omite o `.validate()` final da cadeia (`src/domain/services/shopping_list_service.py:73`).

### 2. Handlers usam o resolvedor
`_handle_delete_item` / `_handle_check_item` / `_handle_uncheck_item` (`src/application/graphs/shopping_list_graph.py`): por cada nome do payload (split `|`, termo já sem `,quantidade`):
- **0 candidatos** → mensagem PT "não encontrado" (corrige o delete que mente).
- **1 candidato** → aplica no `item.id` literal casado.
- **>1 candidatos** → **não aplica**; grava desambiguação pendente e responde a pergunta PT listando os `name` dos candidatos.
- Vários nomes no mesmo turno: aplica os não-ambíguos, pergunta só do **primeiro** ambíguo (documentar).

### 3. Estado de desambiguação pendente (decisão do usuário: **com estado**)

**Serviço de domínio novo** `DisambiguationService` (`src/domain/services/disambiguation_service.py`) envolvendo o `ContextRepository` (ABC async já existente, `set_key/get_key/delete_key`). Encapsula serialização JSON, chave `f"disambiguation:{user.id}"` e TTL — evita duplicar essa regra entre graph (escrita) e app service (leitura).

Entidades novas em `src/domain/entities.py`:
```python
@dataclass
class DisambiguationCandidate: id: str; name: str
@dataclass
class PendingDisambiguation:
    operation: str            # "delete" | "check" | "uncheck"
    query: str
    candidates: list[DisambiguationCandidate]
    expires_at: float         # epoch — TTL embutido no payload
```

API:
```python
async def set_pending(user_id, pending) -> None
async def get_pending(user_id) -> Optional[PendingDisambiguation]   # trata expirado como ausente e limpa
async def clear_pending(user_id) -> None
def resolve_choice(message, candidates) -> ChoiceResult             # puro/sync: kind = match|cancel|none
```

- **TTL embutido no JSON** (`expires_at`) porque a ABC `set_key` não tem parâmetro TTL — funciona igual p/ Redis e in-memory. TTL vem de `settings.disambiguation_ttl_seconds` (~120s), nova chave em `src/infra/settings.py`.
- `resolve_choice`: literal (reusa `find_items_by_name` escopado aos candidatos), ordinal PT ("a primeira", "segundo", "1", "último"), cancelar ("cancelar/deixa/nenhum").

### 4. Escrita (graph) e consumo (app service)

- **Escrita:** injetar `DisambiguationService` no `ShoppingListGraph`. Na ambiguidade, `async_runner.run(disambiguation_service.set_pending(...))` (nós de graph são sync — usar `infra.async_runner.run`, nunca `asyncio.run`). `user_id` vem de `data["input"].user.id`. O **store é o sinal** — não precisa propagar flag pelo merge do `MainGraph`.
- **Consumo:** no topo de `LlmAppService.chat()` (`src/application/appservices/llm_app_service.py:47`), **antes** de `main_graph.invoke` (linha 87):
  ```python
  pending = async_runner.run(self.disambiguation_service.get_pending(user.id))
  if pending is not None:
      return self._consume_disambiguation(user, pending, chat_request.message)
  ```
  `_consume_disambiguation` resolve a escolha:
  - **match** → aplica via `ShoppingListService.delete/check/uncheck(candidate.id)` (injetar `shopping_list_service` no `LlmAppService`) → `clear_pending` → persiste turno → confirma. **Sem** MainGraph (determinístico, sem novo custo de LLM, não re-ambigua).
  - **cancel** → `clear_pending` → "Ok, cancelei." → para.
  - **none** (usuário ignorou e pediu outra coisa) → `clear_pending` → **fallthrough** para `main_graph.invoke(mensagem original)` (não prende o usuário em loop).

### 5. Fallback in-memory (senão a feature não roda sem Redis)
`get_context_repository()` (`src/infra/ioc.py:547`) retorna `None` sem `CACHE_DB_CONNECTION_STRING`. Necessário:
- Novo `InMemoryContextRepository(ContextRepository)` em `src/infra/data/cache/in_memory_context_repository.py` (dict async, espelha o fallback de `_get_session_history_factory`, ioc.py:170).
- `get_context_repository()` retorna o in-memory quando não há Redis **e cacheia como singleton** em `_repo_cache` (hoje instancia fresh a cada chamada — sem cache o dict perderia estado entre os dois turnos). Inócuo p/ Redis.
- Verificar lifecycle `connect()` do `RedisContextRepository` — chamar uma vez no `DisambiguationService` se `set_key/get_key` não conectam sozinhos.

---

## Arquivos a modificar

| Arquivo | Mudança |
|---|---|
| `src/domain/services/shopping_list_service.py` | `find_items_by_name(...)`; corrigir `.validate()` em `delete()` |
| `src/domain/entities.py` | `DisambiguationCandidate`, `PendingDisambiguation` |
| `src/domain/services/disambiguation_service.py` | **novo** serviço |
| `src/application/graphs/shopping_list_graph.py` | handlers delete/check/uncheck usam resolvedor; escrevem pending; montam pergunta PT; injeta `DisambiguationService` |
| `src/application/appservices/llm_app_service.py` | injeta `shopping_list_service` + `disambiguation_service`; check + early return no topo de `chat()`; `_consume_disambiguation` |
| `src/infra/data/cache/in_memory_context_repository.py` | **novo** |
| `src/infra/ioc.py` | `get_context_repository` singleton+fallback; `get_disambiguation_service` novo; wiring em `get_shopping_list_graph` (l.217) e `get_llm_app_service` (l.396) |
| `src/infra/settings.py` | `disambiguation_ttl_seconds` |

Padrão a espelhar: `SmartHomeService.find_entity_ids_by_alias` + `_normalize` (`src/domain/services/smart_home_service.py:48,279`).

---

## Testes (TDD — escrever ANTES da implementação, todos devem falhar primeiro)

**`test_shopping_list_service.py`** — classe `TestShoppingListServiceFindItemsByName`:
- exato (baseline); exato case/acento-insensível; parcial ("carne"→"Carne de panela", "panela"→idem); typo ("grepom"→"Crepom", parametrizado); múltiplos parciais → todos; **exato tem prioridade sobre parcial e sobre fuzzy**; sem match → `[]`; palavra diferente abaixo do threshold ("carne" vs "leite") → `[]`; lista vazia; query em branco; **não acessa o repositório**.

**`test_shopping_list_graph_handlers.py`** — `TestHandleDeleteItemResolution` (+ espelhos check/uncheck):
- match único exato/typo/parcial → aplica; passa termo limpo (sem `,1`/espaços) ao resolvedor; **sem match → não chama delete e output NÃO diz "Removido"** (bug atual) + PT "não encontrado"; **ambíguo → não aplica + pergunta com os dois nomes + "?"** + grava pending; múltiplos `|` (um casa, outro não); lista vazia. Manter verdes as regressões existentes (whitespace tolerance, case-insensitive check/uncheck, idioma PT, `_handle_final_response`).

**`test_disambiguation_service.py`** (novo): set/get roundtrip; get de expirado → None + limpa; clear; `resolve_choice` literal/ordinal/cancel/none.

**`test_in_memory_context_repository.py`** (novo): set/get/delete/get-ausente.

**`LlmAppService`**: turno 2 com pending → aplica via service + clear + não chama MainGraph; cancel; none → fallthrough para MainGraph.

Comandos: `cd src && python -m pytest tests/unit_tests/ -v`.

---

## Verificação end-to-end

1. **Unit:** `cd src && python -m pytest tests/unit_tests/ -v` — tudo verde.
2. **Manual (dev, contra Ollama):** `cd src && python app.py`, via `POST /chat`:
   - "adicione papel grepom" → depois "remova papel crepom" ⇒ remove; "mostre a lista" ⇒ vazio (bug original resolvido).
   - "adicione carne de panela" + "adicione carne seca" → "remova a carne" ⇒ pergunta "…Carne de panela ou Carne seca?"; responder "a primeira" (ou "carne de panela") ⇒ remove só ela; "mostre a lista" ⇒ a outra permanece.
   - Ambíguo + responder "cancelar" ⇒ nada removido.
   - Ambíguo + responder outra coisa ("acende a luz") ⇒ pending descartado, comando normal roteia.
3. Repetir marcar/desmarcar com typo e nome parcial.
