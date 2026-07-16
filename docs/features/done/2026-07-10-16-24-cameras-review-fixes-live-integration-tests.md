# Plano: Correções da funcionalidade de Câmeras + bateria de integração real

- **Status:** done
- **Criado em:** 2026-07-10 16:24
- **Implementado em:** 2026-07-16
- **PR/commit:** — (aguardando commit na branch `fix/cameras-review`)
- **Branch (a criar quando o plano for aprovado):** `fix/cameras-review`
- **Consultorias realizadas (obrigatórias):** `arquiteto`, `especialista-de-prompt`,
  `programador-tester` (2026-07-10)

---

## 1. Contexto e veredicto da revisão

Revisão da funcionalidade de câmeras executada **contra o Home Assistant local**
(`docker/test-backends/docker-compose.dev.yml` + `bootstrap_ha.py`, câmera
`local_file` `camera.camera_sala` com alias "câmera da sala" servindo um PNG).

**Veredicto: o caminho fim-a-fim FUNCIONA.** Validado ao vivo:

- Repositório REST (`get_state` → `idle`/friendly_name; `get_snapshot` → bytes
  PNG; entidade inexistente → 404 tratado pelos handlers com mensagem
  amigável).
- Descoberta WebSocket (`get_exposed_entities` → `camera.camera_sala`) e
  sincronização de aliases (`update_entity_aliases()` popula o SQLite).
- Chat completo com Ollama remoto: "Mostre a câmera da sala" →
  `['smart_home_security_cams']` → data URI com base64 que decodifica de volta
  aos bytes PNG originais; "A câmera da sala está ativa?" → "Camera Sala:
  idle". Os 90 testes unitários de câmera passam.

Porém a revisão encontrou **1 defeito grave, 2 bugs confirmados ao vivo, e um
gap de cobertura** (a bateria de integração atual nunca exercita o caminho
real — só roteamento). Este plano corrige tudo em TDD e cria a bateria real.

## 2. Achados (por severidade)

| # | Severidade | Achado | Evidência |
|---|---|---|---|
| F1 | **Grave** | A data URI do snapshot é persistida **verbatim** no histórico de conversa (`llm_app_service.py::_persist_turn`, `AIMessage(content=output)`) e reinjetada no `MessagesPlaceholder("history")` do `OnlyTalkGraph` no turno seguinte — estouro de contexto **mesmo em single-intent**; todo "mostre a câmera" de hoje envenena o histórico. O mesmo output cru vai ao `MemoryAppService.learn_from_message` (`routes.py:73-77`) → o LLM do MemoryGraph recebe a base64 gigante. O comentário "base64 never enters the history" protege só imagens de **entrada**. | Verificado no código (linhas citadas) |
| F2 | **Alto** | Merge multi-intent: `output_cams` entra na lista `outputs` de `MainGraph._handle_final_response`; com 2+ intents ("mostra a câmera e apaga a luz") a data URI (potencialmente MBs) é enviada ao LLM de merge — truncação/corrupção garantida. Só a shopping list tem bypass (`SHOPPING_LIST_HEADER`). Single-intent escapa por `len(outputs) <= 1`. | Verificado no código |
| F3 | **Médio** | MIME hardcoded: o graph monta `data:image/jpeg;base64,...` mas o HA serviu `image/png` (confirmado ao vivo: bytes com magic PNG dentro de URI declarada jpeg). `SmartHomeCameraSnapshot` **já tem** `content_type: str = "image/jpeg"` (`entities.py:357`) — mas o repositório não o preenche e o graph não o consome. | Confirmado ao vivo |
| F4 | **Médio** | Prompt↔código inconsistentes: o classify promete multi-câmera via pipe (`"sala\|garagem"`) e `_find_entity_ids` retorna lista, mas os handlers usam só `entity_ids[0]` — as demais câmeras são ignoradas silenciosamente. | Verificado no código |
| F5 | **Baixo** | Status exibido cru em inglês ("Camera Sala: idle"); `is_available` computado e nunca usado. | Confirmado ao vivo |
| F6 | **Baixo** | Prompt órfão `infra/prompts/smart_home_cameras_graph_response.md` — nenhum `load_prompt` o carrega (scaffold copiado do sensors, que usa o dele; o de câmeras foi corretamente substituído por template determinístico). | grep confirmado |
| F7 | **Baixo** | `show_snapshot` genérico ("mostre todas as câmeras") → campo vazio → handler retorna `{}` → "Dispositivo não encontrado." — resposta errada para o pedido. | Análise de código |
| F8 | **Menores** | (a) Sessões `aiohttp` nunca fechadas nos 4 repositórios REST do HA (singletons via IoC — sem leak por request, mas sem shutdown limpo); (b) repo de câmera envia `Content-Type: application/json` em GET binário e passa `headers` duplicado; (c) `_handle_smart_home_security_cams` reconstrói `GraphInvokeRequest` descartando `memories`/`context_hints` (hoje inócuo — armadilha de evolução); (d) `output_show_snapshot` reusado com dois significados no state. | Parecer do arquiteto |

