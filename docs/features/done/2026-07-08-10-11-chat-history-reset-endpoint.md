# Plano: Endpoint de Reset do Histórico de Conversa (Chat History)

- **Status:** done
- **Criado em:** 2026-07-08 10:11
- **Implementado em:** 2026-07-08 (branch `feature/pet-health-events-registry`)
- **PR/commit:** não commitado (aguardando solicitação do usuário)
- **Consultorias realizadas (obrigatórias):** `arquiteto`, `especialista-de-prompt`, `programador-tester`

> **Implementação concluída (2026-07-08, TDD via skill `nova-feature`):**
>
> **RED** (`programador-tester`) — 3 arquivos de teste criados:
> `tests/unit_tests/test_llm_app_service_reset_context.py` (6 testes),
> `tests/unit_tests/test_routes_chat_history_delete.py` (2 testes),
> `tests/integration_tests/test_llm_app_service_reset_context_redis.py` (1 teste,
> skip gracioso sem Redis). Item C (adicionar rota à suíte de API key) foi **pulado**:
> `test_routes_require_api_key.py` não é parametrizado por rota (métodos individuais
> hard-coded em `GET /vehicle/{id}`), não há lista para estender; a rota já herda a
> proteção estrutural do mount `Depends(require_api_key)` em `app.py`.
>
> **GREEN** (`programador`) — `LlmAppService.reset_context()` (guard `None`, propaga
> exceção, sem try/except) + rota `DELETE /user/{id}/chat-history`. Construtor,
> prompts, grafos, IoC e domínio intocados. **8 testes-alvo verdes; suíte unitária
> completa 1472 passed, 0 regressão.** Integração não executada (requer Redis vivo).

---

## 1. Objetivo

Adicionar um endpoint **exclusivamente REST** que reseta o histórico de conversa
(`chat_history`) de um usuário — o mesmo histórico que `OnlyTalkGraph` lê e que
`LlmAppService._persist_turn()` escreve a cada turno, obtido via
`get_session_history(user.id)`.

### Requisito verbatim do usuário

> Essa funcionalidade será apenas disponibilizada na API, **não sendo possível
> solicitá-la ao Peruca via chat.**

Consequência de design (inviolável): **nenhum** intent novo, **nenhum** nó de grafo
LangGraph, **nenhuma** menção em prompt. A única superfície é uma rota HTTP. Um
cliente conversando com o Peruca não tem como acionar o reset — nem sob prompt
injection —, porque não existe caminho de código no fluxo de chat que chegue a
`reset_context`.

### Não-objetivos (decididos com `arquiteto` e `especialista-de-prompt`)

- **Não** limpa o `ImageStore` (imagens enviadas pelo usuário) — TTL e ciclo de vida
  próprios; endpoint separado se algum dia for necessário.
