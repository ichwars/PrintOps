"""Return validation errors even if rejected input is not a JSON number."""

import math

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


async def request_validation_error(_request, error: RequestValidationError) -> JSONResponse:
    detail = _json_safe(jsonable_encoder(error.errors()))
    return JSONResponse(status_code=422, content={"detail": detail})
