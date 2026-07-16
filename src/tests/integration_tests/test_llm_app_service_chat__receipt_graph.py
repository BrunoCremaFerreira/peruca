"""
Maintenance-from-receipt-photo — LLM integration batteries (plan §4.2).

Requires a live Ollama serving a multimodal gemma4 at LLM_PROVIDER_URL; the
whole file skips gracefully when it is unreachable (same probe pattern as the
Home Assistant / Music Assistant batteries).

The fixtures are deterministic synthetic receipts (Pillow-rendered, committed
under tests/integration_tests/data/): a full one and a no-odometer variant.
The negative gate case reuses the yellow-square IMAGE_TEST_PNG from the image
batteries. Assertions are intentionally LOOSE — routing, pending-flow state and
the persisted record's structured fields — never exact equality on any
LLM-generated string (OCR transcription is nondeterministic).
"""

import asyncio
import base64
from pathlib import Path

import pytest

from application.appservices.view_models import ChatRequest
from domain.commands import VehicleAdd
from infra.ioc import (
    get_maintenance_record_repository,
    get_user_app_service,
    get_vehicle_app_service,
    get_vehicle_repository,
)
from tests.integration_tests.conftest import INTEGRATION_ENV, _probe_http


pytestmark = pytest.mark.integration


_DATA_DIR = Path(__file__).parent / "data"
RECEIPT_PNG = _DATA_DIR / "receipt_synthetic.png"
RECEIPT_NO_KM_PNG = _DATA_DIR / "receipt_synthetic_no_km.png"

# Same yellow-square PNG used by test_llm_app_service_chat__images_graph.py —
# a real, valid image that is very much NOT a maintenance document.
IMAGE_TEST_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAW0lEQVR42u3ZQQ0AIAwAsYngjbApnhwkoAIySJMz0PfFzHq6AAAAAAAAAAAAAAC4Blg1jgYAAAAAAAAAAAAAAAAAAAAAAAAAAAAA0A/g0AAAAAAAAAAAAAB8A9gG7zFLt4pzJAAAAABJRU5ErkJggg=="  # noqa: E501


def _data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _pending(llm_app_service, user_id: str):
    """Read the pending flow through the SAME service instance under test.

    Building a fresh MaintenanceFlowService via the IoC here would not see the
    armed flow: ioc._get_settings() clears _repo_cache whenever the os.environ
    snapshot differs from the one at construction time, handing back a brand-new
    (empty) in-memory ContextRepository. The state that matters is the one the
    app service itself will consult on the user's next turn.
    """
    return _run(llm_app_service.maintenance_flow_service.get_pending(user_id))


def _records(vehicle_id: str):
    return get_maintenance_record_repository().get_all_by_vehicle_id(vehicle_id)


@pytest.fixture
def ollama_available(integration_env):
    url = INTEGRATION_ENV["LLM_PROVIDER_URL"]
    if not _probe_http(url):
        pytest.skip(f"Ollama não acessível em {url}")


@pytest.fixture
def receipt_setup(ollama_available, integration_user, integration_db_path):
    """Register the Outlander for the integration user; returns (user, vehicle)."""
    user = get_user_app_service().get_by_external_id(
        external_id=integration_user.external_id
    )
    get_vehicle_app_service().add(
        VehicleAdd(
            user_id=user.id,
            name="Mitsubishi Outlander",
            brand="Mitsubishi",
            model="Outlander",
            year=2018,
        )
    )
    vehicle = get_vehicle_repository().get_all_by_user_id(user.id)[0]
    return user, vehicle


