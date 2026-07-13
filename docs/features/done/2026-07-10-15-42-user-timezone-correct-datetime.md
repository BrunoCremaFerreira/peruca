# Plano: Data-hora correta com timezone por usuário

- **Status:** done
- **Criado em:** 2026-07-10 15:42
- **Implementado em:** 2026-07-13
- **PR/commit:** branch `feature/user-timezone` (sem commit — regra "Git Commits — Never Automatic")
- **Branch:** `feature/user-timezone`
- **Consultorias realizadas (obrigatórias):** `arquiteto`, `especialista-de-prompt`,
  `programador-tester` (2026-07-10, planejamento); `arquiteto`,
  `especialista-de-prompt`, `programador-tester`, `programador`,
  `especialista-de-seguranca` (2026-07-12/13, implementação)
- **Resultado:** 2165 testes unitários verdes; bateria de integração §10.7 11/11
  (100%, `AMBIGUOUS_EXCLUDED` vazio) com Ollama, Home Assistant e Music
  Assistant vivos.

---

## 0. Divergências aprovadas durante a implementação

Registradas aqui porque contradizem o texto original das seções indicadas. **O
código é a fonte da verdade**; leia esta seção antes de acreditar em qualquer
outra.

### 0.1 Limite de data futura dos validadores (revisa §8 item 8) — parecer do `arquiteto`

O plano mandava "tolerar o tz do servidor" nos validadores de data futura. Isso
está **errado**, e não só na borda: `maintenance_record_validation.py`,
`pet_health_event_validation.py` e `pet_validation.py` comparavam com
`date.today()` (data local **do servidor**). Um usuário num fuso adiantado
(servidor em UTC, usuário em `Asia/Tokyo`) teria um registro legítimo de "hoje"
**rejeitado durante 9 horas por dia** — caminho feliz, não borda de réveillon.

A causa é semântica: `performed_at`/`occurred_at`/`birth_date` são **datas
civis** (sem hora, sem fuso — §3.6 fixa que não convertem). "Está no futuro?" é
uma pergunta mal formada para uma data civil sem um fuso de referência; o único
limite superior correto e independente de fuso é **a maior data local existente
na Terra** (UTC+14) — ou seja, `UTC hoje + 1 dia`.

Implementado como `clock.max_civil_date_on_earth()`, consumido pelos três
validadores. `vehicle_validation.py` teve o `datetime.now().year` (naive, tz do
servidor) trocado por `datetime.now(timezone.utc).year` — mesmo defeito, e a
folga `+1` que já existia lá absorve a borda.

**A folga de 1 dia é deliberada e semanticamente correta. Não "conserte" isso de
volta para `date.today()`.** Dois testes de service pré-existentes que fixavam o
limite antigo (`hoje+1` rejeitado) foram rebaseados para `hoje+2`.

### 0.2 `GraphInvokeRequest.user_timezone` nasce **vazio** (revisa §3.3) — parecer do `arquiteto`

O plano propunha `user_timezone: str = "America/Sao_Paulo"`. Isso criaria **duas
fontes de verdade** para a mesma política (o literal no domain e o
`DEFAULT_TIMEZONE` da `infra/settings.py`) — e a falha seria silenciosa: um
operador muda o `.env` e qualquer caminho que esqueça de preencher o campo
continua respondendo em São Paulo, sem erro.

Implementado como `user_timezone: str = ""` (coerente com o resto da dataclass,
onde todo default é *vazio*, nunca *política*). A fonte única é
`LlmAppService.chat()`, que resolve via `UserSettingsService.get_timezone()`,
cujo fallback é o `DEFAULT_TIMEZONE` **injetado pela IoC**. Um tz vazio chegando
a um graph é bug de wiring e **falha alto** no `clock` (`ValidationError`).

### 0.3 A localização pt-BR não mora no `clock` (revisa §4 e §7) — parecer do `arquiteto`

`domain/services/clock.py` é **locale-free**: devolve `datetime` aware e formata
pelo `fmt` recebido. Os nomes de dia da semana em português vivem em
`application/appservices/datetime_presenter.py`
(`format_current_datetime(tz) -> "sexta-feira, 10/07/2026 11:32 (America/Sao_Paulo)"`),
que é apresentação, não domínio de tempo.

### 0.4 `llm_app_service` NÃO converte `occurred_at` (revisa §8 item 5)

O §8 pedia "formatação do fluxo curto-circuitado com o tz do usuário", mas
`occurred_at` é **data civil** e o §3.6 proíbe convertê-la (converter um `date`
puro mudaria o dia). O que mudou foi a **referência**: o fluxo resolve
"hoje"/"ontem" na data local do usuário, então a confirmação já imprime o dia
dele. Nenhuma conversão da data civil.

