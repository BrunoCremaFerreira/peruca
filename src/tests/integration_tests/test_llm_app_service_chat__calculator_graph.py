"""
Calculator — LLM integration batteries (Fase 4, plan §9.4). Requires a live
Ollama; every test skips gracefully when the configured provider is offline.

These validate the full chat pipeline against the real model:
  - B1 routing + extraction: math requests route to ["calculator"] and the
    deterministic engine (sequential Decimal folding / SymPy) produces the
    expected result end-to-end. Asserts use numeric/symbolic FRAGMENTS, never
    the whole rendered string (SymPy term order varies between versions).
    The flagship case "2 mais 3 vezes 4" must yield 20 (sequential,
    left-to-right), never 14 (operator precedence).
  - B2 anti-false-positive: sentences that merely contain numbers/math words
    (shopping quantities, temperature deltas, price-percentage chatter,
    concept questions) must NEVER route to ["calculator"].

Acceptance: 100% per battery, with at most 2 flaky phrases per battery allowed
to be moved to the AMBIGUOUS_EXCLUDED list (documented), per the plan's process.

No data fixture: the calculator needs no persisted entities (plan §9.4).
"""

import pytest

from application.appservices.view_models import ChatRequest
from tests.integration_tests.conftest import INTEGRATION_ENV, _probe_http


pytestmark = pytest.mark.integration


# ----------------------------------------------------------------------- #
# Graceful skip when the LLM provider is unreachable (mirrors the
# home_assistant_available / music_assistant_available probe in conftest.py:
# any HTTP answer means the backend is up; connection failure -> skip).
# ----------------------------------------------------------------------- #
@pytest.fixture
def ollama_available(integration_env):
    url = INTEGRATION_ENV["LLM_PROVIDER_URL"]
    if not _probe_http(url):
        pytest.skip(f"Ollama não acessível em {url}")


# ----------------------------------------------------------------------- #
# AMBIGUOUS_EXCLUDED — phrases removed from the acceptance gate because the
# classifier answer is genuinely ambiguous/flaky (max 2 per battery, each one
# documented with the reason). Kept here so the exclusion is visible in review.
# ----------------------------------------------------------------------- #
AMBIGUOUS_EXCLUDED: list[str] = []


def _chat(llm_app_service, message: str) -> dict:
    return llm_app_service.chat(
        ChatRequest(external_user_id="1000", message=message)
    )


