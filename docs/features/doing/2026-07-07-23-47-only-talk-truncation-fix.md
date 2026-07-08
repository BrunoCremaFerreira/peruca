# Plano: Correção do truncamento de respostas do OnlyTalkGraph (persona/pets)

- **Status:** doing (C1 implementado; causa raiz confirmada; C2/C3 são follow-ups)
- **Criado em:** 2026-07-07 23:47
- **Implementado em:** 2026-07-08 (C1) — branch `feature/pet-health-events-registry`
- **PR/commit:** —
- **Origem:** relato do usuário — "Como é o seu irmão Câníça?" → resposta cortada no
  meio ("...orelhas caídas **que dão**"), ocorrendo "quase sempre" ao citar os pets.

> **CAUSA RAIZ CONFIRMADA (H1):** o usuário reportou **130 mensagens no contexto**
> da conversa onde o corte ocorreu. O `OnlyTalkGraph` injetava o histórico inteiro,
> então 130 mensagens + persona + memórias estouravam (ou quase) o `num_ctx=8192`,
> deixando quase nenhum orçamento de geração → o modelo parava no meio da frase.
>
> **C1 implementado (TDD):** janela de histórico no `OnlyTalkGraph`
> (`history_max_messages`, default via `LLM_ONLY_TALK_HISTORY_MAX_MESSAGES=30`; <=0
> mantém o histórico completo). `only_talk_graph.py` corta para as últimas N
> mensagens; setting em `infra/settings.py`; wiring em `ioc.py`; 3 testes novos
> (`test_only_talk_graph_history_window.py`). Suíte: 1464 verdes.
>
> **Follow-ups (não bloqueiam o fix principal):** C2 (robustez de thinking /
> garantir `reasoning=False` explícito e endurecer `_remove_thinking_tag` para
> `<think>` sem fechamento) e C3 (corte da descrição da persona por palavra).

---

## 1. Sintoma

Na conversa livre (caminho `OnlyTalkGraph`), a resposta do Peruca é cortada no meio
de uma frase, sem pontuação e sem reticências. Correlacionado com menções a pets.
Exemplo real: *"O Câníça é uma gracinha, Bruno. Ele é um vira-lata pequeno e
gordinho, com aqueles olhos castanhos muito expressivos e orelhas caídas que dão"*
(fim abrupto).

## 2. Investigação já realizada (evidências)

Diagnóstico empírico contra o Ollama real (gemma4:12b em `unix.rtx-server`):

1. **`POST /api/chat` com `think=false`, `num_predict=-1`, `num_ctx=8192`** (o system
   prompt de persona + o bloco de irmãos com o pet) → resposta **COMPLETA**,
   `done_reason=stop`, `eval_count≈66`. **Sem truncamento no modelo cru.**
2. **`POST /api/chat` SEM `think`** (thinking ligado, padrão do gemma4) →
   `eval_count=67` mas `message.content=''` (**vazio**); os tokens vão para o canal
   de *thinking*. Ou seja, **gemma4:12b é um thinking model** e o tratamento
   thinking/content é a área sensível.
3. **Config do app** (`infra/settings.py`/`ioc.py`): `num_predict=-1` (sem cap),
   `num_ctx=8192`; `get_llm_chat` passa `reasoning=_resolve_reasoning(...)`.
   `_resolve_reasoning(None)` → `settings.llm_reasoning` (default **False**). Com
   `langchain_ollama==1.1.0`, `reasoning=False` → `think=false` → resposta limpa e
   completa (bate com o teste 1).
4. **Achado estrutural confirmado**: `OnlyTalkGraph.invoke` injeta o histórico de
   conversa **inteiro, sem janela** — `only_talk_graph.py:79`
   `history_messages = self._get_session_history(user.id).messages`, propagado
   integralmente ao chain. O `VehicleMaintenanceGraph`, por contraste, limita a 6
   mensagens (`_recent_history`). `CACHE_DB_CONNECTION_STRING` vazio → store em
   memória; sem `CHAT_HISTORY_TTL` → o histórico **cresce indefinidamente** dentro
   da sessão (e sem TTL no Redis, cresce para sempre em produção).

**Conclusão parcial:** o modelo cru **não** trunca com `think=false`. O corte é
introduzido pelo pipeline do app e/ou pela pressão de contexto. Não foi possível
reproduzir o truncamento exato aqui porque (a) o host LLM ficou intermitente e
(b) o truncamento depende do estado acumulado da sessão do usuário, que não temos.

## 3. Hipóteses de causa raiz (ranqueadas)

### H1 — Histórico não-janelado enche o `num_ctx` (mais provável)
`OnlyTalkGraph` injeta todo o histórico. Conforme a sessão acumula turnos (store em
memória, sem TTL), o prompt cresce em direção a `num_ctx=8192`. Quando o prompt
ocupa quase todo o contexto, o Ollama gera pouquíssimos tokens e **para no meio**
(`done_reason=length`). Explica o "quase sempre" e a **piora progressiva** a cada
turno da mesma sessão de teste. Não é intrinsecamente "sobre pets" — é sobre uma
sessão de conversa longa, que é justamente o que o usuário fez ao testar os pets em
sequência. O bloco `{siblings}` adicionado na feature de pets soma alguns tokens por
turno, agravando marginalmente.

