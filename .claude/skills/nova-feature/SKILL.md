---
name: nova-feature
description: Orquestra o ciclo completo de implementação de uma nova feature no projeto Peruca, coordenando os agentes especializados em sequência: planejamento colaborativo (arquiteto + especialista-de-prompt + programador-tester), implementação TDD estrito por camadas (testes antes da implementação, sempre), execução e correção de testes, e commit com gitflow. Use este skill sempre que o usuário pedir para "implementar", "criar" ou "adicionar" uma nova funcionalidade ao Peruca — mesmo que não mencione explicitamente os agentes ou o processo.
---

# Nova Feature — Peruca

Workflow para implementar uma feature nova do zero no projeto Peruca, seguindo TDD estrito e a arquitetura em camadas.

## Regra absoluta — TDD

**Os testes unitários DEVEM ser escritos ANTES de qualquer implementação**, sem exceção — incluindo dataclasses, enums e ABCs do domain layer. O fluxo obrigatório é:

```
1. RED    → Testes escritos e falhando (implementação não existe)
2. GREEN  → Implementação mínima para os testes passarem
3. REFACTOR → Melhoria mantendo todos os testes verdes
```

O `programador` só começa a implementar após o `programador-tester` confirmar que os testes estão escritos.

## Quando usar

- Usuário pede para implementar uma nova funcionalidade
- Usuário descreve um novo comportamento que o Peruca deve ter
- Usuário pede para "criar" um novo domínio, grafo, integração ou endpoint

---

## Fase 1 — Planejamento colaborativo

Lance os três agentes **em paralelo na mesma mensagem** antes de escrever qualquer código:

| Agente | Contribuição |
|---|---|
| `arquiteto` | Estrutura de camadas, componentes, ordem de dependências, restrições arquiteturais |
| `especialista-de-prompt` | Conteúdo exato dos prompts `.md`, design dos nós LangGraph, formato JSON de saída |
| `programador-tester` | Plano completo de testes: nomes de método, cenários de borda, fixtures, conftest |

Consolide as três contribuições em um único plano antes de avançar. O plano deve responder:
- Quais arquivos criar/modificar em cada camada
- Qual a ordem de implementação (ditada pelas dependências)
- Quais testes cobrem cada componente

---

## Fase 2 — Escrita dos testes (ANTES da implementação)

O `programador-tester` escreve **todos** os testes unitários antes do `programador` implementar qualquer coisa. Isso inclui testes para:

- Repositório externo (ex: `test_home_assistant_<dominio>_repository.py`)
- Domain service (novos métodos no `test_smart_home_service.py`)
- Graph `_classify_intent` (ex: `test_<dominio>_graph_classify_intent.py`)

Os testes devem estar colecionáveis mesmo com `ImportError` (implementação ainda não existe):
```bash
cd src && .venv/bin/python -m pytest tests/unit_tests/<novos_arquivos> --collect-only
```

O `programador-tester` confirma que os testes estão prontos. Só então o `programador` começa.

---

## Fase 3 — Implementação por camadas

Com os testes prontos, o `programador` implementa em paralelo onde possível, sempre na ordem domain → infra → application → IoC.

### Etapa A — Domain layer + Prompts (paralela)

| Agente | Tarefa |
|---|---|
| `programador` | `domain/entities.py`, `domain/commands.py`, `domain/interfaces/`, `domain/services/` (modificações), `infra/settings.py` |
| `especialista-de-prompt` | Criar arquivos em `infra/prompts/`: classificador do graph, parser de aliases, atualizar `main_graph.md` |

Validar após conclusão:
```bash
cd src && .venv/bin/python -m pytest tests/unit_tests/test_<dominio>_repository.py tests/unit_tests/test_smart_home_service.py -v
```

### Etapa B — Adaptador HA + Graph + MainGraph + IoC (sequencial)

Com os testes do repositório e service passando, o `programador` implementa:

1. `infra/data/external/smart_home/home_assistant/home_assistant_smart_home_<dominio>_repository.py`
2. `application/graphs/<dominio>_graph.py`
3. `application/graphs/main_graph.py` (adicionar o novo subgrafo)
4. `infra/ioc.py` (factories do repositório e do graph)

