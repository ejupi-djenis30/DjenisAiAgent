"""Deterministic execution and completion guards for the agent loop."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import types
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

TaskOutcome = Literal["completed", "blocked"]
ToolEffect = Literal["meta", "read", "mutate"]

_META_TOOLS = frozenset({"finish_task"})
_READ_TOOLS = frozenset(
    {
        "browser_get_current_url",
        "browser_media_capability",
        "browser_runtime_status",
        "element_id",
        "element_id_fast",
        "get_clipboard_text",
        "get_text",
        "list_files",
        "read_clipboard",
        "read_file",
    }
)
_READ_VERIFIERS_BY_MUTATION: dict[str, frozenset[str]] = {
    "browser_find_and_click": frozenset({"browser_get_current_url"}),
    "browser_find_and_type": frozenset({"browser_get_current_url"}),
    "browser_navigate": frozenset({"browser_get_current_url"}),
    "browser_press_enter": frozenset({"browser_get_current_url"}),
    "click": frozenset({"element_id", "element_id_fast", "get_text"}),
    "copy_to_clipboard": frozenset({"get_clipboard_text", "read_clipboard"}),
    "double_click": frozenset({"element_id", "element_id_fast", "get_text"}),
    "hotkey": frozenset({"element_id", "element_id_fast", "get_text"}),
    "maximize_window": frozenset({"element_id", "element_id_fast", "get_text"}),
    "paste_from_clipboard": frozenset({"element_id", "element_id_fast", "get_text"}),
    "press_key_repeat": frozenset({"element_id", "element_id_fast", "get_text"}),
    "press_keys": frozenset({"element_id", "element_id_fast", "get_text"}),
    "right_click": frozenset({"element_id", "element_id_fast", "get_text"}),
    "scroll": frozenset({"element_id", "element_id_fast", "get_text"}),
    "set_clipboard_text": frozenset({"get_clipboard_text", "read_clipboard"}),
    "switch_window": frozenset({"element_id", "element_id_fast", "get_text"}),
    "take_screenshot": frozenset({"list_files"}),
    "type_text": frozenset({"element_id", "element_id_fast", "get_text"}),
    "write_file": frozenset({"list_files", "read_file"}),
}
_SELF_VERIFYING_MUTATIONS = frozenset({"browser_navigate", "run_shell_command"})
_FAILURE_PREFIXES = (
    "browser click failed",
    "browser element not found",
    "browser element query",
    "browser element timeout",
    "browser keypress failed",
    "browser navigation could not",
    "browser navigation failed",
    "browser typing failed",
    "browser url",
    "could not",
    "error",
    "failed",
    "failure",
    "invalid",
    "permission denied",
    "selenium is not available",
    "selenium is not installed",
    "selenium is unavailable",
    "stagnation guard",
    "this tool only works",
    "tool call rejected",
    "unexpected error",
    "unsupported",
)
_GENERIC_EVIDENCE = frozenset(
    {
        "complete",
        "completed",
        "done",
        "finished",
        "it worked",
        "ok",
        "success",
        "successful",
        "task completed",
    }
)
_OBJECTIVE_ACTION_WORDS = frozenset(
    {
        "apri",
        "cerca",
        "cambia",
        "change",
        "chiudere",
        "chiuderlo",
        "chiudi",
        "click",
        "clicca",
        "complete",
        "close",
        "closing",
        "crea",
        "create",
        "digita",
        "delete",
        "elimina",
        "find",
        "finish",
        "invia",
        "imposta",
        "incolla",
        "leggi",
        "manda",
        "modifica",
        "navigate",
        "open",
        "perform",
        "please",
        "rename",
        "read",
        "rinomina",
        "requested",
        "run",
        "salva",
        "save",
        "search",
        "select",
        "seleziona",
        "send",
        "set",
        "submit",
        "type",
        "turn",
        "copia",
        "copy",
        "move",
        "sposta",
        "scrivi",
        "write",
    }
)
_OBJECTIVE_STOPWORDS = frozenset(
    {
        "allowed",
        "approved",
        "and",
        "con",
        "della",
        "delle",
        "dello",
        "dopo",
        "esegui",
        "favore",
        "following",
        "for",
        "gli",
        "i",
        "il",
        "in",
        "inside",
        "it",
        "la",
        "le",
        "lo",
        "nella",
        "nelle",
        "nello",
        "operator",
        "operation",
        "per",
        "prima",
        "quella",
        "quello",
        "questo",
        "then",
        "the",
        "to",
        "un",
        "una",
        "using",
        "without",
        "with",
        "while",
        "your",
        "keep",
        "keeping",
        "mantieni",
        "mantenendo",
        "senza",
    }
)
_POLARITY_TOKENS = frozenset(
    {
        "activate",
        "activated",
        "attiva",
        "attivato",
        "disable",
        "disabled",
        "deactivate",
        "deactivated",
        "disattiva",
        "disattivato",
        "enable",
        "enabled",
        "false",
        "no",
        "off",
        "on",
        "true",
        "yes",
    }
)
_EVIDENCE_STOPWORDS = frozenset(
    {
        "after",
        "and",
        "are",
        "been",
        "being",
        "browser",
        "button",
        "completed",
        "current",
        "done",
        "from",
        "for",
        "has",
        "have",
        "into",
        "label",
        "observation",
        "operation",
        "page",
        "reads",
        "result",
        "shows",
        "successful",
        "successfully",
        "text",
        "that",
        "the",
        "their",
        "there",
        "these",
        "this",
        "through",
        "tool",
        "value",
        "visible",
        "window",
        "with",
    }
)


@dataclass(frozen=True)
class CompletionDecision:
    """Host-side decision for a model-requested terminal outcome."""

    allowed: bool
    outcome: TaskOutcome | None
    reason: str


def tool_effect(
    tool_name: str,
    arguments: Mapping[str, Any] | None = None,
) -> ToolEffect:
    """Return the effect class used by completion verification."""

    if tool_name in _META_TOOLS:
        return "meta"
    if tool_name == "take_screenshot" and not (arguments or {}).get("save_path"):
        return "read"
    if tool_name in _READ_TOOLS:
        return "read"
    return "mutate"


def observation_is_error(observation: str) -> bool:
    """Classify common string-based tool failures without trusting model judgment."""

    raw_observation = str(observation).strip()
    if not raw_observation:
        return True

    try:
        structured = json.loads(raw_observation)
    except (json.JSONDecodeError, TypeError):
        structured = None
    if isinstance(structured, dict) and "return_code" in structured:
        return_code = structured.get("return_code")
        return not isinstance(return_code, int) or isinstance(return_code, bool) or return_code != 0

    normalized = " ".join(raw_observation.casefold().split())
    normalized = re.sub(r"^[^\w]+", "", normalized)
    if not normalized:
        return True
    return normalized.startswith(_FAILURE_PREFIXES)


def validate_tool_arguments(
    tool: Callable[..., Any],
    arguments: Mapping[str, Any],
    *,
    max_serialized_chars: int,
) -> str | None:
    """Return a stable rejection reason when a tool call violates its Python contract."""

    try:
        serialized = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return "arguments are not JSON-serializable"
    if len(serialized) > max_serialized_chars:
        return f"serialized arguments exceed the {max_serialized_chars}-character host limit"

    try:
        signature = inspect.signature(tool)
        bound = signature.bind(**dict(arguments))
    except TypeError as exc:
        return str(exc)

    try:
        hints = get_type_hints(tool)
    except (NameError, TypeError):
        hints = {}

    for name, value in bound.arguments.items():
        annotation = hints.get(name, signature.parameters[name].annotation)
        if not _value_matches_annotation(value, annotation):
            expected = _annotation_label(annotation)
            return f"argument '{name}' must match {expected}; received {type(value).__name__}"
    return None


def _value_matches_annotation(value: Any, annotation: Any) -> bool:
    if annotation in {Any, inspect.Parameter.empty}:
        return True

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in {Union, types.UnionType}:
        return any(_value_matches_annotation(value, option) for option in args)
    if origin is Literal:
        return value in args
    if origin is list:
        item_type = args[0] if args else Any
        return isinstance(value, list) and all(
            _value_matches_annotation(item, item_type) for item in value
        )
    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            return False
        if len(args) == 2 and args[1] is Ellipsis:
            return all(_value_matches_annotation(item, args[0]) for item in value)
        return len(value) == len(args) and all(
            _value_matches_annotation(item, expected)
            for item, expected in zip(value, args, strict=True)
        )
    if origin is dict:
        if not isinstance(value, Mapping):
            return False
        key_type, value_type = args if len(args) == 2 else (Any, Any)
        return all(
            _value_matches_annotation(key, key_type) and _value_matches_annotation(item, value_type)
            for key, item in value.items()
        )

    if annotation is bool:
        return isinstance(value, bool)
    if annotation is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if annotation is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if annotation is str:
        return isinstance(value, str)
    if isinstance(annotation, type):
        return isinstance(value, annotation)
    return True


def _annotation_label(annotation: Any) -> str:
    label = str(annotation)
    return label.removeprefix("typing.")


class ExecutionGuard:
    """Track progress, reject loops, and require grounded completion evidence."""

    def __init__(
        self,
        *,
        max_repeated_actions: int,
        evidence_min_chars: int,
        objective: str = "",
        trusted_context: str = "",
        permission_tier: str = "",
        available_tool_names: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        self.max_repeated_actions = max_repeated_actions
        self.evidence_min_chars = evidence_min_chars
        self.objective = str(objective)
        self.trusted_context = str(trusted_context)
        self.permission_tier = str(permission_tier).strip().casefold()
        self.available_tool_names = frozenset(available_tool_names)
        self.perception_index = 0
        self.current_perception_fingerprint = ""
        self.current_ui_tree = ""
        self._action_attempt_counts: dict[str, int] = {}
        self.successful_tool_count = 0
        self.last_tool_name = ""
        self.last_tool_succeeded: bool | None = None
        self.last_tool_observation = ""
        self.last_successful_observation = ""
        self._last_mutation_perception_index: int | None = None
        self._last_mutation_fingerprint = ""
        self._last_mutation_ui_tree = ""
        self._last_mutation_tool = ""
        self._last_mutation_arguments: dict[str, Any] = {}
        self._last_mutation_browser_url = ""
        self._last_browser_url = ""
        self._read_verified_after_mutation = False
        self._verification_observation = ""
        self._read_observations: deque[str] = deque(maxlen=16)

    def note_perception(self, screenshot: Any, ui_tree: str) -> None:
        """Record a fresh frame and update post-action verification state."""

        self.perception_index += 1
        self.current_ui_tree = str(ui_tree)
        self.current_perception_fingerprint = _perception_fingerprint(screenshot, ui_tree)

    def reject_repeated_action(self, tool_name: str, arguments: Mapping[str, Any]) -> str | None:
        """Reject the same action against the same observed state after a bounded retry."""

        if tool_effect(tool_name, arguments) == "meta":
            return None
        canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
        progress_fingerprint = _progress_fingerprint(self.current_ui_tree)
        action_key = hashlib.sha256(
            (f"{tool_name}\x1f{canonical}\x1f{progress_fingerprint}").encode(
                "utf-8", errors="replace"
            )
        ).hexdigest()
        attempts = self._action_attempt_counts.get(action_key, 0) + 1
        self._action_attempt_counts[action_key] = attempts
        if len(self._action_attempt_counts) > 256:
            oldest_key = next(iter(self._action_attempt_counts))
            del self._action_attempt_counts[oldest_key]

        if attempts <= self.max_repeated_actions:
            return None
        return (
            "STAGNATION GUARD: the same tool and arguments were requested against an "
            "unchanged observed state. Choose a different tool, refine the target, or report "
            "a blocker."
        )

    def record_tool_result(
        self,
        *,
        tool_name: str,
        observation: str,
        succeeded: bool,
        arguments: Mapping[str, Any] | None = None,
    ) -> None:
        """Record one concrete tool result for progress and completion checks."""

        effect = tool_effect(tool_name, arguments)
        if effect == "meta":
            return

        self.last_tool_name = tool_name
        self.last_tool_succeeded = succeeded
        self.last_tool_observation = str(observation)
        if not succeeded:
            return

        self.successful_tool_count += 1
        self.last_successful_observation = str(observation)
        if effect == "mutate":
            self._read_observations.clear()
            self._last_mutation_perception_index = self.perception_index
            self._last_mutation_fingerprint = self.current_perception_fingerprint
            self._last_mutation_ui_tree = self.current_ui_tree
            self._last_mutation_tool = tool_name
            self._last_mutation_arguments = dict(arguments or {})
            self._last_mutation_browser_url = (
                _extract_http_url(self.current_ui_tree) or self._last_browser_url
            )
            self._read_verified_after_mutation = False
            self._verification_observation = ""
            if tool_name in _SELF_VERIFYING_MUTATIONS:
                self._read_verified_after_mutation = True
                self._verification_observation = str(observation)
        elif self._last_mutation_perception_index is None:
            self._read_observations.append(str(observation))
        elif self._is_compatible_read_verifier(
            tool_name,
            arguments or {},
            observation=str(observation),
        ):
            self._read_verified_after_mutation = True
            self._verification_observation = str(observation)
        if tool_name == "browser_get_current_url":
            self._last_browser_url = _extract_http_url(str(observation))

    def evaluate_completion(
        self,
        *,
        outcome: Any,
        summary: Any,
        evidence: Any,
    ) -> CompletionDecision:
        """Validate a terminal request against host-observed execution state."""

        if outcome not in {"completed", "blocked"}:
            return CompletionDecision(
                False,
                None,
                "outcome must be exactly 'completed' or 'blocked'",
            )
        normalized_summary = str(summary).strip()
        normalized_evidence = str(evidence).strip()
        if not normalized_summary:
            return CompletionDecision(False, None, "summary cannot be empty")
        if len(normalized_evidence) < self.evidence_min_chars:
            return CompletionDecision(
                False,
                None,
                f"evidence must contain at least {self.evidence_min_chars} characters",
            )
        if normalized_evidence.casefold() in _GENERIC_EVIDENCE:
            return CompletionDecision(
                False,
                None,
                "evidence is generic; quote a concrete observation, UI label, value, or URL",
            )

        typed_outcome: TaskOutcome = outcome
        if typed_outcome == "blocked":
            capability_conflict = self._blocked_capability_conflict(normalized_evidence)
            if capability_conflict:
                return CompletionDecision(False, None, capability_conflict)
            if not _evidence_is_grounded(
                normalized_evidence,
                [
                    self.current_ui_tree,
                    self.last_tool_observation,
                    self.trusted_context,
                ],
            ):
                return CompletionDecision(
                    False,
                    None,
                    "blocker evidence is not grounded in the current UI, a tool result, or "
                    "the trusted capability context",
                )
            return CompletionDecision(True, "blocked", "specific blocker reported")

        if self.successful_tool_count == 0:
            if not _evidence_is_grounded(normalized_evidence, [self.current_ui_tree]):
                return CompletionDecision(
                    False,
                    None,
                    "no successful tool result exists and the evidence is not grounded in the "
                    "current UI observation",
                )
            if not _summary_is_supported(normalized_summary, normalized_evidence):
                return CompletionDecision(
                    False,
                    None,
                    "the completion summary is not supported by the supplied evidence",
                )
            if not _objective_is_supported(self.objective, [self.current_ui_tree]):
                return CompletionDecision(
                    False,
                    None,
                    "the observed state does not satisfy the operator objective",
                )
            return CompletionDecision(True, "completed", "initial state verified by perception")

        if self.last_tool_succeeded is not True:
            return CompletionDecision(
                False,
                None,
                "the most recent concrete tool failed; recover or report a blocker",
            )

        verification_sources = [
            self.current_ui_tree,
            *(self._read_observations or [self.last_successful_observation]),
        ]
        if self._last_mutation_perception_index is not None:
            has_fresh_perception = self.perception_index > self._last_mutation_perception_index
            perception_changed = (
                self.current_perception_fingerprint != self._last_mutation_fingerprint
            )
            if not has_fresh_perception:
                return CompletionDecision(
                    False,
                    None,
                    "capture a fresh perception after the last state-changing action",
                )
            if self._read_verified_after_mutation:
                verification_sources = [self._verification_observation]
            elif perception_changed:
                if not _evidence_has_new_support(
                    normalized_evidence,
                    summary=normalized_summary,
                    current_source=self.current_ui_tree,
                    previous_source=self._last_mutation_ui_tree,
                ):
                    return CompletionDecision(
                        False,
                        None,
                        "the evidence was already present before the last state-changing action",
                    )
                verification_sources = [self.current_ui_tree]
            else:
                return CompletionDecision(
                    False,
                    None,
                    "the observed state did not change after the last action; use a read-only "
                    "verification tool or report a blocker",
                )

        if not _evidence_is_grounded(normalized_evidence, verification_sources):
            return CompletionDecision(
                False,
                None,
                "evidence is not grounded in the current verification source",
            )
        if not _summary_is_supported(normalized_summary, normalized_evidence):
            return CompletionDecision(
                False,
                None,
                "the completion summary is not supported by the supplied evidence",
            )
        objective_sources = list(verification_sources)
        if self._last_mutation_tool.startswith("browser_"):
            objective_sources.append(self.current_ui_tree)
        if not _objective_is_supported(self.objective, objective_sources):
            return CompletionDecision(
                False,
                None,
                "the verification source does not satisfy the operator objective",
            )

        return CompletionDecision(True, "completed", "completion evidence verified")

    def prompt_context(self) -> str:
        """Return a compact trusted summary for the next model decision."""

        if self.last_tool_succeeded is None:
            last_result = "none"
        else:
            last_result = "success" if self.last_tool_succeeded else "failure"
        if self._last_mutation_perception_index is None:
            mutation_state = "no state-changing action recorded"
        else:
            fresh = self.perception_index > self._last_mutation_perception_index
            changed = self.current_perception_fingerprint != self._last_mutation_fingerprint
            mutation_state = (
                f"fresh perception after mutation={str(fresh).lower()}, "
                f"observed state changed={str(changed).lower()}, "
                f"read verification={str(self._read_verified_after_mutation).lower()}"
            )
        return (
            f"successful concrete tools={self.successful_tool_count}; "
            f"last concrete tool={self.last_tool_name or 'none'}; "
            f"last result={last_result}; {mutation_state}"
        )

    def _is_compatible_read_verifier(
        self,
        read_tool_name: str,
        read_arguments: Mapping[str, Any],
        *,
        observation: str,
    ) -> bool:
        compatible_tools = _READ_VERIFIERS_BY_MUTATION.get(
            self._last_mutation_tool,
            frozenset(),
        )
        if read_tool_name not in compatible_tools:
            return False
        if read_tool_name == "browser_get_current_url":
            if (
                self._last_mutation_tool == "browser_find_and_type"
                and self._last_mutation_arguments.get("press_enter") is not True
            ):
                return False
            verified_url = _extract_http_url(observation)
            return bool(
                verified_url
                and self._last_mutation_browser_url
                and verified_url != self._last_mutation_browser_url
            )
        if self._last_mutation_tool == "write_file":
            written_path = self._last_mutation_arguments.get("file_path")
            if read_tool_name == "read_file":
                return _same_path(written_path, read_arguments.get("file_path"))
            if read_tool_name == "list_files":
                return _same_parent_directory(
                    written_path,
                    read_arguments.get("directory_path", "."),
                )
        if self._last_mutation_tool == "take_screenshot":
            return _same_parent_directory(
                self._last_mutation_arguments.get("save_path"),
                read_arguments.get("directory_path", "."),
            )
        return True

    def _blocked_capability_conflict(self, evidence: str) -> str | None:
        normalized = evidence.casefold()
        tier_claims = set(
            re.findall(
                r"\bpermission\s+tier(?:\s+is\s+|\s*[=:]\s*|\s+)[`'\"]?"
                r"(observe|interact|system)\b",
                normalized,
            )
        )
        if self.permission_tier and tier_claims and tier_claims != {self.permission_tier}:
            return (
                "blocker evidence names a permission tier that does not match the "
                "host configuration"
            )

        unavailable_claims: set[str] = set()
        unavailable_claims.update(
            re.findall(
                r"(?:does\s+not\s+expose|not\s+available|unavailable|missing)"
                r"\s+(?:the\s+)?[`'\"]?([a-z][a-z0-9_]*)",
                normalized,
            )
        )
        unavailable_claims.update(
            re.findall(
                r"\b([a-z][a-z0-9_]*)\s+(?:tool\s+)?(?:is\s+)?"
                r"(?:not\s+available|unavailable|missing)\b",
                normalized,
            )
        )
        contradicted = sorted(unavailable_claims & self.available_tool_names)
        if contradicted:
            return "blocker evidence claims an available tool is unavailable: " + ", ".join(
                contradicted
            )
        return None


def _perception_fingerprint(screenshot: Any, ui_tree: str) -> str:
    digest = hashlib.sha256()
    normalized_tree = " ".join(str(ui_tree).split())
    digest.update(normalized_tree.encode("utf-8", errors="replace"))
    try:
        thumbnail = screenshot.convert("L").resize((32, 32))
        digest.update(thumbnail.tobytes())
    except (AttributeError, OSError, ValueError, TypeError):
        digest.update(type(screenshot).__qualname__.encode("utf-8", errors="replace"))
    return digest.hexdigest()


def _progress_fingerprint(ui_tree: str) -> str:
    """Fingerprint semantic UI state while ignoring clocks and animation counters."""

    tokens = [
        token.casefold()
        for token in re.findall(r"[\w.-]+", str(ui_tree))
        if not re.fullmatch(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)", token)
    ]
    normalized = " ".join(tokens)
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()


def _evidence_is_grounded(evidence: str, sources: list[str]) -> bool:
    source_tokens = _distinctive_tokens(" ".join(sources))
    if not source_tokens:
        return False
    evidence_tokens = _distinctive_tokens(evidence)
    matched_tokens = evidence_tokens & source_tokens
    return len(matched_tokens) >= 2


def _evidence_has_new_support(
    evidence: str,
    *,
    summary: str,
    current_source: str,
    previous_source: str,
) -> bool:
    evidence_tokens = _distinctive_tokens(evidence)
    current_matches = evidence_tokens & _distinctive_tokens(current_source)
    previous_tokens = _distinctive_tokens(previous_source)
    new_matches = current_matches - previous_tokens
    summary_tokens = _distinctive_tokens(summary)
    return len(current_matches) >= 2 and any(
        _tokens_are_related(new_token, summary_token)
        for new_token in new_matches
        for summary_token in summary_tokens
    )


def _summary_is_supported(summary: str, evidence: str) -> bool:
    """Require the claimed outcome to share a concrete subject/result with evidence."""

    evidence_tokens = _distinctive_tokens(evidence)
    claim_tokens = _distinctive_tokens(summary)
    if not claim_tokens:
        return False
    return any(
        _tokens_are_related(claim_token, evidence_token)
        for claim_token in claim_tokens
        for evidence_token in evidence_tokens
    )


def _objective_is_supported(objective: str, sources: list[str]) -> bool:
    objective_tokens = _objective_anchor_tokens(objective)
    if not objective_tokens:
        return True
    source_tokens = {
        token.casefold() for token in re.findall(r"[\w.-]+", " ".join(sources)) if token
    }

    def supported(token: str) -> bool:
        return any(_tokens_are_related(token, source_token) for source_token in source_tokens)

    if not all(supported(anchor) for anchor in objective_tokens):
        return False

    normalized_objective = " ".join(str(objective).casefold().split())
    preserve_open = bool(
        re.search(
            r"(?:without\s+clos|do\s+not\s+clos|don't\s+clos|"
            r"senza\s+chiud|non\s+chiud|while\s+keep(?:ing)?\b.*\bopen|"
            r"\bkeep\b.*\bopen|manten\w*\b.*\bapert)",
            normalized_objective,
        )
    )
    if preserve_open:
        source_text = " ".join(sources).casefold()
        if re.search(r"\b(?:closed|chiuso|chiusa)\b", source_text):
            return False
        if not re.search(r"\b(?:open|opened|aperto|aperta|visible|visibile)\b", source_text):
            return False
    return True


def _objective_anchor_tokens(value: str) -> set[str]:
    """Extract exact entities, values, destinations, and polarity from a command."""

    raw_value = str(value)
    original_tokens = re.findall(r"[\w.-]+", raw_value)
    normalized_tokens = [token.casefold() for token in original_tokens]
    anchors = {
        token
        for token in _semantic_tokens(raw_value)
        if token not in _OBJECTIVE_ACTION_WORDS and token not in _OBJECTIVE_STOPWORDS
    }

    # Numeric literals and short uppercase identifiers (A, UK, MFA) carry meaning
    # even though they are too short for ordinary fuzzy token matching.
    anchors.update(
        normalized
        for original, normalized in zip(original_tokens, normalized_tokens, strict=True)
        if _is_numeric_literal(normalized) or (original.isupper() and 1 <= len(original) <= 3)
    )

    # In "change A to B", A is prior state rather than a required postcondition.
    if (
        normalized_tokens
        and normalized_tokens[0] in {"cambia", "change", "modifica"}
        and "to" in normalized_tokens
    ):
        transition_index = len(normalized_tokens) - 1 - normalized_tokens[::-1].index("to")
        for original, normalized in zip(
            original_tokens[1:transition_index],
            normalized_tokens[1:transition_index],
            strict=True,
        ):
            if _is_numeric_literal(normalized) or (original.isupper() and 1 <= len(original) <= 3):
                anchors.discard(normalized)

    # Quoted values are operator-authored literals and must survive token length filters.
    for quoted_value in re.findall(r"""["'`](.+?)["'`]""", raw_value):
        anchors.update(
            token.casefold()
            for token in re.findall(r"[\w.-]+", quoted_value)
            if token.casefold() not in _OBJECTIVE_STOPWORDS
        )

    # Imperative commands commonly place a short value last: "set color red",
    # "change A to B", "imposta colore blu".
    if (
        normalized_tokens
        and normalized_tokens[0] in _OBJECTIVE_ACTION_WORDS
        and normalized_tokens[-1] not in _OBJECTIVE_ACTION_WORDS
        and normalized_tokens[-1] not in _OBJECTIVE_STOPWORDS
    ):
        anchors.add(normalized_tokens[-1])
    return anchors


def _distinctive_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for original in re.findall(r"[\w.-]+", str(value)):
        token = original.casefold()
        if token in _EVIDENCE_STOPWORDS:
            continue
        if (
            len(token) >= 4
            or _is_numeric_literal(token)
            or (original.isupper() and 1 <= len(original) <= 3)
        ):
            tokens.add(token)
    return tokens


def _semantic_tokens(value: str) -> set[str]:
    tokens = _distinctive_tokens(value)
    tokens.update(
        token
        for token in re.findall(r"[\w.-]+", str(value).casefold())
        if token in _POLARITY_TOKENS
    )
    return tokens


def _tokens_are_related(left: str, right: str) -> bool:
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= 4 and len(longer) - len(shorter) <= 3 and longer.startswith(shorter)


def _is_numeric_literal(value: str) -> bool:
    return re.fullmatch(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)", value) is not None


def _normalized_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return Path(value).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _same_path(left: Any, right: Any) -> bool:
    left_path = _normalized_path(left)
    right_path = _normalized_path(right)
    if left_path is None or right_path is None:
        return False
    return os.path.normcase(str(left_path)) == os.path.normcase(str(right_path))


def _same_parent_directory(file_value: Any, directory_value: Any) -> bool:
    file_path = _normalized_path(file_value)
    directory_path = _normalized_path(directory_value)
    if file_path is None or directory_path is None:
        return False
    return os.path.normcase(str(file_path.parent)) == os.path.normcase(str(directory_path))


def _extract_http_url(value: str) -> str:
    match = re.search(r"https?://[^\s<>\"']+", str(value), flags=re.IGNORECASE)
    if match is None:
        return ""
    return match.group(0).rstrip(".,;)]}").casefold()