### H2 — Vazamento de *thinking* no `content` (possível, depende do runtime)
Se, no ambiente do usuário, `reasoning` resolver para `None` (ex.: `LLM_REASONING`
vazio/mal-parseado, ou um modelo cujo default é raciocinar), o gemma4 emite
`<think>…</think>` **dentro do `content`** (doc do `langchain_ollama` 1.1.0). O
`Graph._remove_thinking_tag` remove o bloco `<think>.*?</think>` (fechado), mas:
- um bloco `<think>` **sem fechamento** (geração longa de raciocínio consumindo o
  turno) não casa a regex → nada é removido e a resposta fica poluída/estranha; e
- combinado com pressão de `num_ctx`, o raciocínio consome o orçamento e a resposta
  final sai truncada.

### H3 — Corte cosmético da descrição da persona (menor, não é a causa do corte de saída)
`LlmAppService._user_pets_hints` faz `sanitize_for_prompt(pet.description, 200)`, que
corta em 200 chars no meio da palavra e anexa "…". Isso trunca o **texto injetado**
(entrada), não a **saída** do modelo. Pode fazer o Peruca reproduzir uma descrição
truncada, mas não explica o corte de frase da resposta.

## 4. Passo 0 — Diagnóstico definitivo (fazer ANTES de corrigir)

Instrumentar `OnlyTalkGraph.invoke` (log `INFO`/`DEBUG` temporário, sem vazar
conteúdo sensível em produção) capturando por turno:
- `len(history_messages)` e um proxy de tokens do prompt (`prompt_eval_count` do
  `response_metadata`);
- `response_metadata.done_reason` e `eval_count`;
- `len(content)` bruto e presença de `additional_kwargs.reasoning_content` /
  substring `"<think>"` no `content`.

Reproduzir o fluxo do usuário. Leitura:
- `done_reason == "length"` → confirma **H1/H2** (estouro de `num_ctx`/`num_predict`).
- `done_reason == "stop"` com `content` curto e limpo → comportamento do modelo /
  persona (revisar prompt e H3), não corte de contexto.
- `reasoning_content` presente ou `"<think>"` no `content` → confirma **H2**.

Um teste unitário deve acompanhar cada correção (TDD): mockar o `llm_chat` para
devolver metadata/conteúdo representativos e asseverar o comportamento do pipeline.

## 5. Correções propostas (por hipótese; implementar guiado pelo Passo 0)

### C1 — Janela de histórico no `OnlyTalkGraph` (endereça H1) — prioridade alta
- Limitar as mensagens injetadas a uma janela (ex.: últimas `N` mensagens, espelhando
  o `_recent_history` do veicular — `MAX = 6`–`12` mensagens — ou um orçamento de
  tokens que **reserve** headroom de geração, ex.: usar no máx. ~60% de `num_ctx`
  para o prompt). Preferir uma janela por nº de mensagens (simples, determinística,
  testável) na v1; orçamento por tokens como evolução.
- Teste: com um histórico grande (mock), asseverar que o chain recebe no máx. `N`
  mensagens (o mais recentes), preservando a ordem.
- Considerar, em paralelo, subir `num_ctx` (ex.: 16384) se o hardware permitir e/ou
  documentar `CHAT_HISTORY_TTL_SECONDS`/janela como mitigação de crescimento.

### C2 — Robustez de thinking + garantir `reasoning=False` (endereça H2) — prioridade alta
- Confirmar (via Passo 0) que `reasoning=False` chega ao Ollama no ambiente do
  usuário. Se `_resolve_reasoning` puder devolver `None`, considerar **default
  explícito `False`** para o `OnlyTalkGraph` (nunca `None`), evitando o modo de
  raciocínio padrão do gemma4 que injeta `<think>` no `content`.
- Endurecer `Graph._remove_thinking_tag` para o caso de **`<think>` sem
  fechamento**: se houver `<think>` sem `</think>`, remover do `<think>` até o fim
  (ou até o primeiro parágrafo de resposta), em vez de deixar passar. Cobrir com
  testes: bloco fechado, bloco aberto sem fechar, sem bloco, e o caso ```` ``` ````.

### C3 — Corte da descrição por palavra (endereça H3) — prioridade baixa
- Em `sanitize_for_prompt` (ou no caller da persona), cortar em fronteira de palavra
  e/ou elevar o cap da descrição da persona (ex.: 300–400 chars) — cosmético.

## 6. Riscos e não-objetivos
- **Não** alterar o comportamento de escrita de histórico (o `OnlyTalkGraph` é
  read-only; a persistência central em `LlmAppService._persist_turn` permanece).
- **Não** reintroduzir `asyncio.run()` em nós de graph.
- Janela de histórico curta demais degrada a memória conversacional; calibrar `N`.
- Toda mudança em `_remove_thinking_tag` afeta **todos** os graphs — cobrir com
  testes de regressão (é usado por main/only_talk/vehicle/pet/etc.).

## 7. Aberto para confirmação do usuário (acelera o diagnóstico)
- Qual ambiente está sendo testado: modelo (`gemma4:12b` local vs `gemma4:e4b` prod)
  e valor de `LLM_REASONING`?
- O store de histórico é Redis ou memória, e a sessão de teste teve muitos turnos
  antes do corte aparecer? (valida H1)
