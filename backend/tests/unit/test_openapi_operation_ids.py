from collections import Counter

from fastapi.openapi.utils import get_openapi

from backend.app.main import app


def test_openapi_operation_ids_are_unique():
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    operations = Counter(
        method["operationId"]
        for path in schema["paths"].values()
        for method in path.values()
        if isinstance(method, dict) and "operationId" in method
    )
    assert not {operation: count for operation, count in operations.items() if count > 1}
