from flask import Blueprint, request
from infra.ioc import get_llm_app_service


# =====================================
# Services Instances
# =====================================

llm_app_service = get_llm_app_service()


# =====================================
# LLM Routes
# =====================================

llm_bp = Blueprint("llm", __name__)


@llm_bp.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    return llm_app_service.chat(data.get("message", ""))
