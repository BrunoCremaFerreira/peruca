# Plano: Recebimento de imagens em base64 no chat (entrada multimodal)

- **Status:** done (Fases A, B e C implementadas; segurança aprovada)
- **Criado em:** 2026-07-05 03:07
- **Implementado em:** Fases A, B e C — 2026-07-05
- **PR/commit:** commit na branch `development` (2026-07-05)

> **Progresso Fase A:** concluída em TDD (dataclasses + `images`, `ImageValidator`,
> settings de limite, propagação e validação no `LlmAppService`, short-circuit e
> canal lateral `image_description` no `MainGraph`, `_build_human_content` na base
> `Graph`, `OnlyTalkGraph` multimodal com retorno `dict` e split do marcador
> `<<<DESC_IMAGEM>>>`, persistência da descrição no `_persist_turn`, prompts
> `main_graph.md`/`only_talk_graph.md`, wiring na `ioc.py`) + verificação e2e do
> endpoint `/llm/chat`.
>
> **Progresso Fase B:** concluída em TDD. ABC `ImageStore`
> (`save`/`get`/`next_index`) no domínio; `RedisImageStore` (facade síncrono sobre
> `async_runner`, chave `image:{user_id}:{image_id}`, TTL, cap por usuário,
> isolamento cross-user por construção); settings `chat_image_store_ttl_seconds`
> (86400) e `chat_image_store_max_per_user`; factory `get_image_store()` (None sem
> Redis, sem fallback in-memory). `LlmAppService` salva os blobs **antes** da
> referência no histórico (atomicidade), grava a linha `[Imagem #N enviada pelo
> usuário: <descrição>]` e degrada para linha sem `#N` quando o `save` falha ou não
> há store. **Decisão de simplificação:** o contrato Fase A do `OnlyTalkGraph`/
> `MainGraph` (uma `image_description` por turno) ficou **inalterado**; toda a
> lógica de store vive no `LlmAppService`, e o `image_id` é o índice monotônico
> por usuário (`#N`) — mapeia direto para a chave da store, deixando a Fase C
> viável sem retrabalho. 1020 testes unitários verdes + verificação e2e da cadeia
> `LlmAppService` + `RedisImageStore` concreto.
>
> **Progresso Fase C:** concluída em TDD. Gate de re-visão no `OnlyTalkGraph`:
> `image_store` injetado; 1º passe pode emitir a sentinela
> `<<<REVER_IMAGEM: #N | mais_recente>>>` (parsing por regex, `#N` reduzido a
> dígitos puros); o graph resolve o base64 via `image_store.get(user.id, id)` /
> `latest_id(user.id)` — **sempre** no escopo do `user.id` — e faz um 2º passe
> multimodal com a imagem reinjetada, emitindo `<<<DESC_IMAGEM>>>` atualizado.
> Salvaguardas: sem store / sem blob ⇒ sentinela stripada (no-op, 1 passe); teto
> de 1 re-visão por turno (2ª saída não é re-avaliada); acesso à store via facade
> síncrono (sem `asyncio.run` no nó). `MainGraph` transita `revised_image_index`
> no canal lateral; `LlmAppService` persiste a descrição enriquecida sob `#N` no
> turno de re-visão (follow-ups repetidos ficam baratos). Diretiva da sentinela
> injetada **condicionalmente** (só quando há `[Imagem #` no histórico).
> `main_graph.md` reforça follow-up de foto → `["only_talking"]` (sem intent novo).
>
> **Revisão de segurança (`especialista-de-seguranca`) — obrigatória:** aprovou o
> isolamento cross-user (id sempre no escopo do `user.id`; `#N` só dígitos), o
> parsing robusto do handle, o teto de re-visão e a não-persistência do base64.
> Correções aplicadas antes do sign-off:
> - **H-01 (alta, DoS):** `ImageValidator.validate_data_uri` agora estima o
>   tamanho (O(1), sem alocar) e **recusa decodificar** payload acima do limite —
>   o guard de tamanho passa a atuar de fato antes do `base64.b64decode`.
> - **M-01 (média, prompt injection via OCR):** `LlmAppService._sanitize_description`
>   colapsa whitespace/newlines e trunca em 500 chars antes de persistir a
>   descrição (imagem é conteúdo controlável pelo atacante).
> - **B-01 (baixa, log):** `logger.debug` deixou de logar o `ChatRequest` inteiro
>   (base64); loga só `message`, ids e contagem de imagens.
>
> **Pré-existente / fora de escopo:** endpoint `/llm/chat` sem autenticação
> (SEC-001) — todo o isolamento por imagem assume que o chamador é o dono do
> `external_user_id`.
>
> Total: **1037 testes unitários verdes** + verificações e2e das três fases.
>
> **Testes de integração** (marcados `integration`; exigem Ollama gemma4
> multimodal e/ou o Redis de teste, com skip gracioso):
> - `tests/integration_tests/test_llm_app_service_chat__images_graph.py` —
>   roteamento com imagem (texto vazio + imagem → `only_talking`; pergunta visual
>   → `only_talking`) e output não-vazio; **validação de entrada** (base64
>   malformado, mime não suportado, não-data-URI, e payload ~8 MiB rejeitado
>   **sem decodificar** — guard DoS) que **roda offline** (levanta `ValidationError`
>   antes de qualquer LLM); persistência Fase B (blob salvo em `image:{user_id}:1`;
>   histórico com a descrição e **sem** base64); smoke de re-visão Fase C
>   (follow-up de detalhe não quebra e mantém `only_talking`).
> - `tests/integration_tests/test_redis_image_store_integration.py` —
>   round-trip real do `RedisImageStore` sobre Redis vivo (save/get, isolamento
>   cross-user, `next_index`/`latest_id`, cap com evicção). `conftest.py` estendido
>   para limpar as chaves `image:*`/`image_ids:*`/`image_seq:*` entre testes.

