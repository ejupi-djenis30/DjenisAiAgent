"""Unit tests for src/reasoning/gemini_core.py.

All tests use mocks. No real Gemini API calls are made.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import src.reasoning.gemini_core as gemini_core
from src.reasoning.gemini_core import (
    _build_function_declaration,
    _json_type_for_annotation,
    _load_system_prompt,
    _prepare_tools_payload,
    decide_next_action,
)


class TestJsonTypeForAnnotation:
    def test_str_maps_to_string(self) -> None:
        assert _json_type_for_annotation(str) == "string"

    def test_int_maps_to_integer(self) -> None:
        assert _json_type_for_annotation(int) == "integer"

    def test_float_maps_to_number(self) -> None:
        assert _json_type_for_annotation(float) == "number"

    def test_bool_maps_to_boolean(self) -> None:
        assert _json_type_for_annotation(bool) == "boolean"

    def test_unknown_type_defaults_to_string(self) -> None:
        assert _json_type_for_annotation(list) == "string"

    def test_optional_str_maps_to_string(self) -> None:
        from typing import Optional

        assert _json_type_for_annotation(Optional[str]) == "string"

    def test_optional_int_maps_to_integer(self) -> None:
        from typing import Optional

        assert _json_type_for_annotation(Optional[int]) == "integer"


class TestBuildFunctionDeclaration:
    def test_simple_function(self) -> None:
        def greet(name: str) -> str:
            """Say hello."""
            return f"Hello {name}"

        with patch("src.reasoning.gemini_core.genai_types") as mock_types:
            mock_decl = MagicMock()
            mock_types.FunctionDeclaration.return_value = mock_decl
            result = _build_function_declaration(greet)

        assert result is mock_decl
        call_kwargs = mock_types.FunctionDeclaration.call_args[1]
        assert call_kwargs["name"] == "greet"
        assert call_kwargs["description"] == "Say hello."
        props = call_kwargs["parameters_json_schema"]["properties"]
        assert "name" in props
        assert props["name"]["type"] == "string"

    def test_required_params_listed(self) -> None:
        def move(x: int, y: int) -> str:
            return ""

        with patch("src.reasoning.gemini_core.genai_types") as mock_types:
            _build_function_declaration(move)

        call_kwargs = mock_types.FunctionDeclaration.call_args[1]
        assert "x" in call_kwargs["parameters_json_schema"]["required"]
        assert "y" in call_kwargs["parameters_json_schema"]["required"]

    def test_optional_param_not_in_required(self) -> None:
        from typing import Optional

        def func(required: str, optional: Optional[str] = None) -> str:
            return ""

        with patch("src.reasoning.gemini_core.genai_types") as mock_types:
            _build_function_declaration(func)

        call_kwargs = mock_types.FunctionDeclaration.call_args[1]
        assert "required" in call_kwargs["parameters_json_schema"]["required"]
        assert "optional" not in call_kwargs["parameters_json_schema"].get("required", [])

    def test_no_docstring_uses_empty_description(self) -> None:
        def no_doc(x: str) -> str:
            return x

        with patch("src.reasoning.gemini_core.genai_types") as mock_types:
            _build_function_declaration(no_doc)

        call_kwargs = mock_types.FunctionDeclaration.call_args[1]
        assert call_kwargs["description"] == ""

    def test_variadic_params_ignored(self) -> None:
        def varargs(*args: Any, **kwargs: Any) -> str:
            return ""

        with patch("src.reasoning.gemini_core.genai_types") as mock_types:
            _build_function_declaration(varargs)

        call_kwargs = mock_types.FunctionDeclaration.call_args[1]
        assert call_kwargs["parameters_json_schema"]["properties"] == {}


class TestPrepareToolsPayload:
    def test_returns_empty_list_when_no_tools(self) -> None:
        with patch("src.reasoning.gemini_core.genai_types"):
            result = _prepare_tools_payload([])
        assert result == []

    def test_builds_payload_from_callables(self) -> None:
        def my_tool(x: str) -> str:
            """A test tool."""
            return x

        mock_decl = MagicMock()
        mock_tool_obj = MagicMock()

        with patch("src.reasoning.gemini_core.genai_types") as mock_types:
            mock_types.FunctionDeclaration.return_value = mock_decl
            mock_types.Tool.return_value = mock_tool_obj
            result = _prepare_tools_payload([my_tool])

        assert result == [mock_tool_obj]

    def test_uses_prebuilt_declaration_if_present(self) -> None:
        mock_decl = MagicMock()

        def my_tool(x: str) -> str:
            return x

        my_tool.function_declaration = mock_decl  # type: ignore[attr-defined]

        mock_tool_obj = MagicMock()
        with patch("src.reasoning.gemini_core.genai_types") as mock_types:
            mock_types.Tool.return_value = mock_tool_obj
            result = _prepare_tools_payload([my_tool])

        mock_types.FunctionDeclaration.assert_not_called()
        assert result == [mock_tool_obj]


class TestPromptLoading:
    def test_load_system_prompt_reads_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_path = MagicMock()
        fake_path.read_text.return_value = "prompt body"
        monkeypatch.setattr("src.reasoning.gemini_core._PROMPT_FILE", fake_path)

        assert _load_system_prompt() == "prompt body"

    def test_load_system_prompt_returns_empty_on_os_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_path = MagicMock()
        fake_path.read_text.side_effect = OSError("missing")
        monkeypatch.setattr("src.reasoning.gemini_core._PROMPT_FILE", fake_path)

        assert _load_system_prompt() == ""


class TestDecideNextAction:
    def _patch_common_dependencies(self, monkeypatch: pytest.MonkeyPatch, response: Any) -> MagicMock:
        tool_decl = SimpleNamespace(name="click")
        tool_wrapper = SimpleNamespace(function_declarations=[tool_decl])
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.models.generate_content.return_value = response

        monkeypatch.setattr(gemini_core, "_prepare_tools_payload", lambda tools: [tool_wrapper])
        monkeypatch.setattr(gemini_core, "SYSTEM_PROMPT", "Prompt {MAX_LOOP_TURNS} {ACTION_TIMEOUT}")
        monkeypatch.setattr(gemini_core.genai, "Client", lambda api_key: client)
        monkeypatch.setattr(gemini_core.genai_types, "GenerateContentConfig", lambda **kwargs: kwargs)
        return client

    def test_returns_error_when_no_tools_are_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gemini_core, "_prepare_tools_payload", lambda tools: [])

        result = decide_next_action(MagicMock(), "tree", "cmd", [], [])

        assert "Nessun tool disponibile" in result

    def test_returns_function_call_from_response_property_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        function_call = SimpleNamespace(name="click", args={"element_id": "1"})
        candidate = SimpleNamespace(finish_reason=None, content=SimpleNamespace(parts=[]))
        response = SimpleNamespace(candidates=[candidate], function_calls=[function_call], text="")
        self._patch_common_dependencies(monkeypatch, response)

        result = decide_next_action(MagicMock(), "tree", "cmd", [], [lambda: None])

        assert result is function_call

    def test_invalid_tool_call_name_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        function_call = SimpleNamespace(name="invented", args={})
        candidate = SimpleNamespace(finish_reason=None, content=SimpleNamespace(parts=[]))
        response = SimpleNamespace(candidates=[candidate], function_calls=[function_call], text="")
        self._patch_common_dependencies(monkeypatch, response)

        result = decide_next_action(MagicMock(), "tree", "cmd", [], [lambda: None])

        assert "NON ESISTE" in result

    def test_consecutive_deep_think_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tool_decl = SimpleNamespace(name="deep_think")
        tool_wrapper = SimpleNamespace(function_declarations=[tool_decl])
        function_call = SimpleNamespace(name="deep_think", args={})
        candidate = SimpleNamespace(finish_reason=None, content=SimpleNamespace(parts=[]))
        response = SimpleNamespace(candidates=[candidate], function_calls=[function_call], text="")
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.models.generate_content.return_value = response

        monkeypatch.setattr(gemini_core, "_prepare_tools_payload", lambda tools: [tool_wrapper])
        monkeypatch.setattr(gemini_core, "SYSTEM_PROMPT", "Prompt")
        monkeypatch.setattr(gemini_core.genai, "Client", lambda api_key: client)
        monkeypatch.setattr(gemini_core.genai_types, "GenerateContentConfig", lambda **kwargs: kwargs)

        result = decide_next_action(
            MagicMock(),
            "tree",
            "cmd",
            ["PENSIERO PROFONDO: deep_think already used"],
            [lambda: None],
        )

        assert "usare 'deep_think' consecutivamente" in result

    def test_text_only_response_returns_critical_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        candidate = SimpleNamespace(
            finish_reason=None,
            content=SimpleNamespace(parts=[SimpleNamespace(function_call=None, text="just text")]),
        )
        response = SimpleNamespace(candidates=[candidate], function_calls=[], text="just text")
        self._patch_common_dependencies(monkeypatch, response)

        result = decide_next_action(MagicMock(), "tree", "cmd", [], [lambda: None])

        assert "ERRORE CRITICO" in result

    def test_empty_candidates_returns_safety_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        response = SimpleNamespace(candidates=[], function_calls=[])
        self._patch_common_dependencies(monkeypatch, response)

        result = decide_next_action(MagicMock(), "tree", "cmd", [], [lambda: None])

        assert "bloccata per motivi di sicurezza" in result

    def test_rate_limit_error_retries_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeAPIError(Exception):
            def __init__(self, code: int, message: str) -> None:
                self.code = code
                super().__init__(message)

        function_call = SimpleNamespace(name="click", args={"element_id": "1"})
        candidate = SimpleNamespace(finish_reason=None, content=SimpleNamespace(parts=[]))
        response = SimpleNamespace(candidates=[candidate], function_calls=[function_call], text="")
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.models.generate_content.side_effect = [FakeAPIError(429, "quota"), response]

        tool_decl = SimpleNamespace(name="click")
        tool_wrapper = SimpleNamespace(function_declarations=[tool_decl])
        monkeypatch.setattr(gemini_core, "_prepare_tools_payload", lambda tools: [tool_wrapper])
        monkeypatch.setattr(gemini_core, "SYSTEM_PROMPT", "Prompt")
        monkeypatch.setattr(gemini_core.genai, "Client", lambda api_key: client)
        monkeypatch.setattr(gemini_core.genai_types, "GenerateContentConfig", lambda **kwargs: kwargs)
        monkeypatch.setattr(gemini_core.genai_errors, "APIError", FakeAPIError)
        monkeypatch.setattr(gemini_core.time, "sleep", lambda seconds: None)

        result = decide_next_action(MagicMock(), "tree", "cmd", [], [lambda: None])

        assert result is function_call
