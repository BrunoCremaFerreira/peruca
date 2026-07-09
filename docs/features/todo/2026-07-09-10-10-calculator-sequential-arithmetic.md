# Plano: Calculadora Sequencial via Chat (Calculator Graph)

- **Status:** todo
- **Criado em:** 2026-07-09 10:10
- **Implementado em:** —
- **PR/commit:** —
- **Branch (a criar quando o plano for aprovado):** `feature/calculator-graph`
- **Consultorias realizadas (obrigatórias):** `arquiteto`, `especialista-de-prompt`, `programador-tester`

---

## 1. Problema e objetivo

O usuário quer ditar vários valores ao Peruca ("soma 10 com 25, multiplica por 2 e
divide por 3") e receber o resultado de soma, subtração, multiplicação e divisão
**na ordem em que os valores foram ditos** (avaliação sequencial esquerda→direita,
**sem precedência de operadores**), com precisão exata e **zero alucinação**.

**Regra de ouro da feature:** o LLM **nunca** faz aritmética. Ele apenas
**transcreve** a expressão dita pelo usuário; todo o cálculo acontece em Python
puro com `Decimal`. É o mesmo padrão já consolidado pelo `date_resolver.py` do
vehicle-maintenance ("o LLM só emite tokens; o Python resolve").

## 2. Estado atual relevante (verificado no código)

- `MainGraph` classifica intents e roteia para sub-graphs; o nome do node no
  `StateGraph` deve ser idêntico à string de intent do prompt (`intent_router`
  retorna `state["intent"]` como edge target).
- Graphs novos (smart-home, music, vehicle, pet) parseiam a saída do classify com
  `json.loads()` após `Graph._extract_structured_output()`; temperatura 0.1;
  `/no_think` no topo do prompt; aspas retas obrigatórias.
- Precedentes a reutilizar: classe base `Graph` (cache de `_compiled_graph`,
  `load_prompt`, `_remove_thinking_tag`), fallback `not_recognized` → `only_talk`
  (`MainGraph._handle_pet_health`), hard-caps anti-injection
  (`_QUERY_RECORD_LIMIT`), e o **bypass de merge** `SHOPPING_LIST_HEADER` em
  `application/graphs/markers.py`.
- Não há nada de calculadora hoje; "quanto é X mais Y" cai em `only_talking` e o
  modelo calcula (e pode errar) — exatamente o que a feature elimina.

## 3. Decisão central: formato da extração

Houve divergência entre as consultorias, resolvida assim:

**Escolhido — string de expressão canônica** (parecer do `especialista-de-prompt`):

```json
{"intents": ["calculate"], "expression": "10 + 5 * 2 / 3", "reason": ""}
```

- Um único grau de liberdade; schema raso (padrão de todos os prompts do repo).
- 100% validável em Python por regex fechada:
  `^-?\d+(\.\d+)?(\s*[+\-*/]\s*-?\d+(\.\d+)?)*$` — que **rejeita por construção**
  notação científica (`1E+999`), `=`, parênteses e qualquer lixo. Isso atende o
  requisito de hardening do `arquiteto` (DoS por `Decimal` gigante) de forma mais
  simples que validar campos aninhados.
- Tokenização e avaliação esquerda→direita ficam inteiramente no Python.

**Descartado — `{"initial": "10", "steps": [{"op": "add", "value": "5"}]}`**
(parecer do `arquiteto`): JSON aninhado é onde o gemma4:12b mais erra (step
perdido, chave trocada); nenhum prompt do projeto usa aninhamento. Os objetivos
que motivaram o formato (valores como string para não perder precisão em float,
conjunto fechado de operadores, validação campo a campo) são todos preservados na
string canônica — ela nunca passa por float e o parser Python só aceita os 4
operadores.

**Descartado — arrays paralelos** (`"values": [...], "operators": [...]`):
desalinhamento silencioso (operador omitido desloca tudo sem erro de parse).

## 4. Arquitetura (parecer do `arquiteto`, adaptado ao formato escolhido)

### 4.1 Componentes novos

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| `CalculatorGraph` | `src/application/graphs/calculator_graph.py` | Herda de `Graph`. Nodes: `classify` (única chamada LLM: extrai o JSON acima) → `calculate` / `not_supported` / `not_recognized`. O node `calculate` é 100% determinístico: valida, chama o domínio, formata por template — **sem segunda chamada LLM**. |
| Serviço de cálculo | `src/domain/services/calculator_service.py` | **Módulo de funções puras** (precedente: `date_resolver.py`), só stdlib (`decimal`, `re`). `evaluate_expression(expression: str) -> Decimal`: valida (regex + limites), tokeniza e faz fold esquerda→direita. Sem classe, sem factory na IoC — o graph importa direto. |
| Exceções | `src/domain/exceptions.py` | `DivisionByZeroError(ValidationError)` — nunca deixar `decimal.DivisionByZero` da stdlib vazar. Entrada malformada/limites → `ValidationError` (nunca `TypeError`/`IndexError` cru). |
| Prompt | `src/infra/prompts/calculator_graph.md` | Rascunho aprovado em §6. |
| Marcador | `application/graphs/markers.py` | `CALCULATOR_RESULT_HEADER`, com bypass no merge (§7). |

Sem entidade persistida → **sem repositório, sem interface, sem UUID, sem
migração, sem rota REST, sem FlowService**. v1 é single-turn.

### 4.2 Validação e limites (hardening obrigatório)

Dentro de `calculator_service` (a origem dos dados é o LLM — tratar como entrada
hostil):

- Regex fechada acima (rejeita notação científica, `NaN`/`Infinity`, texto).
- Máx. **50 operandos** e máx. **20 dígitos por valor** (mesma filosofia do
  hard-cap `_QUERY_RECORD_LIMIT`).
- Vírgula decimal residual normalizada `","`→`"."` deterministicamente antes da
  regex (o prompt já pede ponto, mas não confiamos nele).
- Divisão por zero → `DivisionByZeroError`; a cadeia aborta.
- Expressão com um único valor e nenhum operador → identidade (retorna o valor).
- Expressão vazia / só operador ("soma 5") → `ValidationError`; o node responde
  por template pedindo a expressão completa (não existe intent `unclear` — a
  incompletude é detectada estruturalmente, não pelo LLM).
- **Jamais** `eval()`/`ast.literal_eval()` sobre a expressão — só regex + fold.
- Camadas: `calculator_service.py` sem imports de `infra/` nem langchain.

### 4.3 Tipo numérico e formatação

- `Decimal` com contexto default (28 dígitos) — `0.1 + 0.2 == Decimal("0.3")`
  exato; divisões periódicas (10/3) ficam limitadas pelo contexto. O teste
  unitário fixa a quantização exibida (sugestão: normalizar/quantizar para até
  10 casas na **apresentação**, domínio devolve `Decimal` cru).
- Formatação pt-BR (vírgula decimal, trim de zeros: `Decimal("20")` → `"20"`,
  nunca `"20.000000"`) é responsabilidade do **graph** (apresentação).

## 5. Intent no MainGraph (parecer do `especialista-de-prompt`)

- Nome: **`"calculator"`** (vira o nome do node; padrão substantivo de domínio).
- Alterações em `main_graph.py`: campo `output_calculator` no `MainGraphState`;
  parâmetro no construtor; node `"calculator"`; handler `_handle_calculator` com
  fallback `not_recognized` → `only_talk` (copiar `_handle_pet_health`); incluir
  `output_calculator` no merge do `_handle_final_response`. Sem gate opcional
  (não há dependência externa) — wired incondicionalmente.
- Regra de desambiguação a adicionar em `infra/prompts/main_graph.md`:
  **`calculator` somente quando o usuário pede operação aritmética explícita
  entre valores numéricos "nus" presentes na própria mensagem.** Colisões
  mapeadas (com exemplos negativos no prompt):
  - "soma 3 maçãs na lista" → `shopping_list` (números qualificam itens);
  - "coloca o volume em 50" → `music`; "ar em 22 graus" → `smart_home_climate`;
  - "troquei o óleo com 100232 km" → `vehicle_maintenance`;
  - "quanto custa a revisão?" → `only_talking` (pergunta de conhecimento).

## 6. Prompt `calculator_graph.md` (rascunho aprovado)

Estrutura espelhando `vehicle_maintenance_graph.md`: `/no_think` + papel +
"APENAS um objeto JSON"; seção destacada **REGRA DE OURO** ("Você NUNCA calcula.
NUNCA escreva o resultado, NUNCA inclua `=`, NUNCA reordene nem aplique
precedência — apenas transcreva", com contra-exemplo errado vs. certo); regras de
transcrição (extenso→dígitos, vírgula→ponto, operadores só `+ - * /`); intents
`calculate` / `not_supported` / `not_recognized`; formato com todos os campos
sempre presentes; **8 few-shots**:

1. 2 valores simples ("quanto é 10 mais 5?" → `"10 + 5"`)
2. N valores mistos provando ordem falada ("10 mais 5 vezes 2" → `"10 + 5 * 2"`)
3. Decimal com vírgula ("2,5 vezes 4" → `"2.5 * 4"`)
4. Extenso puro ("dez mais cinco" → `"10 + 5"`)
5. Extenso misturado com dígito ("vinte dividido por 4" → `"20 / 4"`)
6. Contra-exemplo de cálculo (saída sem `=` nem resultado)
7. `not_supported` com `reason: "percentage"` ("10% de 200")
8. `not_recognized` com números de outro domínio ("comprei 3 maçãs por 10 reais")

Config: temperatura **0.1**, parser `json.loads` via
`Graph._extract_structured_output`, aspas retas.

Template de resposta do node `calculate` (determinístico):
`"10 + 5 × 2 = 30 (calculado na ordem em que você disse)"` — ecoar a expressão dá
transparência e a nota previne estranhamento pela ausência de precedência.
Divisão por zero → template fixo amigável.

## 7. Risco crítico: o merge do `final_response`

Em multi-intent ("soma 10 e 25 e apaga a luz"), o output do `CalculatorGraph`
passa pelo LLM de `main_graph_final_response.md`, que pode "recalcular" o número
aplicando precedência — anulando a garantia da feature pela porta dos fundos.
Mitigação dupla:

1. **Primária (determinística):** `CALCULATOR_RESULT_HEADER` em `markers.py` com
   o mesmo bypass do `SHOPPING_LIST_HEADER` — o trecho do resultado não passa
   pelo LLM de merge e é concatenado depois.
2. **Defesa em profundidade:** regra no `main_graph_final_response.md`:
   "Resultados de cálculo (linhas com `=`): repasse número e expressão EXATAMENTE
   como vieram; NUNCA recalcule ou corrija."

## 8. Wiring — checklist

1. `infra/settings.py`: `llm_calculator_graph_chat_model` (default `gemma4:12b`),
   `llm_calculator_graph_chat_temperature: float = 0.1`,
   `llm_calculator_graph_chat_reasoning: bool | None = None`.
2. `infra/ioc.py`: `get_calculator_graph()` com cache em
   `_repo_cache[("graph", "calculator")]` (seguir `get_pet_health_graph()`).
3. `main_graph.py` + `infra/prompts/main_graph.md` (§5).
4. `infra/prompts/main_graph_final_response.md` + `markers.py` (§7).
5. `.env.example` e lista de env vars do `CLAUDE.md`.

## 9. Estratégia TDD (parecer do `programador-tester`, adaptado ao formato string)

Ordem de nascimento — cada arquivo vermelho antes da implementação correspondente:

### 9.1 `tests/unit_tests/test_calculator_service.py` (primeiro; domínio puro, sem mocks)

- `TestEvaluateBasicOperations`: 2+3=5; 10-4=6; 6*7=42; 10/4=2.5.
- `TestEvaluateSequentialOrder` (a regra de negócio central):
  **`"2 + 3 * 4"` = 20, não 14** (teste que documenta a decisão); `10/2+3=8`;
  `5-1*3=12`; cadeia com 5+ operandos.
- `TestEvaluateDecimalPrecision`: `"0.1 + 0.2"` == `Decimal("0.3")` exato;
  `1/3` com comportamento de quantização fixado; `1.5-2.7 = -1.2` exato.
- `TestEvaluateNegativesAndEdges`: `-5+3=-2`; resultado zero; valor único →
  identidade; `0/5=0`.
- `TestEvaluateDivisionByZero`: `DivisionByZeroError`; `"4 + 6 / 0 - 1"` aborta.
- `TestEvaluateMalformedInput` (tudo → `ValidationError`): string vazia;
  operador pendurado (`"5 +"`); operador desconhecido (`"2 ^ 3"`); texto;
  notação científica `"1E+999"`; `NaN`/`Infinity`; `None`/não-string.
- `TestEvaluateLimits`: >50 operandos; valor com >20 dígitos.

### 9.2 `tests/unit_tests/test_calculator_graph_classify_intent.py` + `test_calculator_graph_handlers.py`

Padrão `test_pet_health_graph_classify_intent.py` (`patch.object(load_prompt)`,
`llm_chat=MagicMock()`, injeção do JSON):

- `TestClassify`: JSON feliz; JSON malformado → `not_recognized` sem exceção;
  `["not_recognized"]` explícito; resposta com `<think>` (sem mockar o extrator —
  cobre `_remove_thinking_tag` real); expressão que não passa na regex
  (`"10 + banana"`) → resposta amigável sem stack trace.
- `TestCalculateNode`: delega ao serviço e formata; `DivisionByZeroError` →
  mensagem amigável pt-BR; **assert de que `llm_chat` não é chamado no node de
  ação**; `Decimal("20")` formatado `"20"`; output prefixado com
  `CALCULATOR_RESULT_HEADER`.

### 9.3 `tests/unit_tests/test_main_graph_calculator.py`

Padrão `test_main_graph_pet_health.py`: intent `["calculator"]` roteia para
`CalculatorGraph.invoke`; não chama `only_talk`; fallback `not_recognized` →
`only_talk`. + teste da factory na IoC se `test_ioc_graph_cache.py` exigir.

### 9.4 `tests/integration_tests/test_llm_app_service_chat__calculator_graph.py` (por último, Ollama vivo, skip gracioso)

- **B1 — roteamento + extração (~7 frases):** "quanto é 2 mais 3 vezes 4?" →
  output contém "20" (sequencial fim-a-fim); "10 dividido por 4" → "2,5"/"2.5";
  "soma 0,1 com 0,2" → "0,3" (vírgula BR); "quanto é dois mais dois?" (extenso);
  "15 menos 20" (negativo); "100 dividido por 0" (mensagem amigável, sem 500);
  "me diz quanto dá 5 vezes 5 menos 3".
- **B2 — anti-falso-positivo (~4 frases, nunca `calculator`):** "você é bom de
  matemática?"; "adicione 2 litros de leite na lista" (→ `shopping_list`);
  "quantas vacinas o Caçolin tomou?"; "conta uma história".
- Aceite no padrão do repo: 100% por bateria, até 2 frases flaky movidas para
  `AMBIGUOUS_EXCLUDED` documentada. Sem fixture de dados.

Convenções: métodos `test_<cenário>__<resultado>`; helpers `_make_graph()`,
`_user()`; `pytest.importorskip("langgraph")` nos testes de graph.

## 10. Fora de escopo v1 (alternativas descartadas / extensões futuras)

- **Porcentagem, potência, raiz, parênteses, média** → `not_supported` com
  `reason` (transformar "10% de 200" em `200 * 0.1` já seria meio cálculo do LLM).
- **Problemas em linguagem natural** ("tinha 150, gastei 30, quanto sobrou?") →
  `only_talking`, com exemplo negativo no prompt (zona cinzenta grande:
  "gastei metade" exige raciocínio).
- **Follow-up multi-turn** ("e dividido por 2?") — exigiria FlowService/focused
  result; anotado como extensão futura.
- **Validator fluente dedicado** — descartado (sem entidade persistida; a
  validação estrutural vive no próprio serviço). Se o formato evoluir para
  objeto, revisitar com `CalculationExpressionValidator` (lembrando o
  `.validate()` final obrigatório).

## 11. Sequência de implementação

1. Testes do serviço de domínio (§9.1, vermelhos) → `calculator_service.py` +
   `DivisionByZeroError`.
2. Testes do graph (§9.2, vermelhos) → `CalculatorGraph` + `calculator_graph.md`
   + `CALCULATOR_RESULT_HEADER`.
3. Testes de roteamento (§9.3, vermelhos) → wiring `main_graph.py`, `ioc.py`,
   `settings.py`, prompts do MainGraph e do final_response.
4. `.env.example` + `CLAUDE.md`.
5. Bateria de integração (§9.4) com Ollama vivo; ajuste fino de prompt se
   necessário.
6. Mover este plano para `doing/` ao iniciar e `done/` ao concluir, preenchendo
   o cabeçalho.
