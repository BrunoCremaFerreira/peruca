"""
VehicleReceiptExtractor — single synchronous vision call that gates ("is this a
vehicle-maintenance document?") and extracts the structured receipt data in one
shot (plan §3.2).

The LLM only transcribes what is printed on the document; Python owns every
validation: strict ISO dates (never tokens, never the future), odometer
coercion + bounds, services capped and joined, and `sanitize_for_prompt` over
the free-text fields (§3.7 — OCR'd text is DATA, never instruction). Malformed
output degrades to an "unreadable" rejection, never to a crash. The domain
never sees this type: the boundary stays `MaintenanceRecordAdd`.
"""

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional

from langchain_core.messages import HumanMessage

from application.appservices.prompt_sanitizer import sanitize_for_prompt
from application.graphs.graph import Graph
from domain.entities import GraphInvokeRequest
from domain.services.clock import max_civil_date_on_earth


logger = logging.getLogger(__name__)

_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_ODOMETER_KM = 2_000_000
_MAX_SERVICES = 10
_MAX_VEHICLE_TERM_CHARS = 100
_MAX_DESCRIPTION_CHARS = 400

_REJECT_REASONS = {"not_a_document", "not_vehicle_maintenance", "unreadable"}
_UNREADABLE = "unreadable"


@dataclass(frozen=True)
class ReceiptExtraction:
    """Validated outcome of the gate + extraction vision call (plan §3.2)."""

    is_maintenance_document: bool
    reject_reason: str  # "" | "not_a_document" | "not_vehicle_maintenance" | "unreadable"
    vehicle_term: Optional[str]
    performed_at: Optional[date]
    odometer_km: Optional[int]
    description: Optional[str]


class VehicleReceiptExtractor(Graph):
    """
    Application-layer component (not a StateGraph): it subclasses Graph only to
    reuse the prompt-loading and structured-output helpers, plus
    `_build_human_content` for the multimodal payload. One `llm.invoke` per
    extraction — synchronous on purpose (no `asyncio.run()` in graph nodes).
    """

    def __init__(
        self,
        llm_vision,
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ):
        super().__init__(provider, strip_think_directive)
        self.llm_vision = llm_vision
        # The prompt is static text (no template variables): the images travel
        # as separate content blocks, so the textual prompt never carries base64.
        self.extraction_prompt = self.load_prompt(
            "vehicle_maintenance_receipt_extract.md"
        )

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        """Graph-port adapter: extract from the request's attached images."""
        return asdict(self.extract(invoke_request.images))

    def extract(self, images: list[str]) -> ReceiptExtraction:
        content = self._build_human_content(self.extraction_prompt, images)
        response = self.llm_vision.invoke([HumanMessage(content=content)])
        parsed = self._parse_payload(response.content)
        if parsed is None:
            return self._rejection(_UNREADABLE)

        if parsed.get("is_maintenance_document") is not True:
            return self._rejection(self._coerce_reason(parsed.get("reject_reason")))

        vehicle_term = sanitize_for_prompt(
            parsed.get("vehicle_term") or "", _MAX_VEHICLE_TERM_CHARS
        )
        performed_at = self._coerce_date(parsed.get("date_value"))
        odometer_km = self._coerce_km(parsed.get("odometer_km"))
        description = self._build_description(parsed.get("services"))

        # Inconsistent gate: "true" with nothing extracted is garbage output —
        # a first-class "unreadable" rejection (plan §3.2).
        if not vehicle_term and performed_at is None and odometer_km is None and not description:
            return self._rejection(_UNREADABLE)

        return ReceiptExtraction(
            is_maintenance_document=True,
            reject_reason="",
            vehicle_term=vehicle_term,
            performed_at=performed_at,
            odometer_km=odometer_km,
            description=description,
        )

    # ------------------------------------------------------------------ #
    # Parsing / normalization — Python is the authority, never the LLM
    # ------------------------------------------------------------------ #
    def _parse_payload(self, raw) -> Optional[dict]:
        extracted = self._extract_structured_output(raw)
        if not extracted:
            return None
        try:
            loaded = json.loads(extracted)
        except (json.JSONDecodeError, ValueError):
            return None
        return loaded if isinstance(loaded, dict) else None

    @staticmethod
    def _rejection(reason: str) -> ReceiptExtraction:
        return ReceiptExtraction(
            is_maintenance_document=False,
            reject_reason=reason,
            vehicle_term=None,
            performed_at=None,
            odometer_km=None,
            description=None,
        )

    @staticmethod
    def _coerce_reason(value) -> str:
        reason = str(value or "").strip()
        return reason if reason in _REJECT_REASONS else _UNREADABLE

    @staticmethod
    def _coerce_date(value) -> Optional[date]:
        """Explicit YYYY-MM-DD only — a relative token or a future date is
        discarded as missing, never resolved (the LLM must transcribe)."""
        text = str(value or "").strip()
        if not _ISO_DATE_PATTERN.match(text):
            return None
        try:
            parsed = date.fromisoformat(text)
        except ValueError:
            return None
        if parsed > max_civil_date_on_earth():
            return None
        return parsed

    @staticmethod
    def _coerce_km(value) -> Optional[int]:
        """Coerce the transcribed odometer: thousands separators and a "km"
        suffix are tolerated; 0 means absent; out-of-bounds is discarded."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            km = int(value)
        elif isinstance(value, str):
            digits = value.lower().replace("km", "").replace(".", "")
            digits = digits.replace(",", "").strip()
            if not digits.isdigit():
                return None
            km = int(digits)
        else:
            return None
        return km if 0 < km <= _MAX_ODOMETER_KM else None

    @staticmethod
    def _build_description(services) -> Optional[str]:
        if not isinstance(services, list):
            return None
        items = [str(s).strip() for s in services[:_MAX_SERVICES] if str(s).strip()]
        if not items:
            return None
        return sanitize_for_prompt(", ".join(items), _MAX_DESCRIPTION_CHARS)
