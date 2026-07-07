# Ambiente de desenvolvimento local (docker compose) para testes de integração

**Status:** done (ambiente montado e verificado end-to-end: 379/382 testes passam)
**Criado em:** 2026-07-07 02:35
**Implementado em:** 2026-07-07 (verificado com a suíte de integração real)
**PR/commit:** — (não comitado; aguardando decisão do usuário)

## Resultado da verificação (2026-07-07)

Subida real dos 3 containers + bootstrap + suíte completa contra o Ollama remoto
(`unix.rtx-server`):

- **379 passed, 3 failed** em 45m39s (382 testes de integração, `-m integration`).
  Nenhum skip de HA/MA/Redis — os três backends foram exercitados de verdade.
- HA populado pelo `bootstrap_ha.py`: áreas `Sala`/`Quarto`/`Cozinha`; entidades
  `light.sala/quarto/cozinha` (controláveis — `turn_on` confirmado), `sensor.
  temperatura_sala`, `sensor.umidade_quarto`, `climate.clima_sala`,
  `camera.camera_sala` (snapshot via `camera_proxy` retorna a imagem) — todas com
  área, aliases (lidos via `config/entity_registry/get`) e exposição ao Assist.
- **Os 3 falhados são classificação de intenção do LLM (gemma4:12b), não de infra:**
  - `shopping_list ... clear[Remove todos os itens ...]` → **flake** (passou no re-run).
  - `main_graph::test_chat_smart_home_security_cams_only` e
    `..._security_cams_and_smart_home_lights` → **falham de forma consistente**: o
    classificador do MainGraph não roteia essas frases de câmera para o intent de
    câmeras. Ocorre ANTES de qualquer sub-graph, logo independe deste ambiente.
    Item para o `especialista-de-prompt` (fora do escopo desta feature de infra).

### Correções aplicadas durante a verificação (vs. plano original)

- Luzes migradas do formato legado `light: platform: template` para a integração
  moderna `template:` (HA removeu o suporte ao formato antigo).
- Câmera: HA removeu o setup de câmera por plataforma YAML. Passou a ser criada via
  **config-entry flow** (`local_file`) no `bootstrap_ha.py`, com
  `allowlist_external_dirs: [/config]` na `configuration.yaml` e uma imagem
  `test_camera.png` versionada.
- Exposição ao Assist é feita só pelo update `options_domain=conversation`
  (`should_expose`), preservando os aliases; o comando `homeassistant/expose_entity`
  foi evitado.

## Objetivo

Subir, via **docker compose local**, os backends necessários para rodar **todos os
testes de integração** do Peruca sem depender de infraestrutura externa (HA em
`unix.kubernetes`, MA em `unix.rtx-server`). Três containers: **redis**,
**home assistant**, **music assistant**. O **Ollama continua no host remoto
`unix.rtx-server:11434`** (já configurado no `conftest.py`), **não** é containerizado.

O Home Assistant deve subir com **dispositivos helper reais** (nomeados, em áreas,
expostos ao Assist, com aliases) para exercitar de verdade os grafos de smart-home.

## Contexto / achados de código (fonte da verdade)

- `src/tests/integration_tests/conftest.py` tem um dict `INTEGRATION_ENV`
  **hardcoded**: `HOME_ASSISTANT_URL=http://unix.kubernetes:8123`,
  `MUSIC_ASSISTANT_URL=http://unix.rtx-server:8095`, e **não** possui a chave
  `HOME_ASSISTANT_TOKEN`. O Redis já é overridável via `TEST_REDIS_URL`
  (default `redis://localhost:6379/15`, DB index 15).
- Fixtures `home_assistant_available` / `music_assistant_available` fazem um probe
  HTTP e **`pytest.skip`** quando o backend não responde. Logo, para os testes de
  smart-home e música **rodarem** (não skiparem), HA e MA precisam estar acessíveis
  em `localhost`.
- **Armadilha crítica:** `_probe_http` considera "up" qualquer resposta HTTP,
  **inclusive 401**. Sem `HOME_ASSISTANT_TOKEN` os testes *rodam*, mas as chamadas
  reais ao HA voltam 401, os grafos degradam graciosamente e teríamos a falsa
  sensação de "HA de verdade" sem nunca tocar as entidades. **Adicionar a chave
  `HOME_ASSISTANT_TOKEN` é requisito, não opcional.**
- Os repos HA filtram por domínios reais: `light.`, `climate.`, `sensor.`,
  `camera.`. O `HomeAssistantSmartHomeConfigurationRepository` (WebSocket) descobre
  entidades via `config/entity_registry/list` filtrando
  `options.conversation.should_expose == True`, lê áreas via
  `config/area_registry/list`, e aliases por entidade. Ou seja: entidades precisam
  estar **expostas ao Assist**, atribuídas a **áreas** (os prompts citam
  `sala`/`quarto`/`cozinha`) e com **aliases** — metadados que vivem no `.storage/`
  do HA, **não** em `configuration.yaml`.
