# Plano: Calculadora Sequencial e Científica via Chat (Calculator Graph)

- **Status:** todo
- **Criado em:** 2026-07-09 10:10
- **Atualizado em:** 2026-07-10 (extensão: raiz quadrada, logaritmos, percentual,
  potência e cálculo simbólico — integrais, derivadas, gradientes, limites)
- **Implementado em:** —
- **PR/commit:** —
- **Branch (a criar quando o plano for aprovado):** `feature/calculator-graph`
- **Consultorias realizadas (obrigatórias):** `arquiteto`, `especialista-de-prompt`,
  `programador-tester` — rodada 1 (2026-07-09, calculadora sequencial) e rodada 2
  (2026-07-10, extensão científica/simbólica)

---

## 1. Problema e objetivo

O usuário quer ditar vários valores ao Peruca ("soma 10 com 25, multiplica por 2 e
divide por 3") e receber o resultado de soma, subtração, multiplicação e divisão
**na ordem em que os valores foram ditos** (avaliação sequencial esquerda→direita,
**sem precedência de operadores**), com precisão exata e **zero alucinação**.

**Extensão (2026-07-10):** o Peruca também deve suportar:

1. **Operações numéricas científicas:** raiz quadrada, logaritmos (ln, log10,
   log base n), percentual ("10% de 200", "150 mais 15%") e potência
   ("2 elevado a 10").
2. **Cálculo simbólico com precisão:** integrais (ex.: ∫cos(w·x)² dx), derivadas,
   gradientes, limites e simplificação de expressões — resolvidos por CAS
   (SymPy) em Python.

**Regra de ouro da feature (inalterada e estendida):** o LLM **nunca** faz
matemática — nem aritmética, nem cálculo simbólico. Ele apenas **transcreve** a
expressão dita pelo usuário para uma forma canônica; todo o cálculo acontece em
Python — o numérico com `Decimal` (stdlib) e o simbólico com SymPy atrás de uma
porta de domínio. É o mesmo padrão já consolidado pelo `date_resolver.py` do
vehicle-maintenance ("o LLM só emite tokens; o Python resolve"). No modo
simbólico, o LLM transcreve `x**3` com `operation: "diff"` — jamais emite
`3*x**2` (isso seria derivar, ou seja, calcular).

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
- **SymPy não é dependência do projeto ainda** (verificado em requirements e
  imports) — a extensão introduz a dependência (§8).

## 3. Decisão central: formato da extração

Houve divergência entre as consultorias (rodada 1), resolvida assim:

**Escolhido — string de expressão canônica** (parecer do `especialista-de-prompt`):

```json
{"intents": ["calculate"], "expression": "10 + 5 * 2 / 3", "operation": "", "variable": "", "to": "", "reason": ""}
```

- Um único grau de liberdade na expressão; schema raso com **todos os campos
  sempre presentes** (padrão de todos os prompts do repo — o gemma4:12b copia bem
  um template fixo; erra quando precisa decidir *quais* chaves emitir).
- Tokenização e avaliação esquerda→direita ficam inteiramente no Python.

**Extensão (rodada 2) — duas intents no classify do próprio `CalculatorGraph`:**

```json
{"intents": ["calculate_symbolic"], "operation": "integrate", "expression": "cos(omega*x)**2", "variable": "x", "to": "", "reason": ""}
```

- `calculate` → node numérico (Decimal, fold sequencial);
  `calculate_symbolic` → node simbólico (SymPy). No `MainGraph` continua **uma
  única intent `calculator`** — a distinção numérico/simbólico é interna ao
  sub-graph (espelha `shopping_list`: uma intent de domínio, várias operações).
- `operation` em conjunto fechado: `integrate | diff | gradient | limit |
  simplify` (vazio no modo numérico). `variable` como **string plana**
  (`"x"` / `"x,y,z"` — nunca lista JSON; consistente com os separadores do
  repo); vazia → o Python infere `sorted(expr.free_symbols)`. `to` usado apenas
  por `limit` (`"0"`, `"oo"`).
- A decisão "resultado numérico vs expressão simbólica" também é do **Python**
  (`expr.free_symbols` vazio → `evalf`), nunca do LLM.

**Validação da expressão numérica — de regex única para tokenizador fechado:**
com `%`, `**` e funções (`sqrt`/`log`) na gramática, a regex única do plano
original vira ilegível; substituir por um **tokenizador de conjunto fechado**
(continua sem `eval`, mais legível e testável). Continua rejeitando por
construção notação científica (`1E+999`), `=`, texto e qualquer lixo — atende o
hardening do `arquiteto` (DoS por `Decimal` gigante).

**Descartados:**

- **`{"initial": "10", "steps": [{"op": "add", "value": "5"}]}`** (rodada 1):
  JSON aninhado é onde o gemma4:12b mais erra; nenhum prompt do projeto usa
  aninhamento. Os objetivos do formato são preservados na string canônica.
- **Arrays paralelos** (`"values": [...], "operators": [...]`): desalinhamento
  silencioso.
- **Campo `"mode": "numeric"|"symbolic"`** (rodada 2): no padrão do repo a
  string de intent **é** o nome do node (`intent_router` retorna
  `state["intent"]` direto); um `mode` exigiria tradução intent→node que nenhum
  graph faz hoje.
- **String única estilo chamada `integrate(cos(w*x)**2, x)`** (rodada 2):
  mistura operação com expressão, e o gemma tende a "ajudar" (resolver) quando
  vê a chamada completa; campos separados dão slots fixos e validação trivial.

## 4. Arquitetura (pareceres do `arquiteto`, adaptados)

### 4.1 Componentes novos

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| `CalculatorGraph` | `src/application/graphs/calculator_graph.py` | Herda de `Graph`. Nodes: `classify` (única chamada LLM: extrai o JSON acima) → `calculate` / `calculate_symbolic` / `not_supported` / `not_recognized`. Os nodes de ação são 100% determinísticos: validam, chamam o domínio, formatam por template — **sem segunda chamada LLM**. |
| Serviço numérico | `src/domain/services/calculator_service.py` | **Módulo de funções puras** (precedente: `date_resolver.py`), só stdlib (`decimal` + tokenizador próprio). `evaluate_expression(expression: str) -> Decimal`: valida (tokenizador fechado + limites), tokeniza e faz fold esquerda→direita. Cobre `+ - * / **`, operando com sufixo `%` e funções `sqrt`/`ln`/`log10`/`log(x, base)` **com argumentos numéricos literais** (via `Decimal.sqrt()`, `.ln()`, `.log10()`; `log(x, base) = ln(x)/ln(base)`). Sem classe, sem factory na IoC — o graph importa direto. |
| Serviço simbólico | `src/domain/services/symbolic_math_service.py` | Valida a requisição (operação no conjunto fechado, caps do §4.3, pré-validação léxica) e **delega à porta** `SymbolicMathEngine`. Sem SymPy importado no domínio. |
| Porta do motor CAS | `src/domain/interfaces/symbolic_math_engine.py` | ABC `SymbolicMathEngine` — contrato de `integrate/diff/gradient/limit/simplify` sobre expressões canônicas. Permite mockar domínio e graph sem SymPy. |
| Adapter SymPy | `src/infra/math/sympy_symbolic_math_engine.py` | `SympySymbolicMathEngine`: parse seguro (`parse_expr` restrito, §4.3), execução com timeout em processo separado, pós-checagens (`Integral` não resolvido, `zoo`/`nan`, `Piecewise`). **Lazy import** do SymPy (primeiro uso, cache em módulo). |
| Exceções | `src/domain/exceptions.py` | `DivisionByZeroError(ValidationError)`; **novas:** `MathDomainError(ValidationError)` (raiz de negativo, log de zero/negativo, log base 1), `NoClosedFormError(ValidationError)` (integral sem forma fechada), `CalculationTimeoutError(ValidationError)` (timeout do motor). Nunca deixar `decimal.InvalidOperation`/`decimal.DivisionByZero` ou exceções do SymPy vazarem cruas. |
| Prompt | `src/infra/prompts/calculator_graph.md` | Rascunho aprovado em §6. |
| Marcador | `application/graphs/markers.py` | `CALCULATOR_RESULT_HEADER`, com bypass no merge (§7) — cobre os **dois** nodes de ação. |

Sem entidade persistida → **sem repositório de dados, sem UUID, sem migração,
sem rota REST, sem FlowService**. v1 é single-turn.

**Decisão de camada (parecer do `arquiteto`):** SymPy **não** entra em
`domain/services/` — o precedente `date_resolver.py` é explicitamente "stdlib
pura", e o motivo decisivo não é só pureza, é **execução**: integrais podem não
terminar, então o motor precisa de isolamento de processo + timeout + kill, que
é maquinário de infraestrutura. Daí a porta em `domain/interfaces/` + adapter em
`infra/math/`, wired via `ioc.py`. Trade-off aceito: mais cerimônia que um
módulo de funções puras; vale pelo hardening e pela testabilidade com mock.

**Divergência resolvida (rodada 2) — onde vivem raiz e log:** o `arquiteto`
propôs mandar toda função unária para o caminho SymPy; o
`especialista-de-prompt` e o `programador-tester` convergiram em mantê-las no
motor Decimal quando os argumentos são **numéricos literais** (`sqrt(144)`,
`log(100, 10)` — `Decimal` tem `sqrt`/`ln`/`log10` nativos e exatos nos casos
exatos, sem custo de processo filho no caminho comum). **Escolhido: Decimal para
argumentos literais; qualquer símbolo ou aninhamento não-literal →
`calculate_symbolic`.** A ambiguidade de escopo apontada pelo arquiteto
("raiz de 16 mais 9" — `sqrt(16) + 9` vs `sqrt(16 + 9)`) é resolvida por
**transcrição com parênteses** conforme a prosódia do ditado (few-shot em §6) —
escolha de transcrição, não de aritmética; regra de ouro preservada.

### 4.2 Validação e limites — modo numérico (hardening obrigatório)

Dentro de `calculator_service` (a origem dos dados é o LLM — tratar como entrada
hostil):

- Tokenizador de conjunto fechado (§3): operando := `-?\d+(\.\d+)?%?` ou chamada
  de função da whitelist numérica (`sqrt`, `ln`, `log10`, `log`) com argumentos
  **numéricos literais**; operadores := `+ - * / **`. Rejeita por construção
  notação científica, `NaN`/`Infinity`, `=`, texto, função desconhecida.
- Máx. **50 operandos** e máx. **20 dígitos por valor** (mesma filosofia do
  hard-cap `_QUERY_RECORD_LIMIT`).
- **Potência:** expoente inteiro com `|exp| ≤ 100`, e a proteção contra
  `9**9**9` é **pré-checagem** (`digitos(base) * exp ≤ N`) — nunca "calcular e
  ver se estoura". `Emax` configurado no contexto `Decimal` como segunda
  barreira.
- **Percentual (semântica de calculadora de mesa, resolvida no fold):** operando
  `n%` com `+`/`-` é relativo ao acumulado (`a + n% = a*(1+n/100)`,
  `a - n% = a*(1-n/100)`); com `*`/`/` é fator (`n/100`). Assim
  `10% * 200 = 20` e `150 + 15% = 172.5` sem o LLM calcular nada.
- **Raiz/log:** `sqrt` de negativo, `log` de zero/negativo, `log` base 1/zero/
  negativa → `MathDomainError` (nunca vazar `decimal.InvalidOperation`).
- Vírgula decimal residual normalizada `","`→`"."` deterministicamente antes da
  tokenização (o prompt já pede ponto, mas não confiamos nele).
- Divisão por zero → `DivisionByZeroError`; a cadeia aborta.
- Expressão com um único valor e nenhum operador → identidade (retorna o valor).
- Expressão vazia / só operador ("soma 5") → `ValidationError`; o node responde
  por template pedindo a expressão completa (não existe intent `unclear` — a
  incompletude é detectada estruturalmente, não pelo LLM).
- **Jamais** `eval()`/`ast.literal_eval()` sobre a expressão — só tokenizador +
  fold.
- Camadas: `calculator_service.py` sem imports de `infra/` nem langchain.

### 4.3 Validação e limites — modo simbólico (hardening obrigatório)

`sympy.sympify()` usa `eval()` internamente — **é vetor de RCE com entrada vinda
de LLM e está proibido**. Pipeline em três barreiras (serviço + adapter):

1. **Pré-validação léxica fechada** (no `symbolic_math_service`, antes de
   qualquer SymPy): charset `[0-9a-zA-Z_+\-*/(). ,^]`; rejeitar `__`, `[`, `]`,
   aspas, `\`, `=`, `!`, `lambda`; extrair identificadores e rejeitar qualquer
   um fora de `_ALLOWED_FUNCTIONS` ∪ símbolos permitidos.
2. **Parse restrito** (no adapter):
   `parse_expr(s, local_dict=WHITELIST, global_dict={}, evaluate=False)` +
   **walk de validação dos nós antes de qualquer avaliação** — `parse_expr` não
   é sandbox por si só: com `evaluate=True`, `10**10**10` é computado na hora do
   parse, e formas de acesso a atributo passam se não bloqueadas. Jamais
   `sympify()`/`eval()` diretos. `transformations=standard_transformations`
   (sem `implicit_multiplication`).
3. **Execução em processo separado** com timeout:
   `multiprocessing.Process` + `join(timeout)` + `terminate()` — `SIGALRM` não é
   confiável fora da main thread do FastAPI, e `ProcessPoolExecutor` não cancela
   tarefa em execução. Worker **longevo e lazy** (criado na 1ª requisição
   simbólica, reciclado apenas quando o timeout o mata) para não pagar o import
   do SymPy por chamada. O serviço recebe o timeout como seam injetável
   (`_run_with_timeout`) para os testes (§9).

**Hard-caps concretos** (mesmo espírito do `_QUERY_RECORD_LIMIT`):

- `_MAX_SYMBOLIC_EXPRESSION_LENGTH = 200` chars (rejeição **antes** do parse)
- `_MAX_SYMBOLIC_AST_NODES = 100` (via `preorder_traversal` pós-parse,
  `evaluate=False`)
- `_MAX_SYMBOLIC_SYMBOLS = 5`
- `_MAX_SYMBOLIC_EXPONENT = 100` (expoente literal; `2**999999` rejeitado no
  walk)
- `_SYMBOLIC_TIMEOUT_SECONDS = 5`
- `_ALLOWED_FUNCTIONS = {sin, cos, tan, asin, acos, atan, sinh, cosh, tanh,
  exp, log, ln, sqrt, Abs}` + constantes `{pi, E}`; símbolos livres arbitrários
  (identificadores alfabéticos ≤ 8 chars) são **permitidos** — só *chamadas de
  função* fora da whitelist são rejeitadas.

**Pós-checagens do resultado (adapter):**

- `integrate` devolvendo `Integral` não-avaliado (sem forma fechada, ex.
  `x**x`) → `NoClosedFormError` → template amigável ("não consegui resolver
  simbolicamente") — nunca ecoar o objeto cru.
- `result.has(zoo, nan)` → `MathDomainError` (ex.: `log(0)` vira `zoo`, não
  exceção — sem a checagem o usuário recebe "zoo" no chat).
- **`Piecewise` em integrais paramétricas:** `integrate(cos(w*x)**2, x)` com `w`
  genérico devolve `Piecewise((x, Eq(w, 0)), (x/2 + sin(2*w*x)/(4*w), True))`.
  **Decisão:** apresentar o **ramo genérico** (condição `True`) — é a resposta
  que o usuário espera (`x/2 + sin(2wx)/(4w)`). Alternativa descartada: criar
  símbolos com assumptions (`Symbol('w', nonzero=True)`) — muda a semântica
  matemática silenciosamente.
- **Racionais, não floats:** `parse_expr("1/2")` dá `Rational(1,2)` exato, mas
  `"0.5"` dá `Float` e contamina toda a expressão; o prompt prefere frações e
  um teste fixa o comportamento com float na entrada.
- `gradient` retorna vetor com **ordem fixada** (ordem de `variable` declarada;
  fallback ordem alfabética de `free_symbols`) — sem isso a saída flake.

### 4.4 Tipo numérico e formatação

- `Decimal` com contexto default (28 dígitos) — `0.1 + 0.2 == Decimal("0.3")`
  exato; divisões periódicas (10/3), raízes irracionais e potências fracionárias
  ficam limitadas pelo contexto. O teste unitário fixa a quantização exibida
  (sugestão: normalizar/quantizar para até 10 casas na **apresentação**, domínio
  devolve `Decimal` cru).
- Formatação pt-BR (vírgula decimal, trim de zeros: `Decimal("20")` → `"20"`,
  nunca `"20.000000"`) é responsabilidade do **graph** (apresentação).
- **Resultado simbólico:** o graph formata `str(expr)` do SymPy (com `**`→`^` ou
  sobrescrito na apresentação, a decidir na implementação); a ordem dos termos
  no `str()` **muda entre versões do SymPy** — testes assertam fragmentos
  estáveis, nunca a string completa (§9).

## 5. Intent no MainGraph (parecer do `especialista-de-prompt`)

- Nome: **`"calculator"`** (vira o nome do node; padrão substantivo de domínio).
  **Continua um único node** — a distinção numérico/simbólico é interna ao
  `CalculatorGraph` (§3).
- Alterações em `main_graph.py`: campo `output_calculator` no `MainGraphState`;
  parâmetro no construtor; node `"calculator"`; handler `_handle_calculator` com
  fallback `not_recognized` → `only_talk` (copiar `_handle_pet_health`); incluir
  `output_calculator` no merge do `_handle_final_response`. Sem gate opcional
  (não há dependência externa) — wired incondicionalmente.
- Regra de desambiguação em `infra/prompts/main_graph.md` (**revisada na rodada
  2** — a regra original "aritmética entre valores numéricos nus" deixaria
  "derivada de x ao cubo" escapar para `only_talking`):

  > **`calculator`** → quando a mensagem contém uma **expressão matemática
  > concreta a ser resolvida** — operandos numéricos ("10 mais 5", "10% de
  > 200", "raiz de 144") **ou simbólicos com variáveis matemáticas** como x, y,
  > ômega ("derivada de x ao cubo", "integral de cosseno de x", "simplifica x
  > mais x") — acompanhada de um pedido de resolução ("quanto é/dá", "calcule",
  > "derive", "integre", "simplifique"). Perguntas **conceituais** sobre
  > matemática e usos **figurados** de termos matemáticos não são `calculator`.

- Colisões mapeadas (com exemplos negativos no prompt):
  - "soma 3 maçãs na lista" → `shopping_list` (números qualificam itens);
  - "coloca o volume em 50" → `music`; "ar em 22 graus" → `smart_home_climate`;
  - "troquei o óleo com 100232 km" → `vehicle_maintenance`;
  - "quanto custa a revisão?" → `only_talking` (pergunta de conhecimento);
  - **novos (rodada 2):** "o que é uma integral? me explica" → `only_talking`
    (conceitual, sem expressão a resolver); "qual a raiz do problema?" / "meu
    limite de cartão é 5000" → `only_talking` (sentido figurado); "derivada
    segunda é muito difícil, né?" → `only_talking` (comentário, sem pedido).

## 6. Prompt `calculator_graph.md` (rascunho aprovado)

Estrutura espelhando `vehicle_maintenance_graph.md`: `/no_think` + papel +
"APENAS um objeto JSON"; seção destacada **REGRA DE OURO** ("Você NUNCA calcula.
NUNCA escreva o resultado, NUNCA inclua `=`, NUNCA reordene nem aplique
precedência no modo numérico, NUNCA derive/integre/simplifique você mesmo —
apenas transcreva", com contra-exemplos errado vs. certo nos dois modos).

**Regras de transcrição:**

- Extenso→dígitos; vírgula→ponto; operadores numéricos `+ - * / **`.
- Potência **sempre `**`** nos dois modos ("ao quadrado" → `** 2`, "ao cubo" →
  `** 3`, "elevado a N" → `** N`).
- Percentual: sufixo `%` no número dito com percentual, **em ordem falada**;
  "**de** após percentual" → `*` ("10% de 200" → `10% * 200`) — sem reordenar,
  sem converter.
- Multiplicação **sempre explícita** no simbólico: "x²y" → `x**2*y`, nunca
  `x**2y`.
- Funções pela whitelist com mapa pt-BR: "seno"→`sin`, "cosseno"→`cos`,
  "raiz quadrada"→`sqrt`, "logaritmo"→`log`/`ln`/`log10`.
- Letras gregas por nome ASCII: "ômega"→`omega`, "teta"→`theta`.
- Ambiguidade de escopo por voz: **"ao quadrado" eleva o termo imediatamente
  anterior completo** ("cosseno de ômega vezes x, ao quadrado" →
  `cos(omega*x)**2`); escopo de `sqrt` segue a prosódia, transcrito com
  parênteses (few-shot ancora o default).

Intents `calculate` / `calculate_symbolic` / `not_supported` / `not_recognized`;
formato com **todos os campos sempre presentes** (`intents`, `expression`,
`operation`, `variable`, `to`, `reason`).

**Few-shots (~16):**

1. 2 valores simples ("quanto é 10 mais 5?" → `"10 + 5"`)
2. N valores mistos provando ordem falada ("10 mais 5 vezes 2" → `"10 + 5 * 2"`)
3. Decimal com vírgula ("2,5 vezes 4" → `"2.5 * 4"`)
4. Extenso puro ("dez mais cinco" → `"10 + 5"`)
5. Extenso misturado com dígito ("vinte dividido por 4" → `"20 / 4"`)
6. Contra-exemplo de cálculo numérico (saída sem `=` nem resultado)
7. Raiz ("quanto é a raiz quadrada de 144?" → `calculate`, `"sqrt(144)"`)
8. Logaritmo com base ("logaritmo de 100 na base 10" → `"log(100, 10)"`)
9. Potência na cadeia sequencial ("2 elevado a 10 mais 5" → `"2 ** 10 + 5"`)
10. Percentual "de" ("quanto é 10% de 200?" → `"10% * 200"`)
11. Percentual aditivo por extenso ("150 mais 15 por cento" → `"150 + 15%"`)
12. Integral com ômega e "ao quadrado" ("integral de cosseno de ômega vezes x,
    ao quadrado, em relação a x" → `calculate_symbolic`, `operation:
    "integrate"`, `expression: "cos(omega*x)**2"`, `variable: "x"`)
13. Derivada ("derivada de x ao cubo" → `operation: "diff"`, `"x**3"`, `"x"`)
14. **Contra-exemplo simbólico** (par errado/certo na REGRA DE OURO): "derivada
    de x ao cubo" — **ERRADO:** `expression: "3*x**2"` (você derivou — isso é
    calcular); **CERTO:** `expression: "x**3"` com `operation: "diff"`.
15. Gradiente ("gradiente de x ao quadrado vezes y, mais z" →
    `operation: "gradient"`, `"x**2*y + z"`, `variable: "x,y,z"`)
16. `not_recognized` com números de outro domínio ("comprei 3 maçãs por 10
    reais")

Opcional: limite ("limite de 1 sobre x quando x vai pro infinito" →
`operation: "limit"`, `"1/x"`, `variable: "x"`, `to: "oo"`).

**Removido do rascunho original:** o few-shot `not_supported` com
`reason: "percentage"` ("10% de 200") — percentual agora é suportado.
`not_supported` sobrevive para o que ficou fora (§10: equações, média,
integrais definidas etc.).

Config: temperatura **0.1**, parser `json.loads` via
`Graph._extract_structured_output`, aspas retas.

Templates de resposta dos nodes de ação (determinísticos):

- Numérico: `"10 + 5 × 2 = 30 (calculado na ordem em que você disse)"` — ecoar a
  expressão dá transparência e a nota previne estranhamento pela ausência de
  precedência. Divisão por zero / domínio inválido (raiz de negativo, log de
  zero) → templates fixos amigáveis.
- Simbólico: `"∫ cos(ω·x)² dx = x/2 + sin(2·ω·x)/(4·ω)"` (expressão de entrada +
  resultado formatado pelo graph). Sem forma fechada / timeout → templates fixos
  amigáveis ("não consegui resolver simbolicamente…").

## 7. Risco crítico: o merge do `final_response`

Em multi-intent ("soma 10 e 25 e apaga a luz"), o output do `CalculatorGraph`
passa pelo LLM de `main_graph_final_response.md`, que pode "recalcular" o número
aplicando precedência — ou "simplificar" um resultado simbólico — anulando a
garantia da feature pela porta dos fundos. Mitigação dupla:

1. **Primária (determinística):** `CALCULATOR_RESULT_HEADER` em `markers.py` com
   o mesmo bypass do `SHOPPING_LIST_HEADER` — o trecho do resultado (dos **dois**
   nodes de ação, numérico e simbólico) não passa pelo LLM de merge e é
   concatenado depois.
2. **Defesa em profundidade:** regra no `main_graph_final_response.md`:
   "Resultados de cálculo (linhas com `=`): repasse número e expressão EXATAMENTE
   como vieram; NUNCA recalcule, simplifique ou corrija."

## 8. Wiring — checklist

1. `infra/settings.py`: `llm_calculator_graph_chat_model` (default `gemma4:12b`),
   `llm_calculator_graph_chat_temperature: float = 0.1`,
   `llm_calculator_graph_chat_reasoning: bool | None = None`.
2. `infra/ioc.py`: `get_calculator_graph()` com cache em
   `_repo_cache[("graph", "calculator")]` (seguir `get_pet_health_graph()`);
   **novo:** `get_symbolic_math_engine()` (adapter SymPy) injetado no graph via
   `symbolic_math_service`.
3. **Dependência:** `sympy>=1.13,<2` em `src/requirements.txt` — o
   `scripts/setup.sh` já instala a partir dele, nada a mudar lá. **Lazy import**
   dentro do adapter (primeiro uso, cache em módulo): import de ~1–2 s e ~60 MB
   não pode penalizar o startup, os requests não-matemáticos, nem a coleta da
   suíte unitária (porta mockada fica livre de SymPy). Risco baixo: SymPy é
   Python puro (transitiva única: mpmath), sem binários; o único vetor real é o
   `eval` interno do parser, tratado no §4.3.
4. `main_graph.py` + `infra/prompts/main_graph.md` (§5).
5. `infra/prompts/main_graph_final_response.md` + `markers.py` (§7).
6. `.env.example` e lista de env vars do `CLAUDE.md`.

## 9. Estratégia TDD (parecer do `programador-tester`, rodadas 1 e 2)

Ordem de nascimento — cada arquivo vermelho antes da implementação correspondente:

### 9.1 `tests/unit_tests/test_calculator_service.py` (primeiro; domínio puro, sem mocks)

Baterias da rodada 1:

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
  operador pendurado (`"5 +"`); operador desconhecido (`"2 ^ 3"` — `^` não é a
  sintaxe canônica, potência é `**`); texto; notação científica `"1E+999"`;
  `NaN`/`Infinity`; `None`/não-string.
- `TestEvaluateLimits`: >50 operandos; valor com >20 dígitos.

Baterias novas da rodada 2 (mesmo arquivo):

- `TestEvaluateSquareRoot`: `test_sqrt_perfect_square__returns_exact` (144→12);
  `test_sqrt_irrational__quantization_fixed` (raiz de 2);
  `test_sqrt_zero__returns_zero`;
  `test_sqrt_negative__raises_math_domain_error`.
- `TestEvaluateLogarithm`: `test_log10_power_of_ten__returns_exact_integer`
  (log10(1000)=3); `test_ln_of_one__returns_zero`;
  `test_log_base_n__computed_as_ln_ratio` (log₂(8)=3, fórmula `ln(x)/ln(base)`
  fixada); `test_log_of_zero__raises_math_domain_error`;
  `test_log_of_negative__raises_math_domain_error`;
  `test_log_base_one__raises_validation_error`;
  `test_log_base_zero_or_negative__raises_validation_error`.
- `TestEvaluatePercentage` (fixa as **duas semânticas** — decisão de negócio
  central da extensão): `test_percent_of__x_percent_de_y__returns_fraction`
  ("10% * 200"→20); `test_percent_increase__y_mais_x_percent__returns_increased`
  ("150 + 10%"→165); `test_percent_decrease__y_menos_x_percent__returns_decreased`
  ("200 - 25%"→150); `test_percent_of_decimal_value__exact_decimal` (sem float
  no caminho); `test_percent_chained_in_sequence__folds_left_to_right`
  ("100 + 10% + 10%" = 121, não 120 — interação com a regra sequencial);
  `test_percent_negative_base__computes` (política fixada pelo teste).
- `TestEvaluatePower`: `test_power_integer_exponent__exact` (2**10=1024);
  `test_power_negative_exponent__returns_fraction` (2**-1=0.5);
  `test_power_fractional_exponent__quantization_fixed`;
  `test_power_zero_to_zero__policy_fixed` (decidir `ValidationError` vs
  convenção `=1` — o teste documenta a escolha);
  `test_power_exponent_exceeds_cap__raises_validation_error_fast` (9**9**9
  rejeitado por **pré-checagem**, assert do tipo de erro, nunca "computa e
  estoura"); `test_power_in_sequential_chain__no_precedence` ("2 + 3 ** 2" = 25,
  não 11 — estende o teste-documento da ordem sequencial).
- `TestEvaluateExtendedGrammar` (o tokenizador substitui a regex — re-fixar o
  hardening): `test_function_syntax_accepted__sqrt_log` (casos felizes);
  `test_scientific_notation_still_rejected__validation_error` (regressão);
  `test_unknown_function_name__raises_validation_error` (`foo(3)`);
  `test_nested_function_or_symbolic_arg__raises_validation_error` (aninhamento
  não-literal é do caminho simbólico).

### 9.1b `tests/unit_tests/test_symbolic_math_service.py` (novo arquivo; engine mockada onde couber, SymPy real nos asserts de matemática)

**Regra de assert de igualdade simbólica:** nunca `str(a) == str(b)`. Padrão:
`sympy.simplify(result - expected) == 0`; **para integrais, o assert primário é
o round-trip da derivada** — `simplify(diff(result, x) - integrand) == 0` —
que valida a antiderivada a menos de constante sem depender da forma escolhida
pela versão do SymPy. Fallback `expr.equals()` (amostragem numérica) onde
`simplify` não prova. Lembrete: `simplify` retornar não-zero **não prova**
desigualdade.

- `TestIntegrate`:
  `test_integrate_cos_squared__antiderivative_verified_by_derivative`
  (`cos(w*x)**2` — cuidado `Piecewise`, ramo genérico, §4.3);
  `test_integrate_polynomial__exact_form` (x²→x³/3, `simplify(a-b)==0` direto);
  `test_integrate_no_closed_form__raises_no_closed_form_error` (`x**x` devolve
  `Integral` não-avaliado, não exceção — o serviço detecta e mapeia);
  `test_integrate_result_is_zoo_or_nan__raises_math_domain_error`.
- `TestDifferentiate`: `test_derivative_polynomial_plus_trig__symbolic_equality`
  (x³+sin(x) → 3x²+cos(x));
  `test_derivative_with_respect_to_named_symbol__uses_declared_variable`.
- `TestGradient`: `test_gradient_two_variables__returns_ordered_vector`
  (x²y → [2xy, x²]; **ordem do vetor fixada**, §4.3);
  `test_gradient_single_variable__degenerate_returns_derivative`.
- `TestLimit`: `test_limit_sin_x_over_x_at_zero__returns_one`;
  `test_limit_divergent__returns_infinity_mapped_to_friendly_error`.
- `TestSimplify`: `test_simplify_trig_identity__reduces` (sin²+cos²→1).
- `TestTimeout` — **injetar a seam, não a integral patológica**:
  `test_run_with_timeout__slow_fn__raises_calculation_timeout_error`
  (fn=`time.sleep(0.3)` com timeout 0.05 — determinístico);
  `test_evaluate__internal_timeout_raised__maps_to_friendly_error` (patch do
  worker). **Nunca** teste unitário esperando o timeout de produção.
- `TestSecurityHardening` (string vem do LLM = hostil; espelha
  `test_graph_classify_literal_eval_safety.py`):
  `test_dunder_import_string__raises_validation_error`
  (`"__import__('os').system('ls')"`);
  `test_attribute_access_string__raises_validation_error`
  (`"().__class__.__mro__"`, `"x.__class__"`);
  `test_function_outside_whitelist__raises_validation_error` (`Lambda`,
  `factorial`); `test_expression_exceeds_length_cap__raises_validation_error_before_parse`;
  `test_node_count_exceeds_cap__raises_validation_error`;
  `test_huge_numeric_literal_in_symbolic__raises_validation_error`
  (`"10**10**10"` — força `evaluate=False` + walk);
  `test_unknown_free_symbols__allowed` (símbolos livres passam; só função fora
  da whitelist é rejeitada — o teste documenta a distinção).

### 9.2 `tests/unit_tests/test_calculator_graph_classify_intent.py` + `test_calculator_graph_handlers.py`

Padrão `test_pet_health_graph_classify_intent.py` (`patch.object(load_prompt)`,
`llm_chat=MagicMock()`, injeção do JSON):

- `TestClassify`: JSON feliz; JSON malformado → `not_recognized` sem exceção;
  `["not_recognized"]` explícito; resposta com `<think>` (sem mockar o extrator —
  cobre `_remove_thinking_tag` real); expressão que não passa no tokenizador
  (`"10 + banana"`) → resposta amigável sem stack trace;
  **novos:** `test_classify__symbolic_phrase__routes_to_symbolic_node` /
  `test_classify__numeric_phrase__routes_to_calculate_node`;
  `test_classify__unknown_operation_value__falls_back_not_recognized` (LLM
  inventa `"operation": "algebra"`);
  `test_classify__percentage_phrase__routes_to_calculate` (**inversão** do caso
  `not_supported`/`percentage` do rascunho original).
- `TestCalculateNode`: delega ao serviço e formata; `DivisionByZeroError` →
  mensagem amigável pt-BR; `MathDomainError` (raiz de negativo/log de zero) →
  mensagem amigável; **assert de que `llm_chat` não é chamado no node de
  ação**; `Decimal("20")` formatado `"20"`; output prefixado com
  `CALCULATOR_RESULT_HEADER`.
- `TestCalculateSymbolicNode` (novo): delega ao `symbolic_math_service` (engine
  mockada) e formata; **mesmo assert de `llm_chat.assert_not_called()`**;
  `test_symbolic_node__formats_result_deterministically` (assertar fragmentos
  estáveis, nunca a string SymPy completa);
  `test_symbolic_node__validation_error_from_hostile_string__friendly_message_no_stacktrace`;
  `test_symbolic_node__timeout_error__friendly_message`;
  `test_symbolic_output__prefixed_with_calculator_result_header` (bypass §7
  vale para o simbólico).

### 9.3 `tests/unit_tests/test_main_graph_calculator.py`

Padrão `test_main_graph_pet_health.py`: intent `["calculator"]` roteia para
`CalculatorGraph.invoke`; não chama `only_talk`; fallback `not_recognized` →
`only_talk`; um caso com **frase simbólica** roteando para o mesmo node (a
distinção numérico/simbólico é interna ao sub-graph). + teste da factory na IoC
se `test_ioc_graph_cache.py` exigir.

### 9.4 `tests/integration_tests/test_llm_app_service_chat__calculator_graph.py` (por último, Ollama vivo, skip gracioso)

- **B1 — roteamento + extração (~14 frases):** "quanto é 2 mais 3 vezes 4?" →
  output contém "20" (sequencial fim-a-fim); "10 dividido por 4" → "2,5"/"2.5";
  "soma 0,1 com 0,2" → "0,3" (vírgula BR); "quanto é dois mais dois?" (extenso);
  "15 menos 20" (negativo); "100 dividido por 0" (mensagem amigável, sem 500);
  "me diz quanto dá 5 vezes 5 menos 3"; **novas:** "quanto é a raiz quadrada de
  144?" → "12"; "qual o logaritmo de 1000 na base 10?" → "3"; "quanto é 10 por
  cento de 200?" → "20"; "150 mais 10 por cento" → "165"; "quanto é 2 elevado a
  10?" → "1024"; "qual a derivada de x ao cubo?" → contém "3" e "x" (fragmentos,
  nunca a string SymPy inteira); "integral de x ao quadrado em relação a x" →
  contém "x³/3"/"x**3/3" (começar com integral polinomial; a de `cos(w*x)**2`
  ditada por voz é frágil como gate de aceite — caso extra tolerado em
  `AMBIGUOUS_EXCLUDED` se flakar).
- **B2 — anti-falso-positivo (~7 frases, nunca `calculator`):** "você é bom de
  matemática?"; "adicione 2 litros de leite na lista" (→ `shopping_list`);
  "quantas vacinas o Caçolin tomou?"; "conta uma história"; **novas:** "me
  explica o que é uma integral" (→ `only_talking`); "aumenta a temperatura em 2
  graus" (→ `smart_home_climate`); "o preço da gasolina subiu 10 por cento"
  (→ `only_talking` — o trap principal da extensão de percentual).
- Aceite no padrão do repo: 100% por bateria, até 2 frases flaky movidas para
  `AMBIGUOUS_EXCLUDED` documentada. Sem fixture de dados.

Convenções: métodos `test_<cenário>__<resultado>`; helpers `_make_graph()`,
`_user()`; `pytest.importorskip("langgraph")` nos testes de graph.

### 9.5 Armadilhas de SymPy registradas (parecer do `programador-tester`)

1. **Formas equivalentes não-idênticas** — `x/2 + sin(2wx)/(4w)` vs
   `x/2 + sin(wx)cos(wx)/(2w)` são o mesmo resultado; asserts por string ou
   `==` estrutural quebram entre versões. Regra: integral → round-trip da
   derivada; demais → `simplify(a-b)==0` com fallback `.equals()`.
2. **`Piecewise` paramétrico** — decidido em §4.3 (ramo genérico `True`); sem a
   decisão, o teste da integral do enunciado falharia.
3. **`zoo`/`nan`/`oo` em vez de exceção** — pós-checagem obrigatória (§4.3).
4. **Ordem de termos no `str()`** muda entre versões — asserts por fragmento.
5. **Import de ~1–2 s** — lazy import no adapter (§8); primeiro
   `simplify`/`integrate` também é mais lento (cache do SymPy frio).
6. **Timeout é decisão de design, não só de teste** — mecanismo de produção
   ratificado pelo `arquiteto` em §4.3 (processo + `join(timeout)` +
   `terminate()`, worker longevo lazy); a seam injetável cobre os testes.
7. **Float contamina exatidão** — preferir racionais (§4.3); teste fixa o
   comportamento com float na entrada.
8. **`parse_expr` não é sandbox** — contrato `evaluate=False` + walk garantido
   pelos testes de `TestSecurityHardening`.

## 10. Fora de escopo v1 (alternativas descartadas / extensões futuras)

- ~~Porcentagem, potência, raiz~~ — **promovidas a escopo pela extensão de
  2026-07-10** (percentual/potência no motor Decimal sequencial; raiz/log com
  argumentos literais no Decimal, casos simbólicos no caminho SymPy).
- **Continuam `not_supported` com `reason`:** equações ("resolva x + 2 = 5"),
  integrais **definidas** (com limites de integração ditados), matrizes,
  média/estatística, parênteses livres ditados no modo numérico sequencial.
- **Problemas em linguagem natural** ("tinha 150, gastei 30, quanto sobrou?") →
  `only_talking`, com exemplo negativo no prompt (zona cinzenta grande:
  "gastei metade" exige raciocínio).
- **Follow-up multi-turn** ("e dividido por 2?", "agora deriva de novo") —
  exigiria FlowService/focused result; anotado como extensão futura.
- **Validator fluente dedicado** — descartado (sem entidade persistida; a
  validação estrutural vive nos próprios serviços). Se o formato evoluir para
  objeto, revisitar com `CalculationExpressionValidator` (lembrando o
  `.validate()` final obrigatório).
- **Delegar tudo (inclusive numérico) ao SymPy** — descartado (rodada 2): o
  motor Decimal garante `0.1+0.2 == 0.3` exato, a semântica de ordem falada e o
  caminho rápido sem processo filho/timeout no caso comum.
- **Assumptions em símbolos (`Symbol('w', nonzero=True)`)** — descartado a favor
  do ramo genérico do `Piecewise` (§4.3).

## 11. Sequência de implementação

1. Baterias da rodada 1 + rodada 2 do serviço numérico (§9.1, vermelhas) →
   `calculator_service.py` (tokenizador fechado, `+ - * / **`, `%`,
   `sqrt/ln/log10/log`) + `DivisionByZeroError` + `MathDomainError`.
2. Testes do serviço simbólico (§9.1b, vermelhos) → `SymbolicMathEngine` (ABC),
   `symbolic_math_service.py`, adapter `SympySymbolicMathEngine`
   (parse restrito + timeout por processo) + `NoClosedFormError` +
   `CalculationTimeoutError` + dependência `sympy` no `requirements.txt`.
3. Testes do graph (§9.2, vermelhos) → `CalculatorGraph` (nodes `calculate` e
   `calculate_symbolic`) + `calculator_graph.md` + `CALCULATOR_RESULT_HEADER`.
4. Testes de roteamento (§9.3, vermelhos) → wiring `main_graph.py`, `ioc.py`
   (incl. `get_symbolic_math_engine()`), `settings.py`, prompts do MainGraph e
   do final_response.
5. `.env.example` + `CLAUDE.md`.
6. Bateria de integração (§9.4) com Ollama vivo; ajuste fino de prompt se
   necessário.
7. Mover este plano para `doing/` ao iniciar e `done/` ao concluir, preenchendo
   o cabeçalho.
