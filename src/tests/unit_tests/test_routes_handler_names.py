"""
Route handler naming unit tests.

Guards against duplicate endpoint function names in routes.py. Two handlers
sharing the same Python name (e.g. two `def user_get`) shadow each other at
module level: only the last definition survives as an attribute, which is
fragile and confusing even though FastAPI still registers both paths via the
decorator. Handler names must be unique and free of typos.

These tests are expected to FAIL until the duplicate/typo'd handler names in
routes.py are renamed to unique, correct identifiers.
"""

from fastapi.routing import APIRoute

from app import app


def _api_routes():
    return [route for route in app.router.routes if isinstance(route, APIRoute)]


class TestRouteHandlerNames:
    def test_endpoint_names__are_unique(self):
        names = [route.endpoint.__name__ for route in _api_routes()]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        assert duplicates == [], f"duplicate handler names: {duplicates}"

    def test_no_handler_name_contains_typo_ckeck(self):
        names = [route.endpoint.__name__ for route in _api_routes()]
        assert not any("ckeck" in name for name in names)

    def test_user_routes__have_distinct_handlers(self):
        by_path = {
            route.path: route.endpoint.__name__
            for route in _api_routes()
            if route.path in {"/user/{id}", "/user/external-id/{external_id}"}
        }
        assert by_path["/user/{id}"] != by_path["/user/external-id/{external_id}"]

    def test_shopping_list_check_routes__have_distinct_handlers(self):
        by_path = {
            route.path: route.endpoint.__name__
            for route in _api_routes()
            if route.path
            in {"/shopping-list/{id}/check", "/shopping-list/{id}/uncheck"}
        }
        assert (
            by_path["/shopping-list/{id}/check"]
            != by_path["/shopping-list/{id}/uncheck"]
        )