- MA **não precisa de token** (`MUSIC_ASSISTANT_TOKEN` já vazio no `INTEGRATION_ENV`;
  os testes de música validam roteamento + degradação graciosa). Basta o server
  standalone acessível na 8095.
- Escopo: **infra de teste + `conftest.py`**. Não cruza fronteiras de camada;
  `domain/`, `application/` e `infra/` de produção ficam intactos. Validado pelo
  agente `arquiteto`.

## Layout de arquivos

Projeto compose **separado** (nunca é auto-carregado, sem risco de colidir com o
`docker-compose.yml`/`docker-compose.override.yml` da app):

```
docker/
└── test-backends/
    ├── docker-compose.dev.yml          # name: peruca-test-backends; redis + HA + MA
    ├── .env.test.example               # commitado (template, SEM segredos)
    ├── bootstrap_ha.py                 # script idempotente de onboarding/seed/token
    ├── run-integration-tests.sh        # wrapper: up → bootstrap → export → pytest
    └── home-assistant/
        └── config/
            ├── configuration.yaml
            └── packages/
                └── test_entities.yaml  # entidades declarativas (helpers/template)
```

- `name: peruca-test-backends` no topo do compose isola rede/volumes (um
  `compose down` da app não derruba os backends de teste e vice-versa).
- **Publicar portas em localhost** (`8123`, `8095`, `6379`); **não** usar
  `network_mode: host` (as entidades são helpers/template/demo, sem discovery de
  rede real). Assim os defaults localhost do `conftest.py` funcionam sem config
  extra.
- **Não tocar** em `docker-compose.yml` nem `docker-compose.override.yml` (são o
  ciclo de vida da app).

## `.gitignore` (segredos e artefatos do HA fora do git)

```
docker/test-backends/.env.test
docker/test-backends/home-assistant/config/.storage/
docker/test-backends/home-assistant/config/*.log
docker/test-backends/home-assistant/config/*.db
```

## Containers (docker-compose.dev.yml)

| Serviço | Imagem | Porta | Observações |
|---|---|---|---|
| `redis` | `redis:7-alpine` | `6379:6379` | Tests usam DB index 15; nenhum seed. |
| `home-assistant` | `ghcr.io/home-assistant/home-assistant:stable` | `8123:8123` | Volume: `./home-assistant/config:/config`. `.storage/` git-ignored. |
| `music-assistant` | `ghcr.io/music-assistant/server:latest` | `8095:8095` | Sem seeding, sem token. Volume nomeado para dados. |

Todos com healthcheck e `restart: unless-stopped` (opcional para dev).

## Entidades helper no Home Assistant

Estratégia validada pelo `arquiteto`: **entidades nascem declarativas em YAML**
(`packages/test_entities.yaml`), o **script só cuida do registry metadata**
(áreas, aliases, exposição) **e do token** — mantendo o máximo fora do `.storage/`.

Por domínio (nomes determinísticos que aparecem nos prompts):

- **`light.`** — template lights `light.sala`, `light.quarto`, `light.cozinha`,
  apoiadas em `input_boolean` (turn_on/off alternam o helper). Satisfaz o filtro
  `light.` dos repos e é controlável/reproduzível.
- **`sensor.`** — `template` sensors (ex.: `sensor.temperatura_sala`,
  `sensor.umidade_quarto`). Domínio `sensor.` direto.
- **`climate.`** — `generic_thermostat` (ex.: `climate.sala`) apoiado num
  input_boolean "heater" + sensor de temperatura template.
- **`camera.`** — integração **`demo`** (`camera.demo_camera`) para evitar servir
  um still/stream real que o `generic` exigiria.

`configuration.yaml`: habilita `default_config`, `template`, `demo` (câmera) e
`homeassistant.packages` apontando para `packages/`.

## Seeding reprodutível do HA — `bootstrap_ha.py` (idempotente)

**Nunca commitar `.storage/`** (contém o segredo de assinatura do JWT + o
long-lived token → vazamento de segredo, reprovado em segurança). O script é a
fonte de verdade declarativa; o token vai para `.env.test` (git-ignored).

Sequência (é um fluxo OAuth real, não um único POST):

1. `POST /api/onboarding/users` → cria owner → retorna `auth_code`.
   (403/409 = já onboarded → no-op.)
2. Troca `auth_code` por `access_token` no endpoint de token OAuth.
3. Completa onboarding restante: `/api/onboarding/core_config`,
   `/api/onboarding/integration`. (Idempotente / tolera "já feito".)
4. WebSocket autenticado com `access_token` → `auth/long_lived_access_token`
   gera o token durável. **Só roda se `.env.test` ainda não tiver token**; senão
   reusa.
