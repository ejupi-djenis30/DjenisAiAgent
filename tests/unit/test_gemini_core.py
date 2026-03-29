"""Unit tests for src/reasoning/gemini_core.py.

All tests use mocks — no real Gemini API calls are made.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.reasoning.gemini_core import (
    _build_function_declaration,
    _json_type_for_annotation,
    _prepare_tools_payload,
)


# ---------------------------------------------------------------------------
# _json_type_for_annotation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _build_function_declaration
# ---------------------------------------------------------------------------


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
        props = call_kwargs["parameters"]["properties"]
        assert "name" in props
        assert props["name"]["type"] == "string"

    def test_required_params_listed(self) -> None:
        def move(x: int, y: int) -> str:
            return ""

        with patch("src.reasoning.gemini_core.genai_types") as mock_types:
            _build_function_declaration(move)

        call_kwargs = mock_types.FunctionDeclaration.call_args[1]
        assert "x" in call_kwargs["parameters"]["required"]
        assert "y" in call_kwargs["parameters"]["required"]

    def test_optional_param_not_in_required(self) -> None:
        from typing import Optional

        def func(required: str, optional: Optional[str] = None) -> str:
            return ""

        with patch("src.reasoning.gemini_core.genai_types") as mock_types:
            _build_function_declaration(func)

        call_kwargs = mock_types.FunctionDeclaration.call_args[1]
        assert "required" in call_kwargs["parameters"]["required"]
        assert "optional" not in call_kwargs["parameters"].get("required", [])

    def test_no_docstring_uses_empty_description(self) -> None:
        def no_doc(x: str) -> str:
            return x  # no docstring

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
        # *args and **kwargs should not appear in properties
        assert call_kwargs["parameters"]["properties"] == {}


# ---------------------------------------------------------------------------
# _prepare_tools_payload
# ---------------------------------------------------------------------------


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
        """If a callable has .function_declaration, use it directly."""
        mock_decl = MagicMock()

        def my_tool(x: str) -> str:
            return x

        my_tool.function_declaration = mock_decl  # type: ignore[attr-defined]

        mock_tool_obj = MagicMock()
        with patch("src.reasoning.gemini_core.genai_types") as mock_types:
            mock_types.Tool.return_value = mock_tool_obj
            result = _prepare_tools_payload([my_tool])

        # Should have used the prebuilt declaration, not called FunctionDeclaration()
        mock_types.FunctionDeclaration.assert_not_called()
        assert result == [mock_tool_obj]