## Objetivo

Permitir que o endpoint `POST /llm/chat` receba **imagens em base64** junto da
mensagem de texto, para que o LLM (`ChatOllama`, gemma4 multimodal servido por
Ollama) possa interpretá-las na conversa livre (`OnlyTalkGraph`).

Escopo: **entrada** de imagens (o usuário envia foto; o Peruca descreve/comenta).
O assistente **não** devolve imagens — `ChatResponse` não muda.

## Faseamento (entregas independentes)

A feature é entregue em três fases, cada uma com valor próprio e testável isolada:

- **Fase A — Visão no turno + descrição no histórico.** Recebe base64, `OnlyTalkGraph`
  monta `HumanMessage` multimodal, gera resposta + descrição factual (marcador
  `<<<DESC_IMAGEM>>>`) e persiste a descrição no histórico (nunca o base64).
  Entrega valor sozinha, barata. Coberta pelas seções abaixo.
- **Fase B — Store de imagem no Redis (fundação, sem comportamento novo).**
  Guarda o base64 numa store separada (`ImageStore`) e grava um handle `#N` na
  linha de descrição do histórico. Ainda **não** re-injeta — é infraestrutura
  testável isoladamente, retrocompatível.
- **Fase C — Re-visão sob demanda.** Quando um follow-up exige detalhe visual
  que a descrição não cobre, o `OnlyTalkGraph` recupera o base64 da store e
  reprocessa a imagem naquele turno, enriquecendo a descrição. É a fase de maior
  risco (prompt engineering + segurança cross-user) e pode ser revertida sem
  perder A/B.

Fases B e C estão detalhadas em **"Store de imagem e re-visão sob demanda"** mais
abaixo. As decisões e mudanças a seguir, salvo indicação, são da **Fase A**.

## Decisões de design (consolidadas com arquiteto, especialista-de-prompt e programador-tester)

1. **Formato do campo:** `images: list[str]` de **data URIs completos**
   (`"data:image/jpeg;base64,..."`), não base64 cru. É o formato que o
   `ChatOllama` espera nos content blocks, carrega o mime type de forma
   autocontida e evita um DTO intermediário. Plural desde já (gemma aceita várias
   imagens). Default `[]` em todas as camadas ⇒ **retrocompatibilidade total**
   (toda construção posicional existente continua válida).

2. **Quem consome a imagem:** apenas o `OnlyTalkGraph`. Os graphs de ação
   (shopping, lights, climate, sensors, cameras) fazem parsing de literais e
   **ignoram** a imagem — ela apenas trafega no `GraphInvokeRequest` e não é usada
   por eles.