5. WS admin (upsert — checar existência antes de criar):
   - `config/area_registry/create` para `sala`, `quarto`, `cozinha`.
   - por entidade: `config/entity_registry/update` setando `area_id` e `aliases`;
     exposição ao Assist via `homeassistant/expose_entity` (ou
     `options.conversation.should_expose = true`).
6. Grava `HOME_ASSISTANT_TOKEN=<token>` em `docker/test-backends/.env.test`.

Idempotência é requisito de "reprodutível": rodar o script duas vezes não pode
falhar nem duplicar áreas/aliases.

## Mudança em `conftest.py` (única mudança de "código")

Espelhar o precedente já existente do `TEST_REDIS_URL`: tornar overridáveis por
env com defaults localhost, e **adicionar a chave nova `HOME_ASSISTANT_TOKEN`**.

```python
"HOME_ASSISTANT_URL": os.environ.get("HOME_ASSISTANT_URL", "http://localhost:8123"),
"HOME_ASSISTANT_TOKEN": os.environ.get("HOME_ASSISTANT_TOKEN", ""),
"MUSIC_ASSISTANT_URL": os.environ.get("MUSIC_ASSISTANT_URL", "http://localhost:8095"),
```

As fixtures que hoje leem `INTEGRATION_ENV["..."]` continuam iguais (o dict agora
resolve do env). `TEST_REDIS_URL` já usa localhost por default — nenhum ajuste.

**TDD:** não exige teste unitário. `conftest.py` **é** infra de teste; não há regra
de negócio nem ramo de produção; testar `os.environ.get` não teria valor. O
precedente `TEST_REDIS_URL` foi adicionado exatamente assim. A "verificação"
equivalente é a suíte de integração rodando verde contra os novos backends.
(Confirmado pelo `arquiteto`.)

## Wrapper de execução — `run-integration-tests.sh`

Passo único para o desenvolvedor (o pytest lê `os.environ`, não o `.env` da app):

1. `docker compose -f docker/test-backends/docker-compose.dev.yml up -d`
2. aguardar healthchecks (HA/MA sobem em ~30–60s)
3. `python docker/test-backends/bootstrap_ha.py` → gera/atualiza `.env.test`
4. `set -a; source docker/test-backends/.env.test; set +a`
5. `cd src && python -m pytest tests/integration_tests/ -v`

## Passos de implementação

1. Criar `docker/test-backends/docker-compose.dev.yml` (redis + HA + MA,
   `name:` próprio, portas em localhost, healthchecks, volume `./home-assistant/config`).
2. Criar `home-assistant/config/configuration.yaml` +
   `packages/test_entities.yaml` (lights template, sensores template, climate
   generic_thermostat, câmera demo).
3. Escrever `bootstrap_ha.py` idempotente (onboarding → token → áreas → exposição
   → aliases → grava `.env.test`).
4. Criar `.env.test.example` (template, sem segredos) e `run-integration-tests.sh`.
5. Atualizar `.gitignore` com as exclusões acima.
6. Ajustar `conftest.py` (env-overridable + chave `HOME_ASSISTANT_TOKEN`).
7. Documentar o fluxo no `README.md` (seção "Rodando testes de integração
   localmente").

## Critérios de aceite

- `docker compose -f docker/test-backends/docker-compose.dev.yml up -d` sobe os 3
  containers saudáveis.
- `bootstrap_ha.py` é idempotente (rodar 2×  não falha, não duplica) e gera um
  `.env.test` com `HOME_ASSISTANT_TOKEN` válido.
- Com Ollama `unix.rtx-server` vivo, `pytest tests/integration_tests/ -v` roda
  **sem skips** de HA/MA/Redis (todas as fixtures de disponibilidade passam) e
  fica **verde**.
- HA lista áreas `sala`/`quarto`/`cozinha` e entidades `light.*`/`sensor.*`/
  `climate.*`/`camera.*` expostas ao Assist (a query de "status das luzes" retorna
  entidades reais, não vazio).
- Nenhum segredo (token, `.storage/`) commitado.

## Alternativas descartadas

- **Commitar `.storage/` seedado**: vazaria segredo (JWT signing key + token) no
  git; opaco e frágil a upgrades do HA. Descartado em favor do script declarativo.
- **`network_mode: host`**: desnecessário sem discovery real; complica portabilidade.
- **Só integração `demo`** (entidades prontas em todos os domínios): resolveria
  "não skipar + output não-vazio" com esforço mínimo, mas **não** dá nomes/áreas/
  aliases determinísticos que os prompts esperam. Usada apenas para a câmera.
- **Encaixar backends no `docker-compose.override.yml`**: acoplaria o ciclo de
  vida da app aos backends de teste. Descartado (SRP de infra).
```