### 0.5 Achados de segurança fechados antes do merge (`especialista-de-seguranca`)

A auditoria **validou o argumento central do §3.1** (a escrita via chat é
contida: um único campo, de um conjunto fechado de ~600 IANA, na própria linha
do usuário autenticado, reversível com uma frase; nenhum caminho — direto ou
transitivo — do chat para escrita em outra entidade). Zero achados Críticos ou
Altos. Corrigidos nesta branch:

- **TZ-001/TZ-002 (Médio):** a `location` transcrita pelo LLM era ecoada na
  resposta — que é persistida no histórico **no papel `assistant`** e reinjetada
  crua pelo `OnlyTalkGraph` nos turnos seguintes — sem `sanitize_for_prompt` e
  sem cap, permitindo **forjar uma linha de turno**. Agora sanitizada no
  `classify` (cap 60), a mesma defesa que vehicle/pet já aplicam. O cap também
  mata o custo do fuzzy sobre uma `location` gigante.
- **TZ-003 (Baixo):** um `DEFAULT_TIMEZONE` com typo derrubava **todo turno de
  chat** de todo usuário sem linha em `user_settings`. Agora falha na composição
  (guard no construtor do `UserSettingsService`).
- **TZ-009 (latente):** `MainGraph._handle_smart_home_security_cams` reconstruía
  o `GraphInvokeRequest` e descartava silenciosamente `user_timezone`, `memories`
  e `context_hints`. Passa o request intacto.

**Follow-ups registrados, fora do escopo desta branch:** TZ-004 (`set_timezone` é
check-then-act; um upsert atômico `ON CONFLICT` eliminaria a corrida, hoje
contida pelo `UNIQUE`); TZ-005 (a garantia "o chat só escreve settings" é
convencional, não estrutural — o `LlmAppService` recebe o service com poder de
escrita embora só leia; um `ReadOnlyUserSettingsRepository` daria a mesma
garantia por ISP que vehicle/pet têm); e `context_summary_graph.py:59`, que ainda
usa `datetime.now()` do servidor no seu `current_datetime` (roda no background da
compaction, sem `GraphInvokeRequest`, logo sem tz para ler — não estava no §8).

---

## 1. Problema e objetivo

Hoje o Peruca **alucina** quando perguntado sobre data/hora: só o `OnlyTalkGraph`
recebe o "agora" (e no timezone **do servidor**); os demais graphs usam
`date.today()` do servidor; timestamps vindos do Home Assistant são exibidos sem
conversão. Requisitos:

1. **O horário considerado nas conversas via chat é sempre o horário local** do
   timezone escolhido pelo usuário.
2. **O timezone pode ser alterado via chat**: "Peruca, altere o timezone para
   São Paulo".
3. **Datetimes de entidades persistidas ficam sempre em UTC** no banco e são
   convertidos para o timezone escolhido **apenas na apresentação** das
   respostas.