3. **O classificador (`MainGraph._classify_intent`) NUNCA recebe a imagem.**
   Motivos: custo/latência de visão em toda mensagem (o classificador roda
   sempre; gemma4 thinking já é o gargalo) e robustez do parsing por
   `ast.literal_eval`. O payload do classificador continua sendo só
   `{"input": message, "music_is_playing": ...}`.

4. **Roteamento com imagem:**
   - **Texto vazio + imagem presente:** short-circuit em código no `MainGraph`
     → força `["only_talking"]` sem chamar o classificador.
   - **Texto genérico/visual** ("o que é isso?", "descreve isso"): roteia por
     texto — já cai em `only_talking`. Reforçado por regra no `main_graph.md`.
   - **Texto com comando de ação** + imagem: roteia para o graph da ação; a
     imagem é ignorada por ele.

5. **Formato para o ChatOllama:** a imagem vai **no `content` do `HumanMessage`**
   como bloco `{"type": "image_url", "image_url": {"url": "data:image/...;base64,..."}}`,
   **não** via parâmetro `images=` do construtor/`.invoke()` (esse é da API crua
   do Ollama; o `ChatOllama` converte o content block internamente). `get_llm_chat`
   em `ioc.py` permanece inalterado.

6. **Histórico (`_persist_turn`): texto + descrição da imagem, nunca base64.**
   O base64 nunca vai para o histórico (Redis/in-memory) — é relido e reinjetado
   a cada turno e explodiria custo/contexto. **Em vez de um placeholder mudo
   (`"[imagem enviada]"`), persistir uma descrição textual factual da imagem**,
   para que turnos futuros da conversa tenham contexto (ex.: usuário depois
   pergunta "e a cor da camisa na foto?").

   **Como gerar a descrição — opção (C), single-pass, sem chamada LLM extra.**
   O caro na visão é o *prefill* da imagem (embeddings visuais que enchem o
   `num_ctx`), pago **uma vez** na chamada que o `OnlyTalkGraph` já faz. A
   descrição sai como poucos tokens de *output* baratos **na mesma chamada** —
   não é uma 2ª chamada de visão (isso seria a opção B, que dobraria o gargalo
   gemma4-thinking). Reusar só o `AIMessage` (opção A) é insuficiente: a resposta
   do Peruca é curta e no personagem, não descreve conteúdo consultável.

   **Contrato de saída do only_talk (só quando há imagem no turno):** a resposta
   ao usuário, seguida de um marcador sentinela e a descrição factual:

   ```
   <resposta ao usuário, 100% no personagem>
   <<<DESC_IMAGEM>>>
   <descrição factual e objetiva, em português, sem persona>
   ```

   Split por string no marcador (**não** JSON/`eval` — nada de parser de literal
   no only_talk, que hoje é chain puro). A parte antes do marcador é o
   `output` mostrado ao usuário; a parte depois é a descrição de memória
   (removida antes de retornar; o usuário nunca a vê). **Fallback obrigatório:**
   marcador ausente ⇒ `output` = conteúdo inteiro, descrição = `"[imagem enviada]"`.
   A diretiva do marcador é injetada **condicionalmente** (só em turno com
   imagem) para não vazar `<<<DESC_IMAGEM>>>` espúrio no caminho texto-puro.

   **O que é persistido no `history`** (turno do usuário, papel `human`, texto
   apenas): `<texto do usuário>` + linha `\n[Imagem enviada pelo usuário: <descrição>]`
   (só a linha entre colchetes se o texto era vazio). O prefixo entre colchetes
   sinaliza ao modelo que aquilo representou uma foto. O `AIMessage` persiste só a
   parte antes do marcador, como hoje.

   **Tamanho-alvo da descrição:** 2–4 frases (~60–110 tokens), factual e
   consultável (o que é, quem/quantos, cores, texto legível, ambiente, ações),
   sem floreio/persona — cap explícito no prompt para o histórico crescer de forma
   modesta e previsível.

