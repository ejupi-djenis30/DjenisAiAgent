"""Contract tests for the local-only reasoning backend.

Every transport boundary is replaced with an in-process test double. The suite
must never contact, provision, or download a model.
"""

from __future__ import annotations

import base64
import json
import socket
from io import BytesIO
from threading import Event
from types import SimpleNamespace
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request

import pytest
from PIL import Image

import src.reasoning.local_llm as local_llm
from src.reasoning.local_llm import (
    LocalFunctionCall,
    LocalLLMRequestError,
    ReasoningFailure,
)


@pytest.fixture(autouse=True)
def deterministic_local_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test on an explicit local endpoint and deterministic model."""

    monkeypatch.setattr(local_llm.config, "local_llm_backend", "ollama")
    monkeypatch.setattr(local_llm.config, "local_llm_endpoint", "http://127.0.0.1:11434")
    monkeypatch.setattr(local_llm.config, "local_llm_model", "qwen3-vl:8b")
    monkeypatch.setattr(local_llm.config, "local_llm_expected_digest", "")
    monkeypatch.setattr(local_llm.config, "local_llm_context_tokens", 65_536)
    monkeypatch.setattr(local_llm.config, "local_llm_vision_enabled", True)
    monkeypatch.setattr(local_llm.config, "local_llm_keep_alive", "10m")
    monkeypatch.setattr(local_llm.config, "local_llm_seed", 0)
    monkeypatch.setattr(local_llm.config, "local_llm_response_max_bytes", 1_048_576)
    monkeypatch.setattr(local_llm.config, "local_llm_image_max_bytes", 5 * 1024 * 1024)
    monkeypatch.setattr(local_llm.config, "local_llm_vision_max_dimension", 1600)
    monkeypatch.setattr(local_llm.config, "local_llm_vision_quality", 80)
    monkeypatch.setattr(local_llm.config, "runtime_mode", "windows")
    monkeypatch.setattr(local_llm.config, "api_timeout", 30)
    monkeypatch.setattr(local_llm.config, "api_max_retries", 3)
    monkeypatch.setattr(local_llm.config, "api_retry_delay", 0.01)
    monkeypatch.setattr(local_llm.config, "tool_argument_max_chars", 16_384)


def _tool(query: str, limit: int = 10) -> str:
    """Search a local index.

    Args:
        query: Exact search query.
        limit: Maximum result count.
    """

    return f"{query}:{limit}"


def _ollama_response(
    *,
    name: str = "_tool",
    arguments: Any | None = None,
    model: str = "qwen3-vl:8b",
    content: str = "",
) -> dict[str, Any]:
    if arguments is None:
        arguments = {"query": "needle", "limit": 3}
    return {
        "model": model,
        "done": True,
        "message": {
            "role": "assistant",
            "content": content,
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
        },
    }


def _openai_response(
    *,
    name: str = "_tool",
    arguments: Any = '{"query":"needle","limit":3}',
    model: str = "local-tool-model",
    content: str | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                },
            }
        ],
    }


class TestToolSchemas:
    def test_callable_schema_is_strict_and_preserves_required_parameters(self) -> None:
        payload = local_llm._prepare_tools_payload([_tool])

        assert payload == [
            {
                "type": "function",
                "function": {
                    "name": "_tool",
                    "description": "Search a local index.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Exact search query.",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum result count.",
                            },
                        },
                        "additionalProperties": False,
                        "required": ["query"],
                    },
                },
            }
        ]

    def test_prebuilt_declaration_is_normalized_without_provider_sdk_types(self) -> None:
        wrapper = SimpleNamespace(
            function_declaration={
                "name": "read_local_state",
                "description": "Read state",
                "parameters": {"type": "object", "properties": {}},
            }
        )

        payload = local_llm._prepare_tools_payload([wrapper])

        assert payload[0]["type"] == "function"
        assert payload[0]["function"]["name"] == "read_local_state"

    @pytest.mark.parametrize(
        "payload",
        [
            '{"x":1,"x":2}',
            '{"x":NaN}',
            '{"x":Infinity}',
            '{"x":-Infinity}',
        ],
    )
    def test_strict_json_rejects_ambiguous_or_nonfinite_values(self, payload: str) -> None:
        with pytest.raises(ValueError):
            local_llm._strict_json_loads(payload)

    @pytest.mark.parametrize(
        ("annotation", "schema"),
        [
            (str, {"type": "string"}),
            (int, {"type": "integer"}),
            (float, {"type": "number"}),
            (bool, {"type": "boolean"}),
            (str | None, {"type": "string"}),
            (list[int], {"type": "array", "items": {"type": "integer"}}),
            (
                dict[str, bool],
                {"type": "object", "additionalProperties": {"type": "boolean"}},
            ),
            (Literal["read", "write"], {"type": "string", "enum": ["read", "write"]}),
        ],
    )
    def test_python_annotations_map_to_strict_json_schema(
        self, annotation: Any, schema: dict[str, Any]
    ) -> None:
        assert local_llm._json_schema_for_annotation(annotation) == schema


class TestLocalVisionPayload:
    def test_screenshot_is_resized_and_encoded_as_bounded_jpeg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_vision_max_dimension", 64)
        encoded = local_llm._encode_screenshot(Image.new("RGB", (256, 128), "white"))

        decoded = Image.open(BytesIO(base64.b64decode(encoded)))

        assert decoded.format == "JPEG"
        assert max(decoded.size) == 64

    def test_screenshot_byte_limit_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_image_max_bytes", 1)

        with pytest.raises(ValueError, match="LOCAL_LLM_IMAGE_MAX_BYTES"):
            local_llm._encode_screenshot(Image.new("RGB", (16, 16), "white"))

    def test_openai_vision_payload_uses_inline_local_image(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_backend", "openai-compatible")
        monkeypatch.setattr(local_llm.config, "local_llm_model", "local-tool-model")
        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "Use one tool.")
        tools = local_llm._prepare_tools_payload([_tool])

        payload = local_llm._build_request_payload(
            screenshot_image=Image.new("RGB", (8, 8), "white"),
            prompt_text="inspect",
            tools=tools,
        )

        content = payload["messages"][1]["content"]
        assert isinstance(content, list)
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert payload["tool_choice"] == "required"
        assert payload["parallel_tool_calls"] is False

    def test_ollama_payload_pins_configured_context_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_context_tokens", 131_072)
        monkeypatch.setattr(local_llm.config, "local_llm_vision_enabled", False)
        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "Use one tool.")

        payload = local_llm._build_request_payload(
            screenshot_image=Image.new("RGB", (8, 8), "white"),
            prompt_text="inspect",
            tools=local_llm._prepare_tools_payload([_tool]),
        )

        assert payload["options"]["num_ctx"] == 131_072
        assert payload["options"]["num_predict"] == local_llm.config.max_tokens
        assert payload["stream"] is False


class TestEndpointAndTransportSafety:
    @pytest.mark.parametrize(
        "endpoint",
        [
            "http://127.0.0.1:11434",
            "http://[::1]:11434",
        ],
    )
    def test_runtime_locality_accepts_literal_loopback(self, endpoint: str) -> None:
        local_llm._validate_endpoint_locality(endpoint)

    @pytest.mark.parametrize(
        "endpoint",
        [
            "https://127.0.0.1:11434",
            "http://8.8.8.8:11434",
            "http://model.example:11434",
            "file:///tmp/model.sock",
        ],
    )
    def test_runtime_locality_rejects_nonlocal_targets(self, endpoint: str) -> None:
        with pytest.raises(ValueError):
            local_llm._validate_endpoint_locality(endpoint)

    def test_localhost_resolution_must_remain_on_loopback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *_args, **_kwargs: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.10", 11434))
            ],
        )

        with pytest.raises(ValueError, match="outside the loopback"):
            local_llm._validate_endpoint_locality("http://localhost:11434")

    def test_fixed_service_name_is_accepted_only_in_docker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(ValueError):
            local_llm._validate_endpoint_locality("http://ollama:11434")

        monkeypatch.setattr(local_llm.config, "runtime_mode", "docker")
        local_llm._validate_endpoint_locality("http://ollama:11434")

    def test_redirect_handler_fails_closed(self) -> None:
        handler = local_llm._NoRedirectHandler()

        with pytest.raises(LocalLLMRequestError, match="prohibited HTTP redirect status 302"):
            handler.redirect_request(
                Request("http://127.0.0.1:11434/api/version"),
                None,
                302,
                "Found",
                {},
                "http://example.test/remote",
            )

    def test_request_ignores_environment_proxies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured_handlers: list[Any] = []

        class Response:
            headers = {"Content-Type": "application/json; charset=utf-8"}

            def __init__(self) -> None:
                self.body = b'{"version":"0.30.0"}'

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, _limit: int) -> bytes:
                chunk, self.body = self.body, b""
                return chunk

        class Opener:
            def open(self, request: Request, *, timeout: float) -> Response:
                assert request.full_url == "http://127.0.0.1:11434/api/version"
                assert timeout == 5.0
                return Response()

        def fake_build_opener(*handlers: Any) -> Opener:
            captured_handlers.extend(handlers)
            return Opener()

        monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:8080")
        monkeypatch.setenv("NO_PROXY", "")
        monkeypatch.setattr(local_llm, "build_opener", fake_build_opener)

        result = local_llm._request_json(
            "GET",
            "http://127.0.0.1:11434/api/version",
            timeout_seconds=5.0,
        )

        proxy_handler = next(item for item in captured_handlers if isinstance(item, ProxyHandler))
        assert proxy_handler.proxies == {}
        assert any(isinstance(item, local_llm._NoRedirectHandler) for item in captured_handlers)
        assert result == {"version": "0.30.0"}

    @pytest.mark.parametrize(
        "raw",
        [
            b"[]",
            b'{"duplicate":1,"duplicate":2}',
            b'{"not_finite":NaN}',
            b"\xff",
        ],
    )
    def test_request_rejects_invalid_response_envelopes(
        self, raw: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Response:
            headers = {"Content-Type": "application/json; charset=utf-8"}

            def __init__(self) -> None:
                self.body = raw

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, _limit: int) -> bytes:
                chunk, self.body = self.body, b""
                return chunk

        monkeypatch.setattr(
            local_llm,
            "build_opener",
            lambda *_handlers: SimpleNamespace(open=lambda *_args, **_kwargs: Response()),
        )

        with pytest.raises(LocalLLMRequestError):
            local_llm._request_json(
                "GET",
                "http://127.0.0.1:11434/api/version",
            )

    def test_request_enforces_response_byte_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class Response:
            headers = {"Content-Type": "application/json; charset=utf-8"}

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, limit: int) -> bytes:
                return b"x" * limit

        monkeypatch.setattr(local_llm.config, "local_llm_response_max_bytes", 1024)
        monkeypatch.setattr(
            local_llm,
            "build_opener",
            lambda *_handlers: SimpleNamespace(open=lambda *_args, **_kwargs: Response()),
        )

        with pytest.raises(LocalLLMRequestError, match="byte limit"):
            local_llm._request_json(
                "GET",
                "http://127.0.0.1:11434/api/version",
            )

    def test_request_rejects_non_json_content_type_before_reading_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Response:
            headers = {"Content-Type": "text/html"}

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, _limit: int) -> bytes:
                pytest.fail("a non-JSON response body must not be consumed")

        monkeypatch.setattr(
            local_llm,
            "build_opener",
            lambda *_handlers: SimpleNamespace(open=lambda *_args, **_kwargs: Response()),
        )

        with pytest.raises(LocalLLMRequestError, match="non-JSON content type"):
            local_llm._request_json("GET", "http://127.0.0.1:11434/api/version")

    def test_request_rejects_target_that_escapes_configured_origin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm, "build_opener", pytest.fail)

        with pytest.raises(LocalLLMRequestError, match="escaped the configured endpoint boundary"):
            local_llm._request_json(
                "GET",
                "http://localhost:11434/api/version",
            )

    def test_request_rejects_compressed_response_before_reading_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Response:
            headers = {
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            }

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, _limit: int) -> bytes:
                pytest.fail("a compressed response body must not be consumed")

        monkeypatch.setattr(
            local_llm,
            "build_opener",
            lambda *_handlers: SimpleNamespace(open=lambda *_args, **_kwargs: Response()),
        )

        with pytest.raises(LocalLLMRequestError, match="prohibited content encoding"):
            local_llm._request_json("GET", "http://127.0.0.1:11434/api/version")

    @pytest.mark.parametrize(
        ("content_length", "message"),
        [
            ("not-an-integer", "invalid content length"),
            ("-1", "configured byte limit"),
            (str(1_048_577), "configured byte limit"),
        ],
    )
    def test_request_rejects_invalid_or_oversized_content_length(
        self,
        content_length: str,
        message: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class Response:
            headers = {
                "Content-Type": "application/json",
                "Content-Length": content_length,
            }

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, _limit: int) -> bytes:
                pytest.fail("a rejected declared body length must not be consumed")

        monkeypatch.setattr(
            local_llm,
            "build_opener",
            lambda *_handlers: SimpleNamespace(open=lambda *_args, **_kwargs: Response()),
        )

        with pytest.raises(LocalLLMRequestError, match=message):
            local_llm._request_json("GET", "http://127.0.0.1:11434/api/version")

    def test_request_rejects_nonfinite_payload_before_transport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm, "build_opener", pytest.fail)

        with pytest.raises(LocalLLMRequestError, match="payload is not valid JSON"):
            local_llm._request_json(
                "POST",
                "http://127.0.0.1:11434/api/chat",
                payload={"temperature": float("nan")},
            )

    @pytest.mark.parametrize(
        ("status", "retryable"),
        [(400, False), (429, True), (500, True)],
    )
    def test_http_failure_retry_classification(
        self,
        status: int,
        retryable: bool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        error = HTTPError(
            "http://127.0.0.1:11434/api/chat",
            status,
            "error",
            None,
            None,
        )

        def fail(*_args: Any, **_kwargs: Any) -> Any:
            raise error

        monkeypatch.setattr(
            local_llm,
            "build_opener",
            lambda *_handlers: SimpleNamespace(open=fail),
        )

        with pytest.raises(LocalLLMRequestError) as captured:
            local_llm._request_json("POST", "http://127.0.0.1:11434/api/chat")

        assert captured.value.retryable is retryable
        assert str(status) in str(captured.value)

    @pytest.mark.parametrize(
        "error",
        [TimeoutError(), URLError(ConnectionRefusedError()), OSError("socket failed")],
    )
    def test_connection_failures_are_retryable(
        self, error: BaseException, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(*_args: Any, **_kwargs: Any) -> Any:
            raise error

        monkeypatch.setattr(
            local_llm,
            "build_opener",
            lambda *_handlers: SimpleNamespace(open=fail),
        )

        with pytest.raises(LocalLLMRequestError) as captured:
            local_llm._request_json("GET", "http://127.0.0.1:11434/api/version")

        assert captured.value.retryable is True


class TestToolCallParser:
    def test_ollama_parser_returns_provider_neutral_call(self) -> None:
        result = local_llm._parse_tool_call(
            _ollama_response(),
            available_tool_names={"_tool"},
        )

        assert result == LocalFunctionCall(
            name="_tool",
            args={"query": "needle", "limit": 3},
        )

    def test_openai_compatible_parser_requires_json_string_arguments(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_backend", "openai-compatible")
        monkeypatch.setattr(local_llm.config, "local_llm_model", "local-tool-model")

        result = local_llm._parse_tool_call(
            _openai_response(),
            available_tool_names={"_tool"},
        )

        assert result == LocalFunctionCall(
            name="_tool",
            args={"query": "needle", "limit": 3},
        )

    @pytest.mark.parametrize(
        ("response", "code", "terminal"),
        [
            (_ollama_response(model="other:8b"), "model_identity_mismatch", True),
            (
                {
                    "model": "qwen3-vl:8b",
                    "done": False,
                    "message": {"role": "assistant", "tool_calls": []},
                },
                "incomplete_response",
                True,
            ),
            (
                {
                    "model": "qwen3-vl:8b",
                    "done": True,
                    "message": {"role": "assistant", "content": "I am done."},
                },
                "mixed_prose_and_tool_call",
                False,
            ),
            (
                {
                    "model": "qwen3-vl:8b",
                    "done": True,
                    "message": {"role": "assistant", "content": "", "tool_calls": []},
                },
                "tool_call_required",
                False,
            ),
        ],
    )
    def test_parser_returns_typed_failures(
        self,
        response: dict[str, Any],
        code: str,
        terminal: bool,
    ) -> None:
        result = local_llm._parse_tool_call(response, available_tool_names={"_tool"})

        assert isinstance(result, ReasoningFailure)
        assert result.code == code
        assert result.terminal is terminal

    def test_parser_rejects_legacy_function_call_envelope(self) -> None:
        response = _ollama_response()
        response["message"]["function_call"] = {"name": "_tool"}  # type: ignore[index]

        result = local_llm._parse_tool_call(response, available_tool_names={"_tool"})

        assert isinstance(result, ReasoningFailure)
        assert result.code == "legacy_function_call"
        assert result.terminal is True

    @pytest.mark.parametrize(
        ("choices", "code", "terminal"),
        [
            ([], "invalid_choice_count", True),
            (
                [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "done"},
                    }
                ],
                "tool_call_required",
                False,
            ),
        ],
    )
    def test_openai_parser_rejects_invalid_completion_envelopes(
        self,
        choices: list[dict[str, Any]],
        code: str,
        terminal: bool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_backend", "openai-compatible")
        monkeypatch.setattr(local_llm.config, "local_llm_model", "local-tool-model")

        result = local_llm._parse_tool_call(
            {"model": "local-tool-model", "choices": choices},
            available_tool_names={"_tool"},
        )

        assert isinstance(result, ReasoningFailure)
        assert result.code == code
        assert result.terminal is terminal

    def test_ollama_parser_requires_object_arguments(self) -> None:
        result = local_llm._parse_tool_call(
            _ollama_response(arguments='{"query":"needle"}'),
            available_tool_names={"_tool"},
        )

        assert isinstance(result, ReasoningFailure)
        assert result.code == "invalid_tool_arguments"

    def test_parser_rejects_multiple_tool_calls(self) -> None:
        response = _ollama_response()
        response["message"]["tool_calls"].append(  # type: ignore[index,union-attr]
            {"function": {"name": "_tool", "arguments": {"query": "second"}}}
        )

        result = local_llm._parse_tool_call(response, available_tool_names={"_tool"})

        assert isinstance(result, ReasoningFailure)
        assert result.code == "multiple_tool_calls"
        assert result.terminal is False

    def test_parser_rejects_prose_mixed_with_tool_call(self) -> None:
        result = local_llm._parse_tool_call(
            _ollama_response(content="First, I will explain."),
            available_tool_names={"_tool"},
        )

        assert isinstance(result, ReasoningFailure)
        assert result.code == "mixed_prose_and_tool_call"

    def test_parser_rejects_unknown_tool_without_echoing_arguments(self) -> None:
        result = local_llm._parse_tool_call(
            _ollama_response(name="undeclared", arguments={"secret": "do-not-log"}),
            available_tool_names={"_tool"},
        )

        assert isinstance(result, ReasoningFailure)
        assert result.code == "unknown_tool"
        assert "do-not-log" not in result.message

    @pytest.mark.parametrize(
        "arguments",
        [
            {"query": float("nan")},
            "not-json",
            '{"query":"a","query":"b"}',
            '{"query":NaN}',
            {"query": "object-is-not-allowed-for-openai"},
        ],
    )
    def test_openai_parser_rejects_malformed_or_ambiguous_arguments(
        self, arguments: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_backend", "openai-compatible")
        monkeypatch.setattr(local_llm.config, "local_llm_model", "local-tool-model")
        response = _openai_response(arguments=arguments)

        result = local_llm._parse_tool_call(response, available_tool_names={"_tool"})

        assert isinstance(result, ReasoningFailure)
        assert result.code == "invalid_tool_arguments"

    def test_openai_parser_rejects_wrong_call_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_backend", "openai-compatible")
        monkeypatch.setattr(local_llm.config, "local_llm_model", "local-tool-model")
        response = _openai_response()
        response["choices"][0]["message"]["tool_calls"][0]["type"] = "custom"  # type: ignore[index]

        result = local_llm._parse_tool_call(response, available_tool_names={"_tool"})

        assert isinstance(result, ReasoningFailure)
        assert result.code == "invalid_tool_call_type"
        assert result.terminal is True

    def test_latest_alias_is_accepted_only_when_tag_is_implicit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_model", "local-model")

        accepted = local_llm._parse_tool_call(
            _ollama_response(model="local-model:latest"),
            available_tool_names={"_tool"},
        )

        assert isinstance(accepted, LocalFunctionCall)


class TestRuntimePreflight:
    def test_ollama_preflight_attests_exact_local_artifact_and_capabilities(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        digest = "a" * 64
        monkeypatch.setattr(local_llm.config, "local_llm_expected_digest", digest)
        requests: list[tuple[str, str, Any]] = []

        def fake_request(
            method: str,
            url: str,
            *,
            payload: Any = None,
            timeout_seconds: float | None = None,
        ) -> dict[str, Any]:
            del timeout_seconds
            requests.append((method, url, payload))
            if url.endswith("/api/version"):
                return {"version": "0.30.0"}
            if url.endswith("/api/tags"):
                return {
                    "models": [
                        {
                            "name": "qwen3-vl:8b",
                            "size": 6_100_000_000,
                            "digest": digest,
                        }
                    ]
                }
            if url.endswith("/api/show"):
                return {
                    "capabilities": ["completion", "tools", "vision"],
                    "model_info": {
                        "vision.context_length": 32_768,
                        "qwen3vl.context_length": 131_072,
                    },
                }
            raise AssertionError(f"unexpected URL: {url}")

        monkeypatch.setattr(local_llm.config, "validate", lambda: True)
        monkeypatch.setattr(local_llm, "_request_json", fake_request)

        result = local_llm.validate_local_runtime()

        assert result.backend == "ollama"
        assert result.model == "qwen3-vl:8b"
        assert result.runtime_version == "0.30.0"
        assert result.model_digest == digest
        assert result.context_tokens == 65_536
        assert [request[0] for request in requests] == ["GET", "GET", "POST"]
        assert requests[-1][2] == {"model": "qwen3-vl:8b", "verbose": False}
        assert all("/pull" not in url for _method, url, _payload in requests)

    @pytest.mark.parametrize(
        ("show_response", "message"),
        [
            (
                {"capabilities": ["tools", "vision"]},
                "did not advertise model metadata",
            ),
            (
                {
                    "capabilities": ["tools", "vision"],
                    "model_info": {},
                },
                "did not advertise a context length",
            ),
            (
                {
                    "capabilities": ["tools", "vision"],
                    "model_info": {"qwen3vl.context_length": False},
                },
                "did not advertise a context length",
            ),
            (
                {
                    "capabilities": ["tools", "vision"],
                    "model_info": {"qwen3vl.context_length": 32_768},
                },
                "cannot provide the configured context window",
            ),
        ],
    )
    def test_ollama_preflight_rejects_missing_or_insufficient_context_metadata(
        self,
        show_response: dict[str, Any],
        message: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fake_request(method: str, url: str, **_kwargs: Any) -> dict[str, Any]:
            del method
            if url.endswith("/api/version"):
                return {"version": "0.30.0"}
            if url.endswith("/api/tags"):
                return {
                    "models": [
                        {
                            "name": "qwen3-vl:8b",
                            "size": 1,
                            "digest": "a" * 64,
                        }
                    ]
                }
            return show_response

        monkeypatch.setattr(local_llm.config, "validate", lambda: True)
        monkeypatch.setattr(local_llm, "_request_json", fake_request)

        with pytest.raises(ValueError, match=message):
            local_llm.validate_local_runtime()

    def test_ollama_preflight_shares_one_total_deadline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monotonic_values = iter([0.0, 1.0, 5.0, 29.0])
        observed_timeouts: list[float] = []

        def fake_request(
            method: str,
            url: str,
            *,
            payload: Any = None,
            timeout_seconds: float | None = None,
        ) -> dict[str, Any]:
            del method, payload
            assert timeout_seconds is not None
            observed_timeouts.append(timeout_seconds)
            if url.endswith("/api/version"):
                return {"version": "0.30.0"}
            if url.endswith("/api/tags"):
                return {
                    "models": [
                        {
                            "name": "qwen3-vl:8b",
                            "size": 1,
                            "digest": "a" * 64,
                        }
                    ]
                }
            return {
                "capabilities": ["tools", "vision"],
                "model_info": {"qwen3vl.context_length": 131_072},
            }

        monkeypatch.setattr(local_llm.config, "validate", lambda: True)
        monkeypatch.setattr(local_llm.time, "monotonic", lambda: next(monotonic_values))
        monkeypatch.setattr(local_llm, "_request_json", fake_request)

        result = local_llm.validate_local_runtime()

        assert result.model_digest == "a" * 64
        assert observed_timeouts == [29.0, 25.0, 1.0]

    def test_ollama_preflight_fails_before_next_request_when_deadline_expires(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monotonic_values = iter([0.0, 1.0, 31.0])
        requests = 0

        def fake_request(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            nonlocal requests
            requests += 1
            return {"version": "0.30.0"}

        monkeypatch.setattr(local_llm.config, "validate", lambda: True)
        monkeypatch.setattr(local_llm.time, "monotonic", lambda: next(monotonic_values))
        monkeypatch.setattr(local_llm, "_request_json", fake_request)

        with pytest.raises(LocalLLMRequestError, match="preflight deadline expired"):
            local_llm.validate_local_runtime()

        assert requests == 1

    def test_ollama_preflight_rejects_pinned_digest_mismatch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_expected_digest", "b" * 64)
        monkeypatch.setattr(local_llm.config, "validate", lambda: True)

        def fake_request(method: str, url: str, **_kwargs: Any) -> dict[str, Any]:
            del method
            if url.endswith("/api/version"):
                return {"version": "0.30.0"}
            if url.endswith("/api/tags"):
                return {
                    "models": [
                        {
                            "name": "qwen3-vl:8b",
                            "size": 1,
                            "digest": "a" * 64,
                        }
                    ]
                }
            pytest.fail("capability probing must not continue after a digest mismatch")

        monkeypatch.setattr(local_llm, "_request_json", fake_request)

        with pytest.raises(ValueError, match="pinned artifact digest"):
            local_llm.validate_local_runtime()

    @pytest.mark.parametrize("version", [None, "", "x" * 129, "bad\nversion"])
    def test_ollama_preflight_rejects_malformed_runtime_version(
        self, version: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm.config, "validate", lambda: True)
        monkeypatch.setattr(
            local_llm,
            "_request_json",
            lambda *_args, **_kwargs: {"version": version},
        )

        with pytest.raises(ValueError, match="malformed runtime version"):
            local_llm.validate_local_runtime()

    def test_openai_compatible_preflight_rejects_missing_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_backend", "openai-compatible")
        monkeypatch.setattr(local_llm.config, "local_llm_endpoint", "http://127.0.0.1:8080/v1")
        monkeypatch.setattr(local_llm.config, "local_llm_model", "local-tool-model")
        monkeypatch.setattr(local_llm.config, "validate", lambda: True)
        monkeypatch.setattr(
            local_llm,
            "_request_json",
            lambda *_args, **_kwargs: {"data": [{"id": "other-model"}]},
        )

        with pytest.raises(ValueError, match="installed/loaded exactly once"):
            local_llm.validate_local_runtime()

    @pytest.mark.parametrize(
        ("models", "capabilities", "message"),
        [
            ([], ["tools", "vision"], "not installed exactly once"),
            (
                [{"name": "qwen3-vl:8b", "size": 1, "digest": "not-a-digest"}],
                ["tools", "vision"],
                "artifact metadata",
            ),
            (
                [{"name": "qwen3-vl:8b", "size": 1, "digest": "a" * 64}],
                ["vision"],
                "tool capability",
            ),
            (
                [{"name": "qwen3-vl:8b", "size": 1, "digest": "a" * 64}],
                ["tools"],
                "vision capability",
            ),
        ],
    )
    def test_ollama_preflight_fails_closed(
        self,
        models: list[dict[str, Any]],
        capabilities: list[str],
        message: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fake_request(method: str, url: str, **_kwargs: Any) -> dict[str, Any]:
            del method
            if url.endswith("/api/version"):
                return {"version": "0.30.0"}
            if url.endswith("/api/tags"):
                return {"models": models}
            return {
                "capabilities": capabilities,
                "model_info": {"qwen3vl.context_length": 131_072},
            }

        monkeypatch.setattr(local_llm.config, "validate", lambda: True)
        monkeypatch.setattr(local_llm, "_request_json", fake_request)

        with pytest.raises(ValueError, match=message):
            local_llm.validate_local_runtime()

    def test_openai_compatible_preflight_requires_exact_loaded_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_backend", "openai-compatible")
        monkeypatch.setattr(local_llm.config, "local_llm_endpoint", "http://127.0.0.1:8080/v1")
        monkeypatch.setattr(local_llm.config, "local_llm_model", "local-tool-model")
        monkeypatch.setattr(local_llm.config, "validate", lambda: True)
        monkeypatch.setattr(
            local_llm,
            "_request_json",
            lambda method, url, **kwargs: {"data": [{"id": "local-tool-model"}]},
        )

        result = local_llm.validate_local_runtime()

        assert result.backend == "openai-compatible"
        assert result.runtime_version == "openai-compatible"
        assert result.model_digest == ""
        assert result.context_tokens is None


class TestDecisionContract:
    @pytest.fixture()
    def screenshot(self) -> Image.Image:
        return Image.new("RGB", (16, 16), "white")

    @staticmethod
    def _invoke(screenshot: Image.Image, *, cancel_event: Event | None = None) -> Any:
        return local_llm.decide_next_action(
            screenshot_image=screenshot,
            ui_tree="button: Search",
            user_command="Search the local index",
            history=[],
            available_tools=[_tool],
            cancel_event=cancel_event,
            runtime_context="No action yet.",
        )

    def test_success_returns_one_provider_neutral_call(
        self, screenshot: Image.Image, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "Use one tool.")
        monkeypatch.setattr(local_llm, "_request_json", lambda *args, **kwargs: _ollama_response())

        result = self._invoke(screenshot)

        assert result == LocalFunctionCall(
            name="_tool",
            args={"query": "needle", "limit": 3},
        )

    def test_no_tools_fails_before_transport(
        self, screenshot: Image.Image, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "Use one tool.")
        request = pytest.fail
        monkeypatch.setattr(local_llm, "_request_json", request)

        result = local_llm.decide_next_action(
            screenshot_image=screenshot,
            ui_tree="",
            user_command="task",
            history=[],
            available_tools=[],
        )

        assert isinstance(result, ReasoningFailure)
        assert result.code == "no_tools_available"
        assert result.terminal is True

    def test_cancellation_fails_before_schema_or_transport(
        self, screenshot: Image.Image, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cancelled = Event()
        cancelled.set()
        monkeypatch.setattr(local_llm, "_prepare_tools_payload", pytest.fail)
        monkeypatch.setattr(local_llm, "_request_json", pytest.fail)

        result = self._invoke(screenshot, cancel_event=cancelled)

        assert isinstance(result, ReasoningFailure)
        assert result.code == "cancelled"

    def test_missing_system_prompt_fails_before_transport(
        self, screenshot: Image.Image, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "   ")
        monkeypatch.setattr(local_llm, "_request_json", pytest.fail)

        result = self._invoke(screenshot)

        assert isinstance(result, ReasoningFailure)
        assert result.code == "missing_system_prompt"
        assert result.terminal is True

    def test_runtime_error_envelope_is_nonretryable(
        self, screenshot: Image.Image, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = 0

        def request(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            nonlocal attempts
            attempts += 1
            return {"error": "model rejected input"}

        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "Use one tool.")
        monkeypatch.setattr(local_llm, "_request_json", request)

        result = self._invoke(screenshot)

        assert isinstance(result, ReasoningFailure)
        assert result.code == "local_runtime_unavailable"
        assert attempts == 1

    def test_transient_transport_failure_retries_then_succeeds(
        self, screenshot: Image.Image, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = 0

        def request(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise LocalLLMRequestError("daemon busy", retryable=True)
            return _ollama_response()

        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "Use one tool.")
        monkeypatch.setattr(local_llm, "_request_json", request)
        monkeypatch.setattr(local_llm, "_wait_before_retry", lambda *_args: False)

        result = self._invoke(screenshot)

        assert isinstance(result, LocalFunctionCall)
        assert attempts == 2

    def test_retry_loop_respects_one_total_reasoning_deadline(
        self, screenshot: Image.Image, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = 0
        monotonic_values = iter([0.0, 0.0, 31.0, 31.0])

        def request(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            nonlocal attempts
            attempts += 1
            raise LocalLLMRequestError("daemon busy", retryable=True)

        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "Use one tool.")
        monkeypatch.setattr(local_llm, "_request_json", request)
        monkeypatch.setattr(local_llm.time, "monotonic", lambda: next(monotonic_values))

        result = self._invoke(screenshot)

        assert isinstance(result, ReasoningFailure)
        assert result.code == "local_runtime_unavailable"
        assert attempts == 1

    def test_cancellation_during_retry_backoff_stops_immediately(
        self, screenshot: Image.Image, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = 0

        def request(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            nonlocal attempts
            attempts += 1
            raise LocalLLMRequestError("daemon busy", retryable=True)

        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "Use one tool.")
        monkeypatch.setattr(local_llm, "_request_json", request)
        monkeypatch.setattr(local_llm, "_wait_before_retry", lambda *_args: True)

        result = self._invoke(screenshot)

        assert isinstance(result, ReasoningFailure)
        assert result.code == "cancelled"
        assert attempts == 1

    def test_nonretryable_transport_failure_stops_immediately(
        self, screenshot: Image.Image, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = 0

        def request(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            nonlocal attempts
            attempts += 1
            raise LocalLLMRequestError("invalid local response", retryable=False)

        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "Use one tool.")
        monkeypatch.setattr(local_llm, "_request_json", request)

        result = self._invoke(screenshot)

        assert isinstance(result, ReasoningFailure)
        assert result.code == "local_runtime_unavailable"
        assert result.terminal is True
        assert attempts == 1

    def test_prompt_redacts_secret_shapes_before_transport(
        self, screenshot: Image.Image, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_payload: dict[str, Any] = {}
        secret = "Bearer this-is-a-private-token-value"

        def request(
            _method: str,
            _url: str,
            *,
            payload: dict[str, Any],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            captured_payload.update(payload)
            return _ollama_response()

        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "Use one tool.")
        monkeypatch.setattr(local_llm, "_request_json", request)

        result = local_llm.decide_next_action(
            screenshot_image=screenshot,
            ui_tree=f"label={secret}",
            user_command="Inspect the UI",
            history=[f"tool result token={secret}"],
            available_tools=[_tool],
        )

        assert isinstance(result, LocalFunctionCall)
        assert secret not in json.dumps(captured_payload)

    def test_openai_payload_disables_parallel_calls_and_requires_a_tool(
        self, screenshot: Image.Image, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(local_llm.config, "local_llm_backend", "openai-compatible")
        monkeypatch.setattr(local_llm.config, "local_llm_endpoint", "http://127.0.0.1:8080/v1")
        monkeypatch.setattr(local_llm.config, "local_llm_model", "local-tool-model")
        monkeypatch.setattr(local_llm.config, "local_llm_vision_enabled", False)
        monkeypatch.setattr(local_llm, "SYSTEM_PROMPT", "Use one tool.")
        captured: dict[str, Any] = {}

        def request(
            method: str,
            url: str,
            *,
            payload: dict[str, Any],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            captured.update(payload)
            assert method == "POST"
            assert url == "http://127.0.0.1:8080/v1/chat/completions"
            return _openai_response()

        monkeypatch.setattr(local_llm, "_request_json", request)

        result = self._invoke(screenshot)

        assert isinstance(result, LocalFunctionCall)
        assert captured["tool_choice"] == "required"
        assert captured["parallel_tool_calls"] is False
        assert captured["n"] == 1
        assert captured["stream"] is False