**Regra de ouro (padrão do repo, `date_resolver`):** o LLM nunca faz aritmética
de calendário nem de fuso. Ele só transcreve o que o usuário disse ("São
Paulo") e, quando tem certeza, sugere um identificador IANA; o Python valida e
resolve tudo.

## 2. Estado atual relevante (verificado no código)

- **A escrita já é UTC** — os domain services usam `datetime.now(timezone.utc)`
  para `when_created`/`when_updated` (`shopping_list_service.py:52`,
  `vehicle_service.py:52`, `pet_service.py:84`, `maintenance_service.py:56,83`,
  `pet_health_service.py:64,91`, `user_memory_service.py:32`,
  `sqlite_shopping_list_repository.py:94,104`). O requisito 3 já vale na
  escrita; **falta a conversão na apresentação**.
- **Bug latente confirmado** — `domain/entities.py:13`:
  `when_created: datetime = datetime.now(timezone.utc)` é default de dataclass
  avaliado **uma vez no import**; toda entidade criada sem `when_created`
  explícito compartilha o timestamp do import (mitigado porque os services
  sobrescrevem no `add`, mas é bug de categoria).
- `only_talk_graph.py:167` injeta
  `datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")` — timezone **do
  servidor**, sem dia da semana, e nenhuma regra anti-alucinação no prompt.
- `vehicle_maintenance_graph.py` (linhas 106, 134, 427, 510, 535...) e
  `pet_health_graph.py` (106, 134, 450, 506, 535, 539) usam `date.today()`
  (data do servidor) para o `current_date` do prompt e para
  `resolve_date_token`/`resolve_period`/`parse_explicit_date`.
- `maintenance_flow_service.py:212` e `pet_health_flow_service.py:183` têm
  `date.today()` **embutido** — o fluxo multi-turno resolveria datas no tz do
  servidor mesmo depois da correção dos graphs (inconsistência sutil + defeito
  de testabilidade).
- `smart_home_sensors_graph.py:173` formata `last_changed.strftime("%H:%M")`
  sem conversão — **o caso mais visível do bug hoje** (timestamp do HA exibido
  em outro fuso).
- `llm_app_service.py:678` formata `occurred_at` no fluxo curto-circuitado.
- **Não existe** entidade de preferências do usuário nem qualquer noção de
  timezone configurável. `date_resolver.py` já recebe a referência `today` por
  parâmetro (desenho correto — não muda).

## 3. Decisões centrais (divergências resolvidas)

### 3.1 Persistência da preferência — nova entidade `UserSettings`

**Escolhido** (parecer do `arquiteto`): entidade `UserSettings(BaseEntity)` em
`domain/entities.py` — `id` UUID (regra do projeto), `user_id: str`,
`timezone: str` (IANA) — relação **1:1 por `user_id`** (índice único).

- SRP: `User` carrega identidade; timezone é *preferência*. Extensível
  (idioma, unidades futuras = colunas novas em `user_settings`, sem migração
  de `user`).
- A separação de entidades é o que entrega a garantia estrutural do chat: o
  caminho do chat recebe `UserSettingsRepository` completo (escrever settings
  via chat é **desejado** e de dano trivial/reversível sob prompt injection) e
  continua **sem nenhuma** referência de escrita a `UserRepository`. ISP =
  interface mínima por caminho; nenhum wrapper ReadOnly novo é necessário.
- **Sem "registro fantasma"**: ausência de linha = usa o default. O default
  vem de `DEFAULT_TIMEZONE` em `infra/settings.py` (padrão
  `America/Sao_Paulo`), lido só na composição (`ioc.py`) e injetado no
  serviço — nunca hardcoded no domain.

**Descartado:** campo `timezone` na entidade `User` (premissa inicial do
`especialista-de-prompt`, fora do escopo dele) — mistura preferência com
identidade e obrigaria o chat a ter acesso de escrita ao `UserRepository`.

### 3.2 "Agora do usuário" — módulo de funções puras, não ABC

**Escolhido** (parecer do `programador-tester`, padrão do repo): módulo
`domain/services/clock.py` de **funções puras stdlib** (`zoneinfo`), com
determinismo por **injeção de parâmetro** — o mesmo padrão do `date_resolver`
(sem freezegun, sem patch de `datetime`):

```python
now_for_timezone(tz: str, *, now_utc: datetime | None = None) -> datetime  # aware
to_local(dt_utc: datetime, tz: str) -> datetime   # naive do SQLite => assume UTC
format_local(dt_utc: datetime, tz: str, fmt: str) -> str
```

- Timezone inválido → `ValidationError` do domínio (nunca vazar
  `ZoneInfoNotFoundError`); `now_utc` naive → rejeitado (fail-fast).
- `zoneinfo.available_timezones()` é caro (lê disco) — **cachear o set** em
  atributo de módulo.

**Descartado:** ABC `Clock` em `domain/interfaces/` + `SystemClock` em infra
(proposta alternativa do `arquiteto`) — a motivação era testabilidade, que a
injeção de `now_utc` resolve no estilo já consagrado do repo; o próprio
arquiteto admitiu a variante domain por ser stdlib pura (precedente
`date_resolver`). Menos cerimônia: sem factory na IoC, sem mock de interface.

### 3.3 Timezone chega aos graphs por campo tipado, não por `context_hints`

`GraphInvokeRequest.user_timezone: str = "America/Sao_Paulo"` — campo novo
tipado (a dataclass já tem defaults; não quebra construções existentes).
`context_hints` é para dicas opcionais não-estruturais (`music_is_playing`,
persona); timezone é dado obrigatório que todos os graphs de data consomem.
**`LlmAppService.chat()` resolve o timezone uma única vez por request** (via
`UserSettingsService`) e o injeta no request — ponto único de verdade; graphs
nunca consultam o repositório de settings.

### 3.4 Alteração via chat — mini-graph `UserSettingsGraph` (nova intent)

**Escolhido**: intent `user_settings` no MainGraph → `UserSettingsGraph` no
padrão dos demais sub-graphs (1 chamada LLM no classify; nodes de ação 100%
determinísticos). **Descartado:** curto-circuito determinístico no
`LlmAppService` (padrão DisambiguationService/FlowService) — esse padrão serve
para *continuações de fluxo pendente*, não para detecção de intenção inicial;
detectar "altere o timezone" por regex/keywords é frágil e foge do padrão "LLM
classifica, Python resolve". **Descartado:** embutir num graph existente —
nenhum tem afinidade semântica e `only_talk` é chain sem ações por design.

### 3.5 Cidade→IANA — híbrido, com o Python como autoridade

O classify emite **os dois campos**: `timezone_iana` (sugestão do modelo — o
gemma4:12b conhece os IANA comuns mas inventa formas plausíveis para os
incomuns: "America/Lisboa") e `location` (transcrição fiel do que foi dito).
Pipeline em Python, no node de ação:

1. `timezone_iana` ∈ `zoneinfo.available_timezones()` → usa.
2. Senão, normaliza `location` (caixa/acentos) e busca em **dicionário curado
   pt-BR** (`brasília`/`horário de brasília` → `America/Sao_Paulo`, `lisboa` →
   `Europe/Lisbon`, `nova york`/`nova iorque` → `America/New_York`, `manaus`,
   `fernando de noronha`, `londres`, `tóquio`...), com fuzzy via
   `text_matching.find_by_term` (já existe no repo).
3. Nada → resposta determinística amigável (sem LLM): "Não reconheci esse
   fuso. Me diga uma cidade grande de referência — por exemplo: São Paulo,
   Lisboa, Nova York ou Londres." (ancorar com exemplos > pedir IANA).

Um IANA emitido pelo LLM **nunca** é persistido sem validação — mesma filosofia
do `date_resolver`.

### 3.6 Conversão UTC→local só na apresentação; REST permanece UTC

- **Chat**: todos os `strftime` de graphs/appservice passam por
  `format_local`/`to_local` com `request.user_timezone`.
- **REST/ViewModels**: **permanecem UTC ISO-8601 com offset** (padrão de API —
  o cliente formata). Decisão registrada; se um dia o REST precisar de local,
  fazer no `auto_map`/app service. Um teste congela o contrato
  (`endswith("+00:00")`).
- Datetimes lidos do SQLite podem vir **naive** — `to_local` assume UTC quando
  `tzinfo is None`.
- **Datas civis não convertem**: `performed_at`/`occurred_at`/`birth_date` são
  `date` de evento (sem hora) — armazenar a data local resolvida como está;
  converter date puro para UTC mudaria o dia. O requisito 3 (UTC no banco)
  aplica-se a *datetimes* (`when_created`/`when_updated`), não a datas civis.
  O que muda para as datas civis é a **referência** ("hoje" no tz do usuário).

### 3.7 Bug do `BaseEntity.when_created` — corrigir nesta feature

Trocar para `field(default_factory=lambda: datetime.now(timezone.utc))`. A
feature é literalmente "datas corretas"; manter timestamps congelados do import
é incoerente. Raio de impacto pequeno (services sobrescrevem no `add`; testes
existentes passam o campo explicitamente), sem risco a dados persistidos.
Verificar na implementação: testes que comparem dataclasses inteiras (dois
`_sample()` sem `when_created` deixarão de ser iguais) e qualquer uso do valor
de import como sentinela (grep antes).

## 4. Arquitetura — componentes

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| `UserSettings` | `src/domain/entities.py` | Entidade nova (`BaseEntity`): `user_id`, `timezone` IANA. 1:1 por usuário. |
| `UserSettingsRepository` | `src/domain/interfaces/user_settings_repository.py` | ABC: `get_by_user_id`, `add`, `update`. |
| `SqliteUserSettingsRepository` | `src/infra/data/sqlite/sqlite_user_settings_repository.py` | Tabela `user_settings` com índice único em `user_id`; id UUID. |
| `UserSettingsService` | `src/domain/services/user_settings_service.py` | `get_timezone(user_id) -> str` (fallback no default injetado; sem registro fantasma) e `set_timezone(user_id, tz)` (valida IANA; cria com UUID ou atualiza o existente — nunca duplica). |
| `UserSettingsValidator` | `src/domain/validations/` | Padrão fluente do repo (**`.validate()` final obrigatório**); tz ∈ `available_timezones()` (set cacheado). |
| Clock | `src/domain/services/clock.py` | Funções puras §3.2 (stdlib `zoneinfo`; sem factory na IoC — graphs importam direto, determinismo via `now_utc`). |
| Resolver cidade→IANA | `src/domain/services/timezone_resolver.py` | Dicionário curado + normalização + fuzzy (`text_matching`) + passthrough IANA validado (§3.5). Funções puras. |
| `UserSettingsGraph` | `src/application/graphs/user_settings_graph.py` | Herda de `Graph`. Nodes: `classify` (única chamada LLM) → `set_timezone` / `get_timezone` / `not_recognized`. Nodes de ação determinísticos, sem LLM. |
| Prompt | `src/infra/prompts/user_settings_graph.md` | Rascunho em §6. |
| Formatação | `application/appservices/datetime_presenter.py` *ou* reuso direto de `clock.format_local` | Ponto único dos `strftime` de apresentação (§3.6). |

Sem FlowService no v1 (cidade não resolvida → responde e encerra o turno; o
custo de repetir a frase é baixo). Sem marcador de merge novo: a resposta do
`set_timezone` é texto curto sem números "recalculáveis" — se a integração
mostrar o merge corrompendo a resposta, promover um `USER_SETTINGS_HEADER` no
padrão do §7 do plano da calculadora.

## 5. Intent no MainGraph

- Nome: **`"user_settings"`** (nome do node; padrão substantivo de domínio).
  Wired incondicionalmente (sem dependência externa).
- `main_graph.py`: campo `output_user_settings` no `MainGraphState`; parâmetro
  no construtor; node `"user_settings"`; handler `_handle_user_settings` com
  fallback `not_recognized` → `only_talk` (copiar `_handle_pet_health`);
  incluir no merge do `_handle_final_response`.
- Regra no `infra/prompts/main_graph.md` (parecer do `especialista-de-prompt`):

  > **`user_settings`** → quando o usuário quer ALTERAR ou CONSULTAR uma
  > configuração do assistente, como o fuso horário/timezone usado nas
  > respostas.
  >
  > Desambiguação: só é `user_settings` quando há pedido de ALTERAR/CONSULTAR
  > a configuração. — "Altere o timezone para São Paulo", "muda o fuso para
  > Lisboa", "qual fuso horário está configurado?" → `["user_settings"]`.
  > — Perguntar data/hora ("que horas são?", "que dia é hoje?") NÃO é
  > configuração — é conversa → `["only_talking"]`. — Alarmes, timers e
  > lembretes ("põe um alarme pra 7h") NÃO são configuração nem casa
  > inteligente → `["only_talking"]`. — Comentários sobre fusos ("o fuso do
  > Japão é maluco", "odeio horário de verão") → `["only_talking"]`.
  > — Menção a cidade sem comando ("vou viajar para Lisboa semana que vem") →
  > `["only_talking"]`.

- Adicionar `["user_settings"]` aos exemplos de formato de saída do prompt.

## 6. Prompt `user_settings_graph.md` (rascunho aprovado)

Molde do `vehicle_maintenance_graph.md`: `/no_think` + papel + "APENAS um
objeto JSON"; JSON raso com **todos os campos sempre presentes**; aspas retas;
temperatura **0.1**; parser `json.loads` via `Graph._extract_structured_output`.

```json
{"intents": ["set_timezone"], "location": "São Paulo", "timezone_iana": "America/Sao_Paulo"}
{"intents": ["get_timezone"], "location": "", "timezone_iana": ""}
{"intents": ["not_recognized"], "location": "", "timezone_iana": ""}
```

**Regra-chave anti-alucinação de IANA** (a saída honesta): *"Se você não tiver
CERTEZA do identificador IANA, deixe `timezone_iana` vazio e preencha apenas
`location` — o sistema resolve."*

**Few-shots (~8):**

1. "Altere o timezone para São Paulo" → `set_timezone`, `"São Paulo"`,
   `"America/Sao_Paulo"`
2. "Muda o fuso horário para Lisboa" → `set_timezone`, `"Lisboa"`,
   `"Europe/Lisbon"`
3. "Usa o horário de Brasília" → `set_timezone`, `"Brasília"`,
   `"America/Sao_Paulo"`
4. "Coloca no fuso de Nova York" → `set_timezone`, `"Nova York"`,
   `"America/New_York"`
5. **"Peruca, configura o fuso de Rondonópolis"** → `set_timezone`,
   `"Rondonópolis"`, `""` — **o few-shot mais importante**: ensina "sem
   certeza → IANA vazio, Python resolve"; sem ele o modelo chuta.
6. "Qual timezone está configurado?" → `get_timezone`
7. "Que horas são?" → `not_recognized` (defesa em profundidade; o MainGraph já
   deveria ter roteado para `only_talking`)
8. "O fuso horário do Japão é maluco" → `not_recognized`

Templates dos nodes de ação (determinísticos): sucesso — "Pronto! Agora uso o
fuso de America/Sao_Paulo (São Paulo)."; `get` — "Estou usando o fuso
America/Sao_Paulo."; não resolvido — template do §3.5 item 3.

## 7. Injeção do "agora" e regra anti-alucinação nos prompts

| Prompt | Mudança |
|---|---|
| `only_talk_graph.md` | `current_datetime` passa a `now_for_timezone(request.user_timezone)` formatado **com dia da semana por extenso**: `quinta-feira, 10/07/2026 14:32 (America/Sao_Paulo)` — modelos erram sistematicamente dia-da-semana←data; fornecer pronto elimina a classe de alucinação. |
| `only_talk_graph.md` (regra nova) | "Quando perguntarem a data, a hora ou o dia da semana, responda usando EXATAMENTE o valor de 'Data e hora atual' acima. Nunca estime, calcule ou invente outro horário, **mesmo para outros fusos**." (cobre "que horas são em Tóquio?" — melhor admitir que só conhece o horário local do que errar aritmética de fuso). |
| `vehicle_maintenance_graph.md` / `pet_health_graph.md` | `current_date` mantém formato `YYYY-MM-DD`, mas passa a ser a **data local do usuário** (`now_for_timezone(tz).date().isoformat()`). |
| `main_graph.md` / `main_graph_final_response.md` | **Não recebem** data/hora — não muda classificação nem merge; só adiciona tokens e ruído. |

## 8. Pontos de substituição (checklist de `datetime.now()`/`date.today()`/`strftime`)

1. `only_talk_graph.py:167` — `now_for_timezone(request.user_timezone)` + dia
   da semana (§7).
2. `vehicle_maintenance_graph.py` — `current_date` (106, 427) e referência do
   `resolve_date_token`/`resolve_period`/`parse_explicit_date` (134, 510, 535,
   537...); `strftime` de `performed_at` (225, 407, 416) **não converte** (data
   civil, §3.6) — só a referência muda.
3. `pet_health_graph.py` — idem (106, 134, 415, 432, 440, 450, 506, 511, 528,
   535, 539) para `occurred_at`.
4. `maintenance_flow_service.py:212` e `pet_health_flow_service.py:183` —
   `date.today()` embutido passa a **referência recebida por parâmetro** (o
   chamador passa a data local do usuário); corrige também o defeito de
   testabilidade.
5. `llm_app_service.py:678` — formatação do fluxo curto-circuitado com o tz do
   usuário.
6. `smart_home_sensors_graph.py:173` — `last_changed` convertido com
   `to_local` antes do `strftime("%H:%M")` (**o bug mais visível hoje**).
7. `domain/entities.py:13` — `field(default_factory=...)` (§3.7).
8. `vehicle_validation.py:64` (`datetime.now().year`) — inspecionar na
   implementação; validação de ano-limite tolera o tz do servidor (borda de
   réveillon é aceitável), documentar se ficar como está.

## 9. Wiring — checklist

1. `infra/settings.py`: `DEFAULT_TIMEZONE` (default `America/Sao_Paulo`),
   `llm_user_settings_graph_chat_model` (default `gemma4:12b`),
   `llm_user_settings_graph_chat_temperature: float = 0.1`,
   `llm_user_settings_graph_chat_reasoning: bool | None = None`.
2. `infra/ioc.py`: `get_user_settings_repository()`,
   `get_user_settings_service()` (recebe o default de timezone),
   `get_user_settings_graph()` com cache em
   `_repo_cache[("graph", "user_settings")]`.
3. `LlmAppService.chat()`: resolve `user_timezone` uma vez (via
   `UserSettingsService`) → `GraphInvokeRequest.user_timezone` (§3.3).
4. Criação da tabela `user_settings` no mesmo ponto onde as demais tabelas
   SQLite nascem (seguir o padrão do repo).
5. `main_graph.py` + `infra/prompts/main_graph.md` (§5); prompts do §7.
6. `.env.example` + lista de env vars do `CLAUDE.md`.

Fora do wiring do chat: **nenhuma rota REST nova é necessária** no v1 (a
alteração é via chat; requisito). Se depois for desejado um
`/user-settings` REST, segue o padrão `VehicleAppService`.

## 10. Estratégia TDD (parecer do `programador-tester`)

Determinismo por **injeção de `now_utc`/referência** (padrão `date_resolver`) —
sem freezegun, sem patch de `datetime`. Ordem de nascimento — cada arquivo
vermelho antes da implementação:

### 10.1 `tests/unit_tests/test_base_entity.py` (primeiro; fix §3.7)

- `TestBaseEntityWhenCreated`:
  `test_two_instances__have_distinct_when_created` (assert robusto sem sleep:
  `t0 <= e.when_created <= t1` com capturas antes/depois — **falha no código
  atual**, timestamp de import << t0);
  `test_default__is_timezone_aware_utc`;
  `test_explicit_value__not_overridden`.

### 10.2 `tests/unit_tests/test_clock.py` (domínio puro)

- `TestNowForTimezone`: `test_valid_iana__returns_aware_datetime`;
  `test_sao_paulo__offset_minus_three` (`now_utc=2026-07-10T12:00Z` → 09:00);
  `test_lisbon_summer__offset_plus_one` (WEST/DST ativo) **e**
  `test_lisbon_winter__offset_zero` (WET) — par DST obrigatório;
  `test_invalid_tz__raises_validation_error` ("America/Sao_Paolo" —
  `ValidationError`, nunca `ZoneInfoNotFoundError` vazando);
  `test_empty_tz__raises_validation_error`;
  `test_naive_now_utc__raises_validation_error` (contrato fail-fast).
- `TestToLocal`: `test_utc_datetime__converted_to_sao_paulo`
  (**2026-07-10T01:00Z → 2026-07-09T22:00-03:00** — a data muda de dia);
  `test_naive_input__assumed_utc` (SQLite devolve naive);
  `test_conversion_preserves_instant`.
- `TestLocalDateForUser` (a ponte com o `date_resolver` — o coração do bug):
  `test_midnight_edge__local_date_is_previous_day`
  (`now_utc=2026-07-10T02:30Z`, SP → `date(2026,7,9)`);
  `test_today_token_with_local_reference` (`resolve_date_token("today",
  local_date)` → 2026-07-09, não o "hoje" do servidor UTC);
  cobertura da virada em `resolve_period("this_week", ...)`.

### 10.3 `tests/unit_tests/test_timezone_resolver.py` (puro, determinístico)

- `TestResolveCityToIana`: `test_sao_paulo__returns_america_sao_paulo`;
  `test_brasilia__returns_america_sao_paulo` (alias curado);
  `test_accents_and_case_insensitive`; `test_lisboa__returns_europe_lisbon`;
  `test_fuzzy_typo__sao_paolo__resolves` (`text_matching.find_by_term`);
  `test_unknown_city__returns_none` (nunca chute);
  `test_iana_passthrough__valid_identifier_accepted` ("America/Bahia");
  `test_iana_passthrough__invalid_identifier__none` (LLM alucinou
  "America/Sao_Paolo" → None — **Python é a autoridade, não o LLM**).

### 10.4 `tests/unit_tests/test_user_settings_service.py` + `test_sqlite_user_settings_repository.py`

- Service (repo `MagicMock`, padrão `test_user_service.py`):
  `test_get__no_settings__returns_default_timezone` (default injetado, sem
  registro fantasma); `test_set__new_user__creates_with_uuid`
  (`uuid.UUID(entity.id)` não levanta); `test_set__existing__updates_not_duplicates`
  (`repo.update` chamado, `repo.add` NÃO); `test_set__invalid_tz__raises_validation_error`
  (+ `repo.add/update.assert_not_called()`);
  `test_set__city_name_rejected` ("Lisboa" ≠ IANA — o service só aceita IANA
  já resolvido).
- Repositório (fixture `sqlite_db_path` real, padrão vehicle):
  `test_add_then_get_by_user_id__round_trip`;
  `test_get_by_user_id__unknown_user__returns_none`;
  `test_update__persists_new_timezone` (e continua 1 registro);
  `test_isolation__user_a_never_sees_user_b`.

### 10.5 `tests/unit_tests/test_user_settings_graph_classify_intent.py` + handlers

Padrão `test_pet_health_graph_classify_intent.py` (patch de `load_prompt` e
`_extract_structured_output`, `llm_chat=MagicMock()`):

- `TestClassify`: `test_set_timezone_with_city__resolves_iana_in_state`;
  `test_unknown_city__state_has_no_resolution` (intent preservado, handler
  responde amigável); `test_malformed_json__falls_back_to_not_recognized`;
  `test_get_timezone_intent__classified`;
  `test_hallucinated_iana__discarded_falls_back_to_location` (IANA inválido no
  JSON + location válida → resolve pela location).
- `TestSetTimezoneNode`: `test_set__persists_resolved_iana`
  (`service.set_timezone.assert_called_once_with(user.id,
  "America/Sao_Paulo")`); `test_set__llm_not_called_in_action_node`
  (`llm_chat.invoke.assert_not_called()`);
  `test_unknown_city__friendly_message_no_persistence`
  (`service.set_timezone.assert_not_called()`).
- `TestGetTimezoneNode`: `test_get__returns_configured_tz_no_llm`.

### 10.6 Regressão nos graphs existentes (encanamento, não a conversão em si)

- `test_only_talk_graph_*`: `current_datetime` do prompt vem de
  `now_for_timezone(request.user_timezone)` (assert do fragmento com o offset
  esperado e dia da semana).
- `test_pet_health_graph_*` / `test_vehicle_maintenance_graph_*`: a referência
  passada a `resolve_date_token`/`current_date` é a **data local** do
  `user_timezone` do request (caso de borda 02:30Z/SP);
  `test_query_output__utc_record_crossing_midnight__shows_local_previous_day`
  para `when_created` (mock do repo com `datetime(2026,7,10,1,0,tzinfo=utc)` →
  output contém "09/07") — apenas onde datetime (não data civil) é exibido.
- `test_smart_home_sensors_graph_*`: `last_changed` UTC exibido no tz do
  usuário.
- Flow services: referência por parâmetro (não mais `date.today()` interno).
- `test_main_graph_user_settings.py`: intent `["user_settings"]` roteia;
  fallback `not_recognized` → `only_talk`.
- ViewModels/appservices: teste que **congela o contrato REST em UTC ISO-8601**
  (`endswith("+00:00")` ou equivalente).

### 10.7 `tests/integration_tests/test_llm_app_service_chat__user_settings_graph.py` (por último, Ollama vivo, skip gracioso)

- **B1 (~7 frases):** "Peruca, altere o meu timezone para São Paulo."; "Muda o
  fuso horário para Lisboa."; "Configura meu fuso para o horário de
  Brasília."; "Qual é o fuso horário configurado?"; "Meu fuso está errado,
  troca para São Paulo."; "Define o horário de Portugal para mim."; "Que horas
  são?" (após set para tz ≠ do servidor).
  - Asserts dos sets: **estado persistido**
    (`user_settings_service.get_timezone(user.id) == "America/Sao_Paulo"`) —
    mais robusto que parsear a resposta.
  - Assert de "que horas são?" **sem flakiness de minuto**: capturar
    `before`/`after` com `now_for_timezone(tz)` em volta do chat, extrair
    `\b(\d{1,2})[:h](\d{2})\b` do output e assertar hora ∈
    `{before.hour, after.hour}` — suficiente: o objetivo é provar o **tz**
    (diferença de 3h entre servidor UTC e SP), não o minuto. Escolher tz de
    teste com offset distinto do servidor para o teste ter poder
    discriminante.
- **B2 anti-falso-positivo (~4):** "Que horas são?" (sem set prévio — responde
  a hora, intent NÃO é `user_settings`); "Põe uma música da década de 80."
  (→ `music`); "Qual a temperatura lá fora?" (→ `smart_home_sensors`);
  **"Vou viajar para Lisboa semana que vem."** (menção a cidade sem comando →
  `only_talking` — o guard mais crítico). Assert B2: intents não contêm
  `user_settings` **e** settings do usuário inalterados.
- Aceite no padrão do repo: 100% por bateria, até 2 frases flaky movidas para
  `AMBIGUOUS_EXCLUDED` documentada.

## 11. Fora de escopo v1 (extensões futuras / descartes)

- **"Que horas são em Tóquio?"** (conversão para fuso arbitrário na conversa) —
  a regra anti-alucinação manda o modelo se ater ao horário local injetado;
  suportar consulta multi-fuso exigiria outra intent e formatação dedicada.
- **Multi-turn para cidade não reconhecida** (PendingFlow "de qual cidade você
  fala?") — v1 responde com exemplos e encerra o turno.
- **Alarmes/timers/lembretes** — não é configuração; fica em `only_talking`.
- **Outras preferências (idioma, unidades)** — a entidade `UserSettings`
  nasce pronta para recebê-las como colunas novas; nada implementado agora.
- **REST de user-settings** — sem rota no v1; alteração é via chat por
  requisito. Padrão `VehicleAppService` quando/se necessário.
- **Conversão de datas civis** (`performed_at`/`occurred_at`/`birth_date`) —
  não se aplica (§3.6); registrado para ninguém "corrigir" errado depois.
- **Detecção automática de timezone** (IP/dispositivo) — fora; a escolha é
  explícita do usuário.

## 12. Sequência de implementação

1. Fix `BaseEntity.when_created` (§10.1 vermelho → §3.7) e rodar a suíte
   completa (checar comparações de dataclass inteira).
2. `test_clock.py` (§10.2, vermelho) → `domain/services/clock.py`.
3. `test_timezone_resolver.py` (§10.3, vermelho) →
   `domain/services/timezone_resolver.py` (dicionário curado + fuzzy +
   passthrough validado).
4. `test_user_settings_service.py` + repositório SQLite (§10.4, vermelhos) →
   entidade `UserSettings`, ABC, `SqliteUserSettingsRepository`,
   `UserSettingsService` + validator (com `.validate()` final).
5. Testes do graph (§10.5, vermelhos) → `UserSettingsGraph` +
   `user_settings_graph.md`.
6. Regressões de encanamento (§10.6, vermelhas) → `GraphInvokeRequest.user_timezone`,
   resolução única no `LlmAppService.chat()`, substituições do §8, prompts do
   §7, wiring do §9.
7. `.env.example` + `CLAUDE.md`.
8. Bateria de integração (§10.7) com Ollama vivo; ajuste fino de prompt.
9. Mover este plano para `doing/` ao iniciar e `done/` ao concluir, preenchendo
   o cabeçalho.