7. **Validação no domínio:** novo `ImageValidator(BaseValidation)` em
   `src/domain/validations/image_validation.py`, padrão fluent com `.validate()`
   obrigatório ao final. Acionado por `LlmAppService.chat()` (mesma fronteira que
   já valida `external_user_id`), **antes** de montar o `GraphInvokeRequest` —
   falha rápida, sem custo de LLM. Limites (tamanho máx, nº máx de imagens,
   allowlist de mime) vêm de `infra/settings.py` e são passados ao validator por
   parâmetro (domínio não importa settings).

## Mudanças por camada

### Domínio (`src/domain/`)
- `entities.py` → `GraphInvokeRequest`: adicionar `images: list[str] = field(default_factory=list)`.
  Tipo primitivo, sem violação de camada.
- `validations/image_validation.py` (novo) → `ImageValidator` com métodos como
  `validate_data_uri`, `validate_mime`, `validate_size`, `validate_count`, seguindo
  o padrão de `UserMemoryValidator`. Usa `ValidationError` de `domain/exceptions.py`.

### Application (`src/application/`)
- `appservices/view_models.py` → `ChatRequest`: adicionar
  `images: list[str] = field(default_factory=list)` (importar `field`).
  `ChatResponse` inalterado.
- `appservices/llm_app_service.py` → em `chat()`:
  - validar imagens via `ImageValidator` (lendo limites de settings) antes de
    montar o request;
  - passar `images=chat_request.images` ao construir `GraphInvokeRequest`;
  - ler `image_description` do resultado do `MainGraph` (canal lateral) e
    repassá-la ao `_persist_turn`;
  - `_persist_turn(user, message, output, image_description=None)`: nunca base64;
    quando `image_description` presente, gravar o `HumanMessage` do usuário como
    `<message>\n[Imagem enviada pelo usuário: <image_description>]` (só a linha
    entre colchetes se `message` vazio). `AIMessage` = `output`, como hoje.
- `graphs/graph.py` (base `Graph`) → helper compartilhável
  `_build_human_content(message, images) -> str | list` que devolve a string
  atual quando não há imagem, ou a lista de content blocks (texto + N blocos de
  imagem) quando há. Mantém a montagem multimodal na camada de aplicação.
- `graphs/only_talk_graph.py`:
  - trocar `("human", "{input}")` por `MessagesPlaceholder("input")` e passar
    `{"history": ..., "input": [human_message]}`, com
    `human_message = HumanMessage(content=self._build_human_content(...))`.
    Caminho sem imagem permanece string ⇒ zero regressão;
  - injetar **condicionalmente** (só com imagem) a diretiva do marcador
    `<<<DESC_IMAGEM>>>` no system prompt;
  - **padronizar o retorno para `dict`**: `{"output": <resposta>, "image_description": <str|None>}`
    (hoje retorna `str` cru — é a única exceção entre os graphs; padronizar
    alinha ao contrato dos demais). O split no marcador separa `output` (antes)
    de `image_description` (depois); fallback se marcador ausente.
- `graphs/main_graph.py`:
  - `MainGraphState` ganha canal lateral `image_description: Optional[str]`;
    `_handle_only_talking` grava `output_only_talking` (para o merge) **e**
    `image_description` (que o `_handle_final_response` **ignora** — não vaza para
    o usuário); `MainGraph.invoke` retorna o state, então `image_description` chega
    ao `LlmAppService`;
  - short-circuit `["only_talking"]` quando `images` não vazio e texto vazio;
  - `_classify_intent` **não** inclui `images` no payload; a imagem é repassada
    intacta aos action nodes.

### Infra (`src/infra/`)
- `settings.py` → novos campos: `chat_image_max_bytes`, `chat_image_max_count`,
  `chat_image_allowed_mimes` (ex.: `image/jpeg`, `image/png`, `image/webp`).
- `ioc.py` → **sem mudança** em `get_llm_chat`. Revalidar `num_ctx` do only_talk
  para o caminho com imagem (visão consome muitos tokens; hoje `llm_num_ctx=8192`).

### Prompts (`src/infra/prompts/`)
- `main_graph.md` → regra curta: perguntas visuais/descritivas ("o que é isso?",
  "o que você vê?", "descreva a imagem") → `["only_talking"]`. (Opcional: hint
  textual booleano `{has_image}`, nunca a imagem em si.)