Validar:
```bash
cd src && .venv/bin/python -m pytest tests/unit_tests/test_<dominio>_graph_classify_intent.py -v
cd src && .venv/bin/python -c "from infra.ioc import get_main_graph; print('OK')"
```

---

## Fase 4 — Testes de integração (após implementação completa)

O `programador-tester` escreve os testes de integração e atualiza o `conftest.py`:

- Um arquivo por domínio: `tests/integration_tests/test_llm_app_service_chat__<dominio>_graph.py`
- Cobertura de todos os intents do subgrafo + testes de fronteira negativos
- O dispositivo físico pode não estar conectado — validar apenas routing e output não-vazio:

```python
assert "<dominio>" in intents
assert isinstance(output, str) and len(output.strip()) > 0
```

---

## Fase 5 — Execução e correção de testes

Rode os testes de integração e corrija iterativamente até todos passarem:

```bash
cd src && .venv/bin/python -m pytest tests/integration_tests/test_llm_app_service_chat__<dominio>_graph.py -v
```

### Erros comuns e correções

| Erro | Causa | Correção |
|---|---|---|
| `KeyError` em `langchain_core/prompts/base.py` | Exemplos JSON no prompt têm `{` e `}` literais interpretados como variáveis de template | Substituir por `(caractere abre chave)` / `(caractere fecha chave)` — igual ao padrão do `smart_home_lights_graph.md` |
| Frase classificada como `only_talking` | Mensagem de teste é declarativa, não imperativa/interrogativa | Adicionar `?` ou reformular como comando |
| `asyncio.run()` dentro de async context | Incompatibilidade com FastAPI async | Manter exatamente o padrão de `SmartHomeLightsGraph` — não alterar |

---

## Fase 6 — Commit

Após **todos** os testes (unitários + integração) passarem:

```bash
git add src/<arquivos_da_feature>
# NÃO commitar .claude/settings.local.json
git commit -m "feat: <descrição da feature>

<detalhes das camadas implementadas>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

Padrão de prefixo (gitflow):
- `feat:` nova funcionalidade
- `fix:` correção de bug
- `test:` testes sem mudança de comportamento
- `refactor:` refatoração sem mudança funcional

---

## Restrições arquiteturais invioláveis

```
API (routes.py) → Application (appservices/, graphs/) → Domain ← Infra
```

1. `domain/` nunca importa de `application/` ou `infra/`
2. Repositórios concretos instanciados apenas em `ioc.py`
3. Nó `classify` faz UMA única chamada LLM (classifica + extrai dados simultaneamente)
4. Nomes de intent no JSON do LLM devem ser idênticos aos nomes dos nós no `StateGraph`
5. `_classify_intent` usa `json.loads()` — nunca `eval()`
6. Nós do graph são síncronos — chamadas async via `asyncio.run()`, sem aninhar
7. Settings nunca hardcodados no código — sempre em `infra/settings.py`

## Padrão de prompt LangGraph

`ChatPromptTemplate.from_template()` interpreta `{variavel}` como placeholder. Em exemplos JSON nos prompts, substituir `{` e `}` por `(caractere abre chave)` e `(caractere fecha chave)`. O único placeholder real é `{input}`.

Diretiva de modelo: subgrafos usam `/no_thinking` na primeira linha. `main_graph.md` usa `/no_think`.

## Referências no codebase

| O que consultar | Onde |
|---|---|
| Padrão de graph | `src/application/graphs/smart_home_lights_graph.py` |
| Padrão de adaptador HA | `src/infra/data/external/smart_home/home_assistant/home_assistant_smart_home_light_repository.py` |
| Padrão de testes unitários (graph) | `src/tests/unit_tests/test_smart_home_lights_graph_classify_intent.py` |
| Padrão de testes de integração | `src/tests/integration_tests/test_llm_app_service_chat__smart_home_lights_graph.py` |
| Padrão de prompt classificador | `src/infra/prompts/smart_home_lights_graph.md` |
| Padrão de prompt alias parser | `src/infra/prompts/smart_home_lights_graph_id_parser_by_alias.md` |