Não-achados (padrões corretos): `_find_entity_ids` com 2ª chamada LLM é o
padrão compartilhado por todos os graphs de smart home (não é desvio);
timeouts do repositório adequados; sem violação de camadas.

## 3. Decisões centrais (divergências resolvidas)

### 3.1 Bypass do merge — **split por linha**, prefixo como marcador natural

**Escolhido** (convergência `arquiteto` + `especialista-de-prompt`): em
`_handle_final_response`, separar `output_cams` **por linha**: linhas que
começam com `data:image/` vão para o bypass (nunca passam pelo LLM de merge,
são concatenadas ao final — mesmo shape do bypass do `SHOPPING_LIST_HEADER`,
`bypass + "\n\n" + merged`); linhas restantes (status) seguem para o merge
normalmente. Constante `IMAGE_DATA_URI_PREFIX = "data:image/"` em
`application/graphs/markers.py` — o prefixo **já é** o marcador, inequívoco;
um wrapper artificial obrigaria o cliente a fazer strip.

**Descartado:** bypass verbatim do `output_cams` inteiro (sugestão do
`programador-tester`, mais simples) — engoliria as linhas de status junto,
impedindo o merge natural delas com as outras intents; e o fix F4
(multi-câmera) produz exatamente o formato misto URI+status por linhas, que
exige o split de qualquer forma.

**Sem regra espelhada no prompt de merge** (parecer do especialista): um LLM
de 12B não reproduz megabytes de base64 nem obedecendo — regra impossível de
cumprir é falsa segurança, e gastaria tokens em todo turno multi-intent. A
defesa em profundidade é em Python: garantir por filtro que nenhuma linha com
o prefixo entre na lista `outputs`.

### 3.2 F1 — sanitização de data URI fora do canal de resposta

Helper puro na camada application (ex.
`application/appservices/output_sanitizer.py`):
`replace_image_data_uris(text, placeholder="[snapshot da câmera exibido]")` —
substitui **linhas** iniciadas por `IMAGE_DATA_URI_PREFIX`. Aplicado em:

1. `_persist_turn` — o `AIMessage` gravado no histórico recebe o texto
   sanitizado (a resposta HTTP ao cliente continua com a URI intacta — ela é o
   entregável).
2. Caminho do `learn_from_message` — sanitizar o `output` antes do MemoryGraph
   (no `routes.py` ou na entrada do `MemoryAppService`; decidir na
   implementação pelo ponto que cubra todos os chamadores).

### 3.3 F3 — content_type: ligar as pontas que já existem

- Repositório: capturar `response.content_type` (aiohttp parseia o header).
  **Guarda:** header ausente → aiohttp devolve `application/octet-stream`; só
  aceitar valores `image/*`, senão manter o default `image/jpeg` da entidade
  (URI inválida jamais).
- Graph: `f"data:{snapshot.content_type};base64,{encoded}"`.
- Entidade: **inalterada** (campo e default já existem — retrocompatível).

### 3.4 F5 — mapa fechado de estados em pt-BR no graph