# ----------------------------------------------------------------------- #
# Scenario 1 — full receipt + "registra essa nota": confirmation armed,
# nothing persisted; then "sim" persists the record for the right vehicle.
# ----------------------------------------------------------------------- #
def test_full_receipt__register_then_confirm__persists_record(
    llm_app_service, receipt_setup
):
    user, vehicle = receipt_setup

    response = llm_app_service.chat(
        ChatRequest(
            external_user_id="1000",
            message="Peruca, registra essa nota.",
            images=[_data_uri(RECEIPT_PNG)],
        )
    )

    assert "vehicle_maintenance" in response.get("intents"), response
    assert response.get("output")

    # The mandatory confirmation turn is armed; nothing persisted yet (§3.5).
    pending = _pending(llm_app_service, user.id)
    assert pending is not None, response
    assert pending.operation == "register_receipt_confirm", (
        pending.operation,
        pending.slots,
        response,
    )
    assert pending.slots.get("vehicle_id") == vehicle.id, pending.slots
    assert _records(vehicle.id) == [], "nothing may persist before the 'sim'"

    confirm = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message="sim")
    )
    assert confirm.get("output")

    records = _records(vehicle.id)
    assert len(records) == 1, (confirm, [r.description for r in records])
    record = records[0]
    assert record.vehicle_id == vehicle.id
    # OCR-transcribed description: assert presence, never exact wording.
    assert record.description
    assert _pending(llm_app_service, user.id) is None, "the flow must be consumed by the 'sim'"


# ----------------------------------------------------------------------- #
# Scenario 2 — non-document image + explicit register request: the vision
# gate refuses; zero records, no pending flow.
# ----------------------------------------------------------------------- #
def test_non_document_image__register_request__gate_refuses(
    llm_app_service, receipt_setup
):
    user, vehicle = receipt_setup

    response = llm_app_service.chat(
        ChatRequest(
            external_user_id="1000",
            message="Registra essa manutenção.",
            images=[IMAGE_TEST_PNG],
        )
    )

    # Stage 1 (routing) fires on the textual intent; stage 2 (vision gate)
    # must refuse the yellow square without arming or persisting anything.
    assert "vehicle_maintenance" in response.get("intents"), response
    assert response.get("output")
    assert _records(vehicle.id) == [], response
    assert _pending(llm_app_service, user.id) is None, response


# ----------------------------------------------------------------------- #
# Scenario 3 — any photo + small talk: routes to only_talking, the
# maintenance graph is never involved.
# ----------------------------------------------------------------------- #
def test_photo_with_small_talk__routes_only_talking(
    llm_app_service, receipt_setup
):
    user, vehicle = receipt_setup

    response = llm_app_service.chat(
        ChatRequest(
            external_user_id="1000",
            message="Olha que legal!",
            images=[IMAGE_TEST_PNG],
        )
    )

    assert "only_talking" in response.get("intents"), response
    assert "vehicle_maintenance" not in response.get("intents"), response
    assert response.get("output")
    assert _records(vehicle.id) == []
    assert _pending(llm_app_service, user.id) is None


# ----------------------------------------------------------------------- #
# Scenario 4 (optional in §4.2) — receipt without the KM line: the flow asks
# for the odometer; a numeric reply completes up to the confirmation turn.
# ----------------------------------------------------------------------- #
def test_receipt_without_km__flow_asks_km_then_arms_confirmation(
    llm_app_service, receipt_setup
):
    user, vehicle = receipt_setup

    response = llm_app_service.chat(
        ChatRequest(
            external_user_id="1000",
            message="Peruca, registra essa nota.",
            images=[_data_uri(RECEIPT_NO_KM_PNG)],
        )
    )

    assert "vehicle_maintenance" in response.get("intents"), response
    assert response.get("output")

    pending = _pending(llm_app_service, user.id)
    assert pending is not None, response
    assert pending.operation == "register_receipt", (
        pending.operation,
        pending.slots,
        response,
    )
    assert pending.missing_slots == ["km"], (pending.missing_slots, pending.slots)
    assert _records(vehicle.id) == []

    reply = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message="100232")
    )
    assert reply.get("output")

    pending = _pending(llm_app_service, user.id)
    assert pending is not None, reply
    assert pending.operation == "register_receipt_confirm", (
        pending.operation,
        pending.slots,
        reply,
    )
    assert pending.slots.get("odometer_km") == 100232, pending.slots
    # Still nothing persisted: the receipt path never skips the confirmation.
    assert _records(vehicle.id) == []