- `only_talk_graph.md` → nova seção "Imagens": o Peruca observa e comenta a foto
  em português, no personagem; não inventar o que não é visível; referir-se
  naturalmente ("a foto que você me mandou"), nunca termos técnicos; exceção à
  regra de concisão quando a descrição exigir. **Contrato do marcador** (só em
  turno com imagem): emitir a resposta ao usuário, depois `<<<DESC_IMAGEM>>>`,
  depois a descrição factual e neutra (2–4 frases, "anotação para a própria
  memória, que o usuário não vê" — sem persona). Diretiva injetada
  condicionalmente pelo graph, nunca no caminho texto-puro.

## Store de imagem e re-visão sob demanda (Fases B e C)

Objetivo: manter o base64 **fora** do contexto de conversa (só a descrição vive
no histórico), mas guardá-lo numa store para que um follow-up que exija **nova
análise dos pixels** possa reinjetá-lo naquele turno. Default continua barato;
re-visão só paga o *prefill* de imagem quando realmente acionada.

### Reconciliação de duas recomendações (decisão registrada)

Houve divergência entre os agentes sobre **onde decidir a re-visão**:

- O `arquiteto` sugeriu decidir no **classificador** (`main_graph`), emitindo um
  intent `revisit_image`.
- O `especialista-de-prompt` argumentou — de forma decisiva — que isso **quebra o
  contrato mais sensível do sistema**: a saída do classificador é um literal de
  lista parseado por `ast.literal_eval`, e cada intent precisa casar com um **nome
  de nó** do `StateGraph` (o `intent_router` usa a lista como alvos de aresta). Um
  `revisit_image` rotearia para nó inexistente. Re-visão é um **modificador
  ortogonal ao roteamento**, não uma rota.

**Decisão adotada:** a re-visão é um **gate auto-julgado dentro do `OnlyTalkGraph`**
via sentinela de string — o classificador fica **intocado**. O primeiro passe
(texto puro, barato) responde pela descrição do histórico; **só quando** a
pergunta exigir um detalhe visual concreto não coberto pela descrição, o modelo
emite `<<<REVER_IMAGEM: #N | mais_recente>>>`, e o graph faz um 2º passe com o
base64 reinjetado.

**Como isso respeita a restrição "sem `asyncio.run` em nós síncronos":** o
`RedisChatMessageHistory` já expõe hoje interface **síncrona** (`.messages`,
`.add_messages`) sobre um repo async, usando o `async_runner` (loop único do
projeto), e é lido **dentro** do `OnlyTalkGraph`. A `ImageStore` espelha esse
facade síncrono (sobre `async_runner`, **não** `asyncio.run`), então o acesso à
store dentro do graph segue o padrão já sancionado.

### Fase B — `ImageStore` (fundação)

- **Interface (domínio):** novo ABC `ImageStore` em `src/domain/interfaces/data_repository.py`,
  **separado** de `ContextRepository` (ISP — blob store ≠ histórico). Métodos
  mínimos: `save(user_id, image_id, data_uri)`, `get(user_id, image_id) -> Optional[str]`,
  `update_description(...)` se necessário na Fase C. Fala em `str` (data URI),
  sem conhecer Redis.
- **Impl (infra):** `RedisImageStore` em `src/infra/data/external/redis/`, facade
  síncrono sobre `async_runner` (espelha `RedisChatMessageHistory`). Chave Redis
  **namespaced por usuário**: `image:{user_id}:{image_id}` — evita colisão,
  permite limpeza por usuário e **impede resolução cross-user** (segurança: o
  `get` só resolve id do próprio `user.id` da requisição). Valor = data URI
  completo (autocontido).
- **Factory (`ioc.py`):** `get_image_store()` espelhando `_get_session_history_factory`.
  **Sem Redis** (`CACHE_DB_CONNECTION_STRING` vazio) ⇒ store `None` e re-visão
  **desligada** (degrada para o caminho barato); **não** cair em in-memory
  (base64 incharia RAM e não sobrevive entre workers).
- **Settings:** `CHAT_IMAGE_STORE_TTL_SECONDS` (**default 86400 = 24h**, próprio e
  desacoplado do histórico, que hoje é `None`/sem expiry) e
  `chat_image_store_max_per_user` (cap de imagens por usuário — segundo eixo de
  contenção de RAM ao lado do TTL). Como o base64 é pesado (centenas de KB a
  poucos MB por imagem), o TTL é o que limita a RAM; 24h cobre re-visão ao longo
  do dia e expira blobs ociosos. Coerência de TTL: se o blob expira antes da
  descrição, o `get` retorna `None` e o fluxo responde só pela descrição textual
  (referência órfã tratada graciosamente).
- **Handle `#N` no histórico:** a linha passa a ser
  `[Imagem #N enviada pelo usuário: <descrição>]`. O `#N` é o handle estável que
  liga descrição ↔ base64 na store. O `OnlyTalkGraph` gera o `image_id` (retorno
  estendido para `{"output", "image_descriptions": [{"image_id", "index", "description"}]}`,
  lista porque `images` é `list[str]`).
- **Ordenação (atomicidade):** salvar o blob **antes** de persistir a referência
  no histórico (nunca referência apontando para blob inexistente). Falha no save
  ⇒ degrada para gravar só a descrição sem `#N` (re-visão indisponível), sem
  abortar o turno. O `save` fica no `LlmAppService` (coordena com `_persist_turn`,
  que escreve o histórico); o `get`/re-injeção da Fase C fica no graph.

### Fase C — Gate de re-visão

- **Detecção (`OnlyTalkGraph`):** sentinela `<<<REVER_IMAGEM: #N | mais_recente>>>`
  emitida no 1º passe. Split de string (não `eval`). **Salvaguarda:** só tem
  efeito se existir base64 armazenado para a conversa; em conversa sem imagem o
  marcador é ignorado/stripado (falso positivo é inócuo).
- **Resolução "qual imagem":** default **"mais recente"**; referência explícita
  via handle `#N` que o modelo lê das linhas do histórico. **Não** reusar o
  `DisambiguationService` (acoplado a shopping list); disambiguation interativa de
  imagens fica para fase futura.
- **Reinjeção:** o base64 recuperado entra pelo **mesmo** mecanismo de
  `HumanMessage` multimodal (content blocks) da Fase A — nenhum caminho novo de
  visão. `ImageStore` síncrona injetada no `OnlyTalkGraph` (como `get_session_history`).
- **Enriquecimento (não efêmero):** no turno de re-visão o modelo emite
  `<<<DESC_IMAGEM>>>` **atualizado** (descrição anterior + detalhe novo, ex. nº de
  série); o graph atualiza a descrição daquele `#N` na store, respeitando o cap de
  tamanho (2–4 frases; se estourar, resume). Assim follow-ups repetidos sobre o
  mesmo detalhe voltam a ser baratos.
- **Calibração conservadora (prompt):** emitir a sentinela **só** quando a
  pergunta pedir detalhe visual concreto ausente da descrição (números, texto
  pequeno/etiquetas, cores exatas, contagens finas); exigir que a sentinela
  **nomeie o atributo** pedido; exemplos pareados "descrição basta → responde
  direto" vs "precisa rever → sentinela". Opcional: cap de re-visões por turno.
- **Prompts:** `main_graph.md` — apenas 1–2 exemplos de follow-up de foto →
  `["only_talking"]` (sem novo intent). `only_talk_graph.md` — contrato da
  sentinela `<<<REVER_IMAGEM>>>`, uso do `#N`/"última foto", descrição atualizada
  no turno de re-visão.
- **Segurança (acionar `especialista-de-seguranca`):** `image_id` sempre resolvido
  no escopo do `user.id` da requisição — nunca aceitar id arbitrário que o cliente
  ou o LLM inventem apontando para blob de outro usuário.

## Plano de testes (TDD — escrever ANTES da implementação)

Ordem RED → GREEN. Itens 1–6 = **Fase A**; itens 7–8 = **Fases B e C**.

1. **Dataclasses / retrocompatibilidade**
   - `tests/unit_tests/test_chat_view_models_images.py` (novo): default lista vazia,
     construção legada posicional válida, com imagens armazena a lista,
     `ChatResponse` inalterado.
   - `tests/unit_tests/test_graph_invoke_request_images.py` (novo): default vazio,
     construção legada `message/user` válida, com imagens armazena.

2. **`ImageValidator` isolado**
   - `tests/unit_tests/test_image_validation.py` (novo): png/jpeg válidos passam;
     base64 malformado, mime não suportado, acima do tamanho máx, string vazia,
     item inválido em lista → `ValidationError`; valor-limite exato passa;
     ausência de `.validate()` não lança (documenta o padrão); mensagem de erro
     correta por regra.

3. **Propagação em `LlmAppService.chat`**
   - `test_llm_app_service.py` (classe `TestLlmAppServiceImagePropagation`):
     encaminha imagens ao `GraphInvokeRequest`; sem imagens → lista vazia;
     preserva `message/user/memories/context_hints`; disambiguation short-circuit
     segue funcionando; imagem inválida → `ValidationError` **antes** de
     `main_graph.invoke` (asserção de que o graph não é chamado); happy path
     atravessa.

4. **Classificador ignora imagem**
   - `test_main_graph_classify_intent.py` (classe `TestClassifyIntentIgnoresImages`):
     payload do classificador não tem chave de imagem; `input` é string de texto;
     roteamento por texto inalterado; contraprova de que o action subgraph recebe
     as imagens.

5. **`OnlyTalkGraph` multimodal + descrição**
   - `test_only_talk_graph.py` (classe `TestOnlyTalkGraphMultimodalInput`):
     sem imagem → `input` string (regressão) e retorno com `image_description=None`;
     com imagem → lista de content blocks (texto + bloco[s] de imagem base64);
     histórico ainda lido e injetado; não escreve histórico. Asserções miram a
     **intenção** (existe bloco de texto + de imagem), não a chave literal frágil.
   - Classe `TestOnlyTalkGraphImageDescription`: retorno é `dict`
     `{"output", "image_description"}`; split no marcador `<<<DESC_IMAGEM>>>`
     separa resposta (antes) de descrição (depois); a descrição **não** aparece no
     `output` mostrado ao usuário; **fallback** — marcador ausente ⇒ `output` =
     conteúdo inteiro e `image_description` = `"[imagem enviada]"`; diretiva do
     marcador só injetada quando há imagem (turno texto-puro não pede marcador).

6. **Bordas e persistência da descrição**
   - imagem sem texto processada (sem `EmptyParamValidationError` quando há
     imagem — decisão de produto confirmada: mensagem vazia é válida se houver
     imagem);
   - múltiplas imagens → N blocos;
   - `MainGraph`: `image_description` transita pelo canal lateral do state e
     **não** é lido pelo `_handle_final_response` (não vaza no `output`); permanece
     `None` para intents não-visão.
   - `_persist_turn` (classe `TestPersistTurnWithImageDescription`): base64 nunca
     vaza; com descrição → `HumanMessage` = `<texto>\n[Imagem enviada pelo usuário: <descrição>]`
     (só a linha entre colchetes quando texto vazio); `AIMessage` = `output` sem a
     descrição; sem imagem → comportamento atual inalterado.

7. **Fase B — `ImageStore`**
   - `test_redis_image_store.py` (novo): `save`→`get` round-trip retorna o data URI;
     `get` de id inexistente/expirado → `None`; chave namespaced por usuário
     (`image:{user_id}:{image_id}`); `get` **não** resolve id de outro usuário
     (segurança cross-user); TTL aplicado.
   - `test_ioc_image_store.py` (novo): factory retorna `RedisImageStore` com Redis
     configurado; **sem** `CACHE_DB_CONNECTION_STRING` → store `None` (re-visão
     desligada, não in-memory).
   - Persistência do handle: `_persist_turn` grava `[Imagem #N ...]` com o `#N`;
     `save` do blob ocorre **antes** da referência; falha no `save` → degrada para
     descrição sem `#N` sem abortar o turno.

8. **Fase C — Gate de re-visão**
   - `test_only_talk_graph.py` (classe `TestOnlyTalkGraphRevision`): sentinela
     `<<<REVER_IMAGEM: #N>>>` no 1º passe dispara `image_store.get` + 2º passe com
     content block de imagem; sem base64 armazenado → sentinela ignorada (falso
     positivo inócuo, responde normal); default "mais recente" quando sem `#N`;
     `#N` explícito resolve a imagem certa; turno de re-visão emite
     `<<<DESC_IMAGEM>>>` atualizado → `update_description` na store (com cap de
     tamanho); a store síncrona é acessada via `async_runner` (não `asyncio.run`).
   - `test_main_graph_classify_intent.py`: follow-up de foto continua roteando
     `["only_talking"]` (nenhum intent novo; contrato `ast.literal_eval` intacto).

## Ordem de implementação (por fase, TDD estrito)

**Fase A:**
1. Testes + dataclasses (`ChatRequest`, `GraphInvokeRequest`).
2. Testes + `ImageValidator` + campos em `settings.py`.
3. Testes + integração do validator e propagação em `LlmAppService.chat`.
4. Testes + short-circuit e não-propagação ao classificador no `MainGraph`.
5. Testes + helper `_build_human_content`, retorno `dict` e split do marcador
   `<<<DESC_IMAGEM>>>` no `OnlyTalkGraph`; canal lateral `image_description` no
   `MainGraph`; persistência da descrição no `_persist_turn`.
6. Ajustes de prompt (`main_graph.md`, `only_talk_graph.md` com o contrato do
   marcador) + revalidar `num_ctx`.

**Fase B:**
7. Testes + `ImageStore` (ABC no domínio) + `RedisImageStore` + factory
   `get_image_store` + settings de TTL/cap; `save` + handle `#N` no `_persist_turn`.

**Fase C:**
8. Testes + gate `<<<REVER_IMAGEM>>>` no `OnlyTalkGraph` (get da store, 2º passe,
   enriquecimento) + exemplos de follow-up no `main_graph.md` + sentinela no
   `only_talk_graph.md`. Revisão de segurança (`especialista-de-seguranca`).

## Riscos e pontos de atenção

- **DoS / custo de LLM:** payload base64 gigante é vetor de abuso. Limite de
  tamanho verificado **antes** de decodificar (checar `len` da string). Acionar
  `especialista-de-seguranca` antes do deploy.
- **`num_ctx` insuficiente** trunca a imagem/instrução silenciosamente — revalidar.
- **`_handle_smart_home_security_cams`** é o único nó que reconstrói o
  `GraphInvokeRequest` (só `message`/`user`), então já dropa `images` — coerente
  (câmeras produzem imagem, não consomem), apenas registrado.
- **Descrição via marcador depende de obediência do modelo:** gemma4 pode não
  emitir `<<<DESC_IMAGEM>>>` de forma consistente. Mitigado pelo fallback (sem
  marcador ⇒ resposta inteira vira `output`, descrição vira `"[imagem enviada]"`),
  mas validar a taxa de acerto nos testes de integração.
- **Contrato do only_talk muda de `str` → `dict`:** afeta um único chamador
  (`MainGraph._handle_only_talking`) e os testes do only_talk/main graph — contido
  e testável; alinha o only_talk ao contrato `dict` dos demais graphs.
- **(Fase B) RAM do Redis:** base64 é pesado. `CHAT_IMAGE_STORE_TTL_SECONDS`
  (default **24h/86400s**) + cap de imagens por usuário contêm a RAM desde a
  Fase B. Sem Redis, re-visão fica desligada (degrada para o caminho barato).
- **(Fase C) Segurança cross-user:** `image_id` sempre resolvido no escopo do
  `user.id`; nunca aceitar id arbitrário do cliente/LLM. Revisão obrigatória do
  `especialista-de-seguranca` antes de liberar a Fase C.
- **(Fase C) Disparo espúrio da sentinela:** gate julgado pelo modelo pode rever à
  toa. Mitigado por redação conservadora, exigência de atributo nomeado, e a
  salvaguarda de que a sentinela só age se há base64 armazenado.
- **Decisões de produto a confirmar:** allowlist de mimes final, `chat_image_max_bytes`
  e `chat_image_max_count`, tamanho-alvo final da descrição (2–4 frases), e cap de
  imagens por usuário. **`CHAT_IMAGE_STORE_TTL_SECONDS` definido: 24h (86400s).**

## Fora de escopo (fases futuras)

- Imagem direcionando roteamento de ação ("adicione o que está na foto à lista").
- Disambiguation **interativa** de imagens ("qual foto, a do prato ou a do
  recibo?") — exigiria generalizar o `DisambiguationService` (hoje acoplado a
  shopping list). A Fase C resolve por "mais recente"/handle `#N`.
- Saída de imagens pelo assistente (`ChatResponse` com mídia).
