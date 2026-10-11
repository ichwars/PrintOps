"""Exercise malicious and legitimate inputs through shipped dependency boundaries."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import sys
from collections import OrderedDict
from http.client import HTTPResponse as StdlibResponse

import jwt
import pytest
from multidict import CIMultiDict
from urllib3.exceptions import ProtocolError
from urllib3.response import HTTPResponse
from virtualenv.create.pyenv_cfg import PyEnvCfg

SECRET = "dependency-regression-key-" + "x" * 64


def _signed_payload(payload: bytes) -> str:
    def encode(value: bytes) -> bytes:
        return base64.urlsafe_b64encode(value).rstrip(b"=")

    signing_input = encode(b'{"alg":"HS256","typ":"JWT"}') + b"." + encode(payload)
    signature = hmac.new(SECRET.encode(), signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + encode(signature)).decode()


def test_deep_jwt_payload_raises_the_authentication_error_family():
    token = _signed_payload(b'{"nested":' + b"[" * 10000 + b"0" + b"]" * 10000 + b"}")
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(token, SECRET, algorithms=["HS256"])


@pytest.mark.parametrize("claim", ["exp", "nbf", "iat"])
@pytest.mark.parametrize("value", [None, [], {}])
def test_invalid_time_claims_raise_the_authentication_error_family(claim, value):
    token = jwt.encode({"sub": "42", claim: value}, SECRET, algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(token, SECRET, algorithms=["HS256"])


def test_non_alphabet_signature_junk_is_rejected():
    token = jwt.encode({"sub": "42"}, SECRET, algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(token + "!!!!", SECRET, algorithms=["HS256"])


def test_signed_tokens_and_provider_signature_padding_remain_valid():
    token = jwt.encode({"sub": "42", "exp": 4102444800}, SECRET, algorithm="HS256")
    for candidate in (token, token + "="):
        assert jwt.decode(candidate, SECRET, algorithms=["HS256"])["sub"] == "42"


def _chunked_response(chunk_header: bytes) -> HTTPResponse:
    class Socket:
        def makefile(self, *_args, **_kwargs):
            return io.BytesIO(
                b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + chunk_header + b"\r\nabc\r\n0\r\n\r\n"
            )

    response = StdlibResponse(Socket())
    response.begin()
    return HTTPResponse(body=response, headers=dict(response.headers.items()), preload_content=False)


def test_chunk_size_extension_has_a_bounded_read():
    response = _chunked_response(b"3;" + b"x" * 100000)
    with pytest.raises(ProtocolError):
        list(response.read_chunked())


def test_normal_chunk_extensions_remain_supported():
    response = _chunked_response(b"3;extension=value")
    assert b"".join(response.read_chunked()) == b"abc"


@pytest.mark.parametrize("boundary", ["\n", "\r", "\u2028", "\u0085"])
def test_virtualenv_prompt_cannot_replace_interpreter_home(tmp_path, boundary):
    path = tmp_path / "pyvenv.cfg"
    content = OrderedDict(home="/trusted/python", prompt=f"label{boundary}home = /untrusted/python")
    PyEnvCfg(content, path).write()
    homes = [line for line in path.read_text().splitlines() if line.startswith("home = ")]
    assert homes == ["home = /trusted/python"]


def test_virtualenv_normal_prompt_preserves_spaces(tmp_path):
    path = tmp_path / "pyvenv.cfg"
    PyEnvCfg(OrderedDict(home="/trusted/python", prompt="PrintOps development"), path).write()
    assert 'prompt = "PrintOps development"' in path.read_text()


@pytest.mark.parametrize("operation", ["reflected_union", "subtraction"])
def test_multidict_items_operators_release_operand_references(operation):
    mapping = CIMultiDict(seed="value")
    sentinel = object()
    operand = [(f"header-{index}", sentinel) for index in range(100)]
    before = sys.getrefcount(sentinel)
    if operation == "reflected_union":
        result = operand | mapping.items()
        assert len(result) == 101
    else:
        result = mapping.items() - operand
        assert result == {("seed", "value")}
    del result
    assert sys.getrefcount(sentinel) == before