Constante de módulo no próprio cameras graph (o graph é a camada de
apresentação deste fluxo; domain fica neutro de idioma; `infra/prompts/` é
para templates de LLM):

```python
_CAMERA_STATE_PT = {"idle": "em espera", "recording": "gravando",
                    "streaming": "transmitindo ao vivo",
                    "unavailable": "indisponível"}
```

Lookup por `state.lower()`, fallback para o estado cru. ("em espera" e não
"disponível" — não colapsar semântica.) `is_available` permanece não usado
(remoção em limpeza futura, fora deste escopo). A tabela vem do prompt órfão
(F6), que é **removido** no mesmo PR — mantê-lo criaria o risco de alguém
religá-lo (base64 por LLM é o antipadrão que este plano elimina).

### 3.5 F4 — multi-câmera: corrigir agora, com cap

O encanamento já suporta (lista + pipes no id-parser); só o `[0]` trunca.
- `check_status`: iterar e juntar linhas — trivial.
- `show_snapshot`: iterar, **uma data URI por linha**, com cap explícito
  `_MAX_SNAPSHOTS_PER_REQUEST = 3` (N URIs de MBs multiplicam a resposta
  HTTP). Contrato do cliente não muda: o output misto já é `\n`-joined; quem
  consome já faz split por linha.
- F7 (pedido genérico "mostre todas as câmeras"): com o iterador pronto,
  campo genérico vazio + entidades disponíveis → responder pedindo para
  especificar OU mostrar todas até o cap — **decidir na implementação pelo
  caminho mais simples; default recomendado: pedir para especificar** (mostrar
  todas muda contrato de tamanho de resposta).

## 4. Ajustes de prompt (parecer do `especialista-de-prompt`)

`smart_home_cameras_graph.md` (qualidade geral boa — aspas retas, JSON raso,
multi-intent coberto):