- **Não** limpa `PendingFlow` (`maintenance_flow:{user_id}`,
  `pet_health_flow:{user_id}`) nem o estado de disambiguation da shopping list —
  mecanismos com TTL próprio e ciclo de vida distinto do chat history. Bundlar os
  três sob um único verbo quebraria SRP e criaria efeito colateral silencioso (ex.:
  cancelar um cadastro de vacina em andamento só porque o usuário quis "esquecer a
  conversa").
- **Não** cria nenhuma interface de domínio nova. A abstração relevante
  (`BaseChatMessageHistory.clear()`, de `langchain_core`) já existe e já é usada por
  `LlmAppService` e `OnlyTalkGraph`.
- **Não** corrige a fragmentação pré-existente de `_get_session_history_factory()`
  (ver §5, Débito técnico).

## 2. Decisão arquitetural (`arquiteto`)

### 2.1 Onde vive: novo método em `LlmAppService`

Não um `ContextAppService` dedicado. `LlmAppService` já carrega
`self.get_session_history: Optional[Callable[[str], BaseChatMessageHistory]]` e já é
o colaborador que grava o histórico (`_persist_turn`). Reusá-lo garante que o reset
atinge **exatamente a mesma chave e o mesmo backend** que a escrita. Criar um serviço
novo exigiria uma 5ª chamada a `_get_session_history_factory()` em `ioc.py`,
agravando a fragmentação in-memory (§5) sem ganho de coesão.

```python
# application/appservices/llm_app_service.py
def reset_context(self, user_id: str) -> None:
    if self.get_session_history is None:
        return
    self.get_session_history(user_id).clear()
```

Espelha o guard já presente em `_persist_turn` (`if self.get_session_history is
None: return`). `BaseChatMessageHistory.clear()` já é implementado por
`RedisChatMessageHistory.clear()` (→ `context_repo.delete_key("chat_history:{id}")`)
e por `InMemoryChatMessageHistory.clear()`.

### 2.2 Rota

```python
# routes.py — junto das rotas de User
@router.delete("/user/{id}/chat-history", tags=["User Chat History"])
def user_chat_history_reset(
    id: str,
    llm_app_service: LlmAppService = Depends(get_llm_app_service),
) -> None:
    llm_app_service.reset_context(user_id=id)
```

- **Nome `chat-history`, não `context`:** "context" é um termo já sobrecarregado no
  código (`ContextRepository` é o KV store genérico do qual chat_history, pending
  flows e imagens são todos clientes). Nomear pelo recurso real evita a leitura
  errada de que o endpoint limpa tudo.
- **Verbo `DELETE`** e forma aninhada `/user/{id}/...`: mesmo padrão já estabelecido
  por `DELETE /user/{id}/memory` (que faz `UserMemoryService.clear_by_user`).
- Fica sob o `router` autenticado (`X-API-Key`), como todas as rotas exceto
  `/health`. Nenhuma exposição pública.

### 2.3 Validação e idempotência

- **Sem** checagem de existência do usuário — mesmo padrão das demais rotas
  `/user/{id}/...` (memory, vehicle), que usam `id` apenas como escopo.
- **Idempotente:** resetar um histórico já vazio é no-op bem-sucedido.
- Retorno `-> None`, **200 implícito** (o projeto não usa 204 em nenhuma rota de
  "clear"; manter o padrão, não introduzir convenção isolada).

### 2.4 Propagação de erro (ponto que faltava resolver)

Ao contrário de `_persist_turn` — que engole exceções num `try/except` + log, por
ser escrita *best-effort* em background —, `reset_context()` **propaga** a exceção.
É uma ação **síncrona** pedida explicitamente via API: se o Redis estiver fora do ar,
o chamador precisa receber um erro (500), não um 200 mentiroso de "resetado com
sucesso".

## 3. Impacto em prompts/grafos (`especialista-de-prompt`)

**Nenhum.** Verificado:

- `only_talk_graph.md` injeta o histórico via `MessagesPlaceholder("history")`, que
  suporta lista vazia nativamente (é o caso do 1º turno de qualquer usuário novo).
  Nenhuma instrução pressupõe quantidade mínima de turnos ou continuidade narrativa.
- `vehicle_maintenance_graph.md` / `pet_health_graph.md` já marcam o bloco de
  histórico recente como "pode estar vazio", e `_recent_history()` já tem fallback
  silencioso para histórico ausente/vazio.
- Demais prompts (`main_graph.md`, `shopping_list_graph.md`, `smart_home_*`,
  `music_graph.md`, `memory_graph.md`) não consomem `{history}`.
- `context_hints` não precisa de tratamento — é recomputado a cada request, nunca
  persistido entre turnos.

Efeito colateral esperado (não é regressão): se o reset ocorrer no meio de uma
conversa, a **próxima classificação livre** (fora de flow) perde a pista das últimas
mensagens para resolver elipses — comportamento já tratado como "pode estar vazio"
pelos prompts. Os `PendingFlow` em si continuam funcionando (short-circuit
determinístico em `LlmAppService`, sem depender do chat history) e estão fora de
escopo do reset (§1).

Nenhuma alteração em `infra/prompts/`.

## 4. Plano de testes (`programador-tester`) — TDD, testes primeiro

### 4.1 `tests/unit_tests/test_llm_app_service_reset_context.py`

Classe `TestLlmAppServiceResetContext` (reusar o helper `_make_service()` de
`test_llm_app_service_history.py`):

1. `test_reset_context__valid_user_id__calls_get_session_history_with_user_id` —
   `get_session_history.assert_called_once_with(user_id)`.
2. `test_reset_context__valid_user_id__calls_clear_once` —
   `history.clear.assert_called_once_with()` (confirma que não se chama
   `clear(user_id)` — o escopo por usuário está na obtenção do histórico).
3. `test_reset_context__get_session_history_is_none__is_noop_and_does_not_raise` —
   `LlmAppService(..., get_session_history=None)`; não lança.
4. `test_reset_context__returns_none` — contrato `-> None`.
5. `test_reset_context__empty_string_user_id__still_calls_get_session_history` —
   documenta que não há validação de formato/existência (decisão consciente, §2.3).
6. `test_reset_context__history_clear_raises__propagates_exception` —
   `history.clear.side_effect = RuntimeError(...)`; `pytest.raises(RuntimeError)`.
   Trava a decisão de §2.4 (propagar, não engolir).

### 4.2 `tests/unit_tests/test_routes_chat_history_delete.py`

Padrão `TestClient` + `dependency_overrides` (igual à suíte de `DELETE
/user/{id}/memory`):

1. `test_delete_chat_history__calls_reset_context_with_path_id` —
   `svc.reset_context.assert_called_once_with(user_id=user_id)`.
2. `test_delete_chat_history__returns_200`.
3. Se `test_routes_require_api_key.py` for parametrizado por rota, **adicionar** a
   nova rota à lista (garante que exige `X-API-Key`) em vez de duplicar o teste.

### 4.3 Integração (opcional, recomendado) — sem Ollama

`tests/integration_tests/test_llm_app_service_reset_context_redis.py`, usando a
fixture `redis_backed_env`/`llm_app_service_redis` já existente (skip gracioso se o
Redis não responder). O endpoint não chama LLM, então não precisa da suíte de
integração pular por falta de Ollama.

1. `test_reset_context__redis_backed__clears_history_key` — popula histórico real
   (`add_messages` ou um `service.chat()`), chama `reset_context`, afirma
   `get_session_history(user.id).messages == []` (ou que a chave `chat_history:{id}`
   não existe mais no Redis). É o único teste que prova que a chave certa é apagada
   de fato — o mock unitário não garante isso.

### 4.4 "Não alcançável via chat"

**Sem teste dedicado.** A garantia é a **ausência** de código: nenhum intent novo em
nenhum grafo, nenhuma entrada de prompt. Testar uma negativa sobre código inexistente
seria frágil e de baixo valor. Os testes de contrato de intent já existentes
(`MainGraph` e sub-grafos enumeram os intents/node names válidos) sinalizariam
qualquer adição indevida. Guard-rail humano (revisão, não teste): nenhum `.md` de
prompt deve ganhar menção a "resetar conversa"/"limpar histórico" como intent.

## 5. Débito técnico identificado (fora de escopo — registrar)

`_get_session_history_factory()` (`infra/ioc.py`, ~linha 266) é chamada
separadamente em 4 pontos (`get_vehicle_maintenance_graph`, `get_pet_health_graph`,
`get_only_talk_graph`, `get_llm_app_service`), cada uma criando seu próprio closure.
Em **modo Redis** isso não importa (mesma chave `chat_history:{user_id}` no store
compartilhado — o reset funciona corretamente em produção). Em **modo in-memory**
(sem `CACHE_DB_CONNECTION_STRING`) o problema é mais grave que "4 stores
desconectados": `get_llm_app_service()` **não** é cacheado em `_repo_cache`
(diferente dos graphs, que são singletons por processo) — é reconstruído a cada
`Depends()`, então o histórico em fallback in-memory já não sobrevive entre requests,
independentemente desta feature. Não bloqueia o reset; tratar como issue própria de
infraestrutura se o modo in-memory precisar ser confiável algum dia.

## 6. Arquivos a tocar

| Arquivo | Mudança |
|---|---|
| `application/appservices/llm_app_service.py` | novo método `reset_context()` |
| `routes.py` | rota `DELETE /user/{id}/chat-history` |
| `tests/unit_tests/test_llm_app_service_reset_context.py` | novo (6 testes) |
| `tests/unit_tests/test_routes_chat_history_delete.py` | novo (2 testes) |
| `tests/unit_tests/test_routes_require_api_key.py` | +1 rota na lista (se parametrizado) |
| `tests/integration_tests/test_llm_app_service_reset_context_redis.py` | novo, opcional (1 teste) |

Sem mudanças em `infra/prompts/`, `domain/`, `infra/ioc.py` (a factory
`get_llm_app_service` já injeta `get_session_history`), nem em qualquer grafo
LangGraph.

## 7. Ordem de implementação (TDD)

1. Escrever `test_llm_app_service_reset_context.py` (6 testes) — **falha** (método
   inexistente).
2. Implementar `LlmAppService.reset_context()` — testes 1–6 passam.
3. Escrever `test_routes_chat_history_delete.py` — **falha** (rota inexistente).
4. Adicionar a rota em `routes.py`; adicionar à lista de `require_api_key` se
   parametrizada — testes passam.
5. (Opcional) Escrever + rodar o teste de integração Redis (skip se sem Redis).
6. Suíte unitária completa verde; sem regressão.