# ----------------------------------------------------------------------- #
# B1 — routing + extraction: should route to calculator and the output must
# contain the expected result fragments.
#
# Each case: (message, required_all, required_any, forbidden)
#   required_all — every fragment must be present in the output
#   required_any — at least one fragment must be present (accepted variants)
#   forbidden    — fragments that must NOT appear (e.g. the precedence result)
# ----------------------------------------------------------------------- #
B1_CASES = [
    pytest.param(
        "quanto é 2 mais 3 vezes 4?",
        (),
        ("= 20",),
        ("= 14",),  # sequential (2+3)*4=20, never precedence 2+(3*4)=14
        id="sequential-2-plus-3-times-4-is-20",
    ),
    pytest.param(
        "10 dividido por 4",
        (),
        ("= 2,5", "= 2.5"),
        (),
        id="division-10-by-4-is-2.5",
    ),
    pytest.param(
        "soma 0,1 com 0,2",
        (),
        ("= 0,3", "= 0.3"),
        (),
        id="decimal-comma-0.1-plus-0.2-is-0.3",
    ),
    pytest.param(
        "quanto é dois mais dois?",
        (),
        ("= 4",),
        (),
        id="spelled-out-two-plus-two-is-4",
    ),
    pytest.param(
        "15 menos 20",
        (),
        ("= -5",),
        (),
        id="negative-result-15-minus-20-is-minus-5",
    ),
    pytest.param(
        "100 dividido por 0",
        (),
        ("dividir por zero",),  # friendly message, no exception/500
        (),
        id="division-by-zero-friendly-message",
    ),
    pytest.param(
        "me diz quanto dá 5 vezes 5 menos 3",
        (),
        ("= 22",),
        (),
        id="sequential-5-times-5-minus-3-is-22",
    ),
    pytest.param(
        "quanto é a raiz quadrada de 144?",
        (),
        ("= 12",),
        (),
        id="sqrt-144-is-12",
    ),
    pytest.param(
        "qual o logaritmo de 1000 na base 10?",
        (),
        ("= 3",),
        (),
        id="log-1000-base-10-is-3",
    ),
    pytest.param(
        "quanto é 10 por cento de 200?",
        (),
        ("= 20",),
        (),
        id="percent-10-of-200-is-20",
    ),
    pytest.param(
        "150 mais 10 por cento",
        (),
        ("= 165",),
        (),
        id="percent-150-plus-10-percent-is-165",
    ),
    pytest.param(
        "quanto é 2 elevado a 10?",
        (),
        ("= 1024",),
        (),
        id="power-2-to-the-10-is-1024",
    ),
    pytest.param(
        "qual a derivada de x ao cubo?",
        ("3", "x"),  # fragments only — never the full SymPy string
        (),
        (),
        id="derivative-x-cubed-contains-3-and-x",
    ),
    pytest.param(
        "integral de x ao quadrado em relação a x",
        (),
        ("x³/3", "x**3/3", "x^3/3"),  # equivalent renderings of x**3/3
        (),
        id="integral-x-squared-is-x-cubed-over-3",
    ),
]


@pytest.mark.parametrize("message,required_all,required_any,forbidden", B1_CASES)
def test_b1_math_request__routes_to_calculator_with_expected_result(
    message,
    required_all,
    required_any,
    forbidden,
    ollama_available,
    llm_app_service,
    integration_user,
):
    response = _chat(llm_app_service, message)

    intents = response.get("intents") or []
    output = response.get("output")

    assert "calculator" in intents, response
    assert isinstance(output, str) and len(output.strip()) > 0, response
    for fragment in required_all:
        assert fragment in output, response
    if required_any:
        assert any(fragment in output for fragment in required_any), response
    for fragment in forbidden:
        assert fragment not in output, response


# ----------------------------------------------------------------------- #
# B2 — anti-false-positive: intents must NEVER contain "calculator". Where the
# plan pins the expected route, it is asserted as well.
#
# Each case: (message, expected_intent) — expected_intent None means only the
# not-calculator guard applies.
# ----------------------------------------------------------------------- #
B2_CASES = [
    pytest.param(
        "você é bom de matemática?",
        None,
        id="math-opinion-question",
    ),
    pytest.param(
        "adicione 2 litros de leite na lista",
        "shopping_list",
        id="shopping-quantity-goes-to-shopping-list",
    ),
    pytest.param(
        "quantas vacinas o Caçolin tomou?",
        None,
        id="pet-count-question",
    ),
    pytest.param(
        "conta uma história",
        None,
        id="tell-a-story",
    ),
    pytest.param(
        "me explica o que é uma integral",
        "only_talking",
        id="concept-question-goes-to-only-talking",
    ),
    pytest.param(
        "aumenta a temperatura em 2 graus",
        "smart_home_climate",
        id="temperature-delta-goes-to-climate",
    ),
    pytest.param(
        "o preço da gasolina subiu 10 por cento",
        "only_talking",
        id="price-percentage-chatter-goes-to-only-talking",
    ),
]


@pytest.mark.parametrize("message,expected_intent", B2_CASES)
def test_b2_non_math_message__never_routes_to_calculator(
    message,
    expected_intent,
    ollama_available,
    llm_app_service,
    integration_user,
):
    response = _chat(llm_app_service, message)

    intents = response.get("intents") or []

    assert "calculator" not in intents, response
    if expected_intent is not None:
        assert expected_intent in intents, response