1. Adicionar few-shot de `check_status` genérico/plural ("As câmeras estão
   funcionando?").
2. Adicionar few-shot de `check_status` multi-câmera ("As câmeras da sala e da
   garagem estão gravando?" → `"sala|garagem"`).
3. Normalizar o exemplo de `not_recognized` para valor `""` (hoje preenche
   `"nao_relacionado_a_cameras"`, que o código ignora — convenção a menos).

`smart_home_cameras_graph_id_parser_by_alias.md` (bom; whitelist em Python
contém alucinação):

4. Few-shot de saída mista parcial (`"cozinha|banheiro"` →
   `camera.cozinha|None`) — desambigua o conflito entre "retorne None para
   aquela posição" e o formato global.
5. Alinhar o formato declarado do dicionário com o que o código injeta
   (`str(dict)`) — ou, melhor, formatar o dict em linhas `'nome' = 'id'` no
   código antes de injetar, como o prompt já promete.

`main_graph_final_response.md`: **inalterado** (§3.1).
`smart_home_cameras_graph_response.md`: **removido** (§3.4).

## 5. Estratégia TDD (parecer do `programador-tester`)

Ordem de nascimento — cada arquivo vermelho antes da implementação:

### 5.1 F3 — content_type

- `test_home_assistant_smart_home_camera_repository.py`
  (`TestGetSnapshot`; helper `_mock_aiohttp_session_bytes` ganha
  `content_type` — para "ausente", simular `application/octet-stream`, que é o
  que o aiohttp devolve, não `None`):
  `test_get_snapshot__png_content_type_header__snapshot_content_type_is_image_png`;
  `test_get_snapshot__jpeg_content_type_header__snapshot_content_type_is_image_jpeg`;
  `test_get_snapshot__octet_stream_content_type__defaults_to_image_jpeg`;
  `test_get_snapshot__non_image_content_type__defaults_to_image_jpeg`.
- `test_smart_home_camera_entities.py`:
  `test_smart_home_camera_snapshot__constructed_without_content_type__defaults_to_image_jpeg`
  (trava retrocompatibilidade).
- `test_smart_home_cameras_graph_show_snapshot.py` (os 2 testes atuais de
  `data:image/jpeg` permanecem como caso JPEG):
  `test_handle_show_snapshot__png_snapshot__data_uri_prefix_is_image_png`;
  `test_handle_show_snapshot__png_snapshot__base64_decodes_to_original_png_bytes`
  (magic bytes reais, roundtrip completo, fatiar após a primeira vírgula);
  `test_handle_show_snapshot__snapshot_with_default_content_type__uri_uses_jpeg`.

### 5.2 F5 — estados pt-BR

`test_smart_home_cameras_graph_check_status.py`:
`test_handle_check_status__known_states__mapped_to_pt_br` (parametrizado nos 4
pares, asserta `friendly_name` preservado — "Camera Sala: gravando");
`test_handle_check_status__unknown_state__falls_back_to_raw_state`;
`test_handle_check_status__uppercase_known_state__still_mapped`.

### 5.3 F4/F7 — multi-câmera

`test_smart_home_cameras_graph_show_snapshot.py` / `..._check_status.py`:
`test_handle_show_snapshot__two_cameras__two_data_uri_lines`;
`test_handle_show_snapshot__more_than_cap__truncated_to_cap`;
`test_handle_check_status__two_cameras__two_status_lines`;
`test_handle_show_snapshot__generic_request_with_available_entities__asks_to_specify`
(comportamento decidido em §3.5).

### 5.4 F2 — bypass do merge

`test_main_graph_camera_snapshot_bypass.py` (novo; espelha o padrão do teste
do `SHOPPING_LIST_HEADER`):
`test_final_response__data_uri_in_output_cams_and_second_output__merge_llm_not_called_with_uri`
(inspecionar `invoke.call_args`);
`test_final_response__data_uri_and_conversational_output__uri_byte_identical_in_final_output`
(igualdade exata do trecho, não `in` de prefixo);
`test_final_response__data_uri_and_conversational_output__merged_text_preserved`;
`test_final_response__data_uri_single_intent__no_merge_llm_call_and_output_is_uri`
(regressão do caminho `len(outputs) <= 1`);
`test_final_response__camera_status_text_in_output_cams__goes_through_normal_merge`;
`test_final_response__output_cams_with_uri_and_status_lines__status_merged_uri_bypassed`
(pina a decisão §3.1 de split por linha);
`test_final_response__merge_llm_returns_empty__uri_still_present`;
`test_final_response__text_mentioning_data_image_mid_string__not_bypassed`
(detecção por prefixo de linha, não `in`).

### 5.5 F1 — sanitização do histórico/memória

- `test_output_sanitizer.py` (novo): linha-URI única → placeholder; misto
  URI+status → só a linha da URI substituída; texto sem URI → intacto;
  múltiplas URIs → todas; `data:image/` no meio de frase → intacto.
- `test_llm_app_service_*`:
  `test_persist_turn__output_with_data_uri__history_receives_placeholder_not_uri`
  (mock do `get_session_history`, inspecionar o `AIMessage`);
  `test_persist_turn__plain_output__unchanged`.
- Memória: teste no ponto escolhido (§3.2) garantindo que o texto que chega ao
  MemoryGraph não contém `data:image/`.

### 5.6 F6/F8 — limpeza

Sem testes novos: remover o `.md` órfão (suíte acusa se algum `load_prompt`
quebrar); F8a (close das sessões aiohttp) **registrado, fora do escopo** (item
de lote futuro com lifespan do FastAPI); F8b/F8c corrigidos de carona com
testes existentes (o handler do MainGraph passa a encaminhar `data["input"]`
como os demais); F8d opcional.

## 6. Nova bateria de integração (o gap principal)

**Arquivo novo** `tests/integration_tests/test_llm_app_service_chat__smart_home_cameras_live.py`
— a bateria antiga **permanece intocada** (documenta a degradação graciosa sem
aliases; atualizar só a docstring apontando para a nova).

**Fixture de seeding — function-scoped** (o `integration_db_path` recria o DB
por teste; seeding module-scoped seria apagado no 2º teste):
`seeded_camera_aliases(home_assistant_available, integration_db_path)` rodando
`asyncio.get_event_loop().run_until_complete(get_smart_home_app_service().update_entity_aliases())`
(padrão do repo, sem pytest-asyncio; o `close()` do WS já acontece no
`finally` do service). Custo de 1 roundtrip WS por teste — desprezível contra
a latência do gemma4; não otimizar agora.

**Skip gracioso em camadas, dentro da fixture:**
1. `home_assistant_available` (conectividade — já existe);
2. `HOME_ASSISTANT_TOKEN` vazio → skip "rode bootstrap_ha.py";
3. pós-seed: alias repo vazio para `camera.` → skip "câmera/aliases ausentes
   no HA" (valida pelo mesmo caminho que o graph usa; probe REST separado é
   redundante).

**Casos (bateria pequena de propósito — 3 testes):**

1. `test_chat__show_snapshot_camera_sala__returns_decodable_png_data_uri` —
   "Mostre a câmera da sala": `smart_home_security_cams` em intents; output
   inicia com `data:image/png;base64,` (pós-F3);
   `base64.b64decode(..., validate=True)`; decoded inicia com
   `b"\x89PNG\r\n\x1a\n"`; tamanho > 0.
2. `test_chat__check_status_camera_sala__returns_friendly_name_and_mapped_state`
   — asserta `"Camera Sala" in output` e estado ∈ valores do mapa pt-BR
   (**não** fixar só "em espera": o estado real do local_file pode variar;
   assertar contra o conjunto fechado ainda pega inglês cru vazando).
3. `test_chat__snapshot_and_light_off__uri_intact_after_merge_bypass` —
   "mostra a câmera da sala e apaga a luz da sala" — o único ponto que prova o
   bypass fim-a-fim com LLM real. Asserts: exatamente 1 ocorrência de
   `data:image/png;base64,`; trecho decodifica para PNG; sobra texto
   conversacional não-vazio fora da URI. **Mitigação de flakiness:** se o
   classificador emitir só 1 intent, `pytest.skip` (o SUT é o bypass, não o
   classificador, que tem bateria própria) — sem isso herda-se a variância do
   gemma4 num teste caro.

**Riscos registrados:** a 2ª chamada LLM do `_find_entity_ids` (timeout 15s →
degrada para "Dispositivo não encontrado") é a maior fonte de flakiness sob
GPU carregada — se flakar em CI, aumentar o timeout via plano, não afrouxar o
assert. xdist: DB/aliases por worker isolam; o HA compartilhado é
read-only para câmeras e o único mutador ("apaga a luz") não tem assert de
estado. Histórico in-memory keyed por `user.id` novo por teste — sem
contaminação.

## 7. Fora de escopo

- F8a (shutdown limpo das sessões aiohttp dos 4 repositórios REST + lifespan
  FastAPI) — lote separado.
- Remoção do campo `is_available` não usado.
- Formatação LLM de respostas de câmera (o template determinístico é o design
  correto — o prompt órfão morre).
- Streaming/gravação de vídeo, snapshots por área ("câmeras da sala"),
  histórico de snapshots.

## 8. Sequência de implementação

1. §5.1 (F3, vermelho) → repositório captura `content_type` + graph monta URI
   dinâmica.
2. §5.2 (F5, vermelho) → mapa pt-BR + remoção do prompt órfão (F6).
3. §5.3 (F4/F7, vermelho) → iteração multi-câmera com cap + genérico.
4. §5.4 (F2, vermelho) → `IMAGE_DATA_URI_PREFIX` em markers + bypass por linha
   no `_handle_final_response` + F8c de carona.
5. §5.5 (F1, vermelho) → `output_sanitizer` + `_persist_turn` + caminho da
   memória.
6. Ajustes de prompt (§4) — junto dos passos 3-4 (few-shots multi-câmera).
7. Bateria de integração (§6) com o stack docker + Ollama vivo — por último,
   depois dos fixes green nas units (os asserts `data:image/png` dependem de
   F3).
8. Rodar a suíte completa + a bateria antiga de câmeras (deve continuar verde).
9. Mover este plano para `doing/` ao iniciar e `done/` ao concluir.
