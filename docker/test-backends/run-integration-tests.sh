#!/usr/bin/env bash
#
# One-shot runner for the Peruca integration suite against local backends.
#
#   1. brings up redis + home assistant + music assistant (docker compose)
#   2. bootstraps Home Assistant (onboarding, entities, token) idempotently
#   3. sources the generated .env.test so pytest sees the endpoints + token
#   4. runs the integration tests (Ollama still comes from unix.rtx-server)
#
# Any extra arguments are forwarded to pytest, e.g.:
#   ./run-integration-tests.sh -k lights
#   ./run-integration-tests.sh tests/integration_tests/test_llm_app_service_chat__music_graph.py
#
# Run it from inside the project virtualenv (it needs aiohttp/websockets/pytest).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE=(docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml")

echo "==> Starting test backends (redis, home assistant, music assistant)..."
"${COMPOSE[@]}" up -d

echo "==> Bootstrapping Home Assistant (onboarding, entities, token)..."
python "$SCRIPT_DIR/bootstrap_ha.py"

echo "==> Loading test environment from .env.test..."
set -a
# shellcheck disable=SC1091
source "$SCRIPT_DIR/.env.test"
set +a

echo "==> Running integration tests..."
cd "$PROJECT_ROOT/src"
if [ "$#" -gt 0 ]; then
  python -m pytest "$@"
else
  python -m pytest tests/integration_tests/ -v
fi
