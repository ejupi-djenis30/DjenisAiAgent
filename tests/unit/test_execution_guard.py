from __future__ import annotations

from typing import Literal

import pytest

from src.orchestration import execution_guard as guard_module
from src.orchestration.execution_guard import (
    ExecutionGuard,
    observation_is_error,
    validate_tool_arguments,
)


def _tool(
    target: str,
    *,
    attempts: int = 1,
    outcome: Literal["safe", "unsafe"] = "safe",
) -> str:
    return f"{target}:{attempts}:{outcome}"


def _guard() -> ExecutionGuard:
    return ExecutionGuard(
        max_repeated_actions=2,
        evidence_min_chars=12,
        objective="Complete the requested operation",
        trusted_context="permission tier observe; click unavailable",
        permission_tier="observe",
        available_tool_names={"finish_task", "read_file"},
    )


def test_validate_tool_arguments_accepts_declared_contract() -> None:
    assert (
        validate_tool_arguments(
            _tool,
            {"target": "Save", "attempts": 2, "outcome": "safe"},
            max_serialized_chars=256,
        )
        is None
    )


def test_validate_tool_arguments_rejects_missing_extra_and_wrong_type() -> None:
    missing = validate_tool_arguments(_tool, {}, max_serialized_chars=256)
    extra = validate_tool_arguments(
        _tool, {"target": "Save", "invented": True}, max_serialized_chars=256
    )
    wrong_type = validate_tool_arguments(
        _tool, {"target": "Save", "attempts": "two"}, max_serialized_chars=256
    )
    wrong_literal = validate_tool_arguments(
        _tool, {"target": "Save", "outcome": "maybe"}, max_serialized_chars=256
    )

    assert missing and "target" in missing
    assert extra and "invented" in extra
    assert wrong_type and "attempts" in wrong_type
    assert wrong_literal and "outcome" in wrong_literal


def test_validate_tool_arguments_enforces_serialized_size() -> None:
    error = validate_tool_arguments(
        _tool,
        {"target": "x" * 100},
        max_serialized_chars=32,
    )

    assert error and "host limit" in error


def test_observation_error_classifier_handles_string_tool_failures() -> None:
    assert observation_is_error("Error: target missing")
    assert observation_is_error("Could not connect to the browser.")
    assert observation_is_error("Selenium is unavailable.")
    assert observation_is_error("❌ Invalid key: mystery.")
    assert observation_is_error("Browser typing failed. Check the logs.")
    assert observation_is_error('{"stdout": "", "stderr": "denied", "return_code": -1}')
    assert not observation_is_error(
        '{"stdout": "the word failed is data", "stderr": "", "return_code": 0}'
    )
    assert not observation_is_error("Current URL: https://example.com/dashboard")


def test_repeated_action_is_rejected_only_against_unchanged_state() -> None:
    guard = _guard()
    guard.note_perception(object(), "Window: Settings")

    assert guard.reject_repeated_action("click", {"element_id": "save"}) is None
    assert guard.reject_repeated_action("click", {"element_id": "save"}) is None
    assert "STAGNATION GUARD" in (
        guard.reject_repeated_action("click", {"element_id": "save"}) or ""
    )

    guard.note_perception(object(), "Window: Settings | Status: Saved")
    assert guard.reject_repeated_action("click", {"element_id": "save"}) is None


def test_repeated_action_ignores_volatile_clock_values() -> None:
    guard = _guard()

    for second in range(2):
        guard.note_perception(object(), f"Window: Settings | Clock 12:00:0{second}")
        assert guard.reject_repeated_action("click", {"element_id": "save"}) is None

    guard.note_perception(object(), "Window: Settings | Clock 12:00:02")
    assert "STAGNATION GUARD" in (
        guard.reject_repeated_action("click", {"element_id": "save"}) or ""
    )


def test_completion_can_verify_an_already_satisfied_initial_state() -> None:
    guard = _guard()
    guard.note_perception(object(), "Application: Editor | Status: Document saved")

    decision = guard.evaluate_completion(
        outcome="completed",
        summary="The document is already saved.",
        evidence='UI label reads "Status: Document saved".',
    )

    assert decision.allowed is True
    assert decision.outcome == "completed"


def test_completion_rejects_generic_or_ungrounded_evidence() -> None:
    guard = _guard()
    guard.note_perception(object(), "Application: Editor")

    generic = guard.evaluate_completion(
        outcome="completed",
        summary="Finished.",
        evidence="task completed",
    )
    invented = guard.evaluate_completion(
        outcome="completed",
        summary="Finished.",
        evidence="The invoice total is exactly 42.50 CHF.",
    )

    assert generic.allowed is False
    assert invented.allowed is False


def test_completion_rejects_one_weak_match_and_an_unrelated_summary() -> None:
    guard = _guard()
    guard.note_perception(
        object(),
        "Dialog: Preferences | Status: Changes saved | Clock: 12:01",
    )

    weak = guard.evaluate_completion(
        outcome="completed",
        summary="Preferences saved.",
        evidence="The editor is visible now.",
    )
    unrelated = guard.evaluate_completion(
        outcome="completed",
        summary="The email was sent.",
        evidence='Current UI reads "Status: Changes saved".',
    )

    assert weak.allowed is False
    assert unrelated.allowed is False
    assert "summary" in unrelated.reason


def test_mutation_requires_changed_perception_or_read_verification() -> None:
    guard = _guard()
    guard.note_perception(object(), "Page: Checkout | URL: https://example.test/checkout")
    guard.record_tool_result(
        tool_name="browser_find_and_click",
        observation="Browser element clicked successfully.",
        succeeded=True,
    )
    guard.note_perception(object(), "Page: Checkout | URL: https://example.test/checkout")

    unverified = guard.evaluate_completion(
        outcome="completed",
        summary="Checkout submitted.",
        evidence="Browser element clicked successfully.",
    )
    assert unverified.allowed is False
    assert "did not change" in unverified.reason

    guard.record_tool_result(
        tool_name="browser_get_current_url",
        observation="Current URL: https://example.test/checkout/confirmed",
        succeeded=True,
    )
    verified = guard.evaluate_completion(
        outcome="completed",
        summary="Checkout submitted.",
        evidence="Current URL: https://example.test/checkout/confirmed",
    )

    assert verified.allowed is True


def test_unrelated_read_tool_cannot_verify_a_mutation() -> None:
    guard = _guard()
    guard.note_perception(object(), "Window: Editor | Button: Save")
    guard.record_tool_result(
        tool_name="click",
        observation="Clicked Save.",
        succeeded=True,
        arguments={"element_id": "save"},
    )
    guard.note_perception(object(), "Window: Editor | Button: Save")
    guard.record_tool_result(
        tool_name="list_files",
        observation="Directory contains report.txt",
        succeeded=True,
    )

    decision = guard.evaluate_completion(
        outcome="completed",
        summary="The document was saved.",
        evidence="Directory contains report.txt",
    )

    assert decision.allowed is False
    assert "did not change" in decision.reason


def test_filesystem_verifier_must_read_the_written_resource(tmp_path) -> None:
    target = tmp_path / "target.txt"
    unrelated = tmp_path / "README.md"
    guard = _guard()
    guard.note_perception(object(), "Window: Terminal")
    guard.record_tool_result(
        tool_name="write_file",
        observation=f"Successfully wrote 5 characters to '{target}'.",
        succeeded=True,
        arguments={"file_path": str(target), "content": "hello"},
    )
    guard.note_perception(object(), "Window: Terminal")
    guard.record_tool_result(
        tool_name="read_file",
        observation="Content of 'README.md': Project documentation",
        succeeded=True,
        arguments={"file_path": str(unrelated)},
    )

    rejected = guard.evaluate_completion(
        outcome="completed",
        summary="Project documentation was written.",
        evidence="README.md contains Project documentation",
    )
    assert rejected.allowed is False

    guard.record_tool_result(
        tool_name="read_file",
        observation="Content of 'target.txt': hello",
        succeeded=True,
        arguments={"file_path": str(target)},
    )
    accepted = guard.evaluate_completion(
        outcome="completed",
        summary="The target file contains hello.",
        evidence="target.txt content is hello",
    )
    assert accepted.allowed is True


def test_self_consistent_wrong_value_cannot_redefine_the_objective(tmp_path) -> None:
    target = tmp_path / "foo.txt"
    guard = ExecutionGuard(
        max_repeated_actions=2,
        evidence_min_chars=12,
        objective="Write hello to foo.txt",
    )
    guard.note_perception(object(), "Window: Terminal")
    guard.record_tool_result(
        tool_name="write_file",
        observation=f"Successfully wrote 7 characters to '{target}'.",
        succeeded=True,
        arguments={"file_path": str(target), "content": "goodbye"},
    )
    guard.note_perception(object(), "Window: Terminal")
    guard.record_tool_result(
        tool_name="read_file",
        observation=f"Content of '{target.name}': goodbye",
        succeeded=True,
        arguments={"file_path": str(target)},
    )

    decision = guard.evaluate_completion(
        outcome="completed",
        summary="The file contains goodbye.",
        evidence=f"{target.name} content is goodbye",
    )

    assert decision.allowed is False
    assert "operator objective" in decision.reason


def test_wrong_destination_and_polarity_cannot_satisfy_the_objective() -> None:
    recipient = ExecutionGuard(
        max_repeated_actions=2,
        evidence_min_chars=12,
        objective="Send report to Alice",
    )
    recipient.note_perception(object(), "Compose report | Recipient: Alice | Button: Send")
    recipient.record_tool_result(
        tool_name="click",
        observation="Clicked Send.",
        succeeded=True,
        arguments={"element_id": "send"},
    )
    recipient.note_perception(object(), "Message: Report sent to Bob")

    wrong_recipient = recipient.evaluate_completion(
        outcome="completed",
        summary="Report sent to Bob.",
        evidence="Message reads Report sent to Bob",
    )
    assert wrong_recipient.allowed is False
    assert "operator objective" in wrong_recipient.reason

    polarity = ExecutionGuard(
        max_repeated_actions=2,
        evidence_min_chars=12,
        objective="Turn off WiFi",
    )
    polarity.note_perception(object(), "WiFi network is on and connected")
    wrong_polarity = polarity.evaluate_completion(
        outcome="completed",
        summary="WiFi is on and connected.",
        evidence="WiFi network is on and connected",
    )
    assert wrong_polarity.allowed is False
    assert "operator objective" in wrong_polarity.reason


@pytest.mark.parametrize(
    ("objective", "wrong_state", "correct_state"),
    [
        ("Type 123", "Input value 456 entered", "Input value 123 entered"),
        ("Set value 42", "Value 41 confirmed", "Value 42 confirmed"),
        ("Set scale 0.2", "Scale 0.5 confirmed", "Scale 0.2 confirmed"),
        ("Set color red", "Color selected blue", "Color selected red"),
        ("Change A to B", "Value C selected", "Value B selected"),
        ("Change US to UK", "Region US selected", "Region UK selected"),
        (
            "Imposta il colore rosso",
            "Colore selezionato blu",
            "Colore selezionato rosso",
        ),
    ],
)
def test_objective_preserves_short_and_numeric_values(
    objective: str,
    wrong_state: str,
    correct_state: str,
) -> None:
    assert guard_module._objective_is_supported(objective, [wrong_state]) is False
    assert guard_module._objective_is_supported(objective, [correct_state]) is True


def test_numeric_value_can_ground_fresh_completion_evidence() -> None:
    guard = ExecutionGuard(
        max_repeated_actions=2,
        evidence_min_chars=12,
        objective="Set value 42",
    )
    guard.note_perception(object(), "Form | Value input empty")
    guard.record_tool_result(
        tool_name="type_text",
        observation="Typed 2 characters.",
        succeeded=True,
        arguments={"element_id": "value", "text": "42"},
    )
    guard.note_perception(object(), "Form | Value 42 confirmed")

    decision = guard.evaluate_completion(
        outcome="completed",
        summary="Value 42 confirmed.",
        evidence="Value 42 confirmed in form",
    )

    assert decision.allowed is True


def test_multiple_read_observations_can_jointly_verify_the_objective() -> None:
    guard = ExecutionGuard(
        max_repeated_actions=2,
        evidence_min_chars=12,
        objective="Read alpha.txt and beta.txt",
    )
    guard.note_perception(object(), "Terminal")
    guard.record_tool_result(
        tool_name="read_file",
        observation="Content of alpha.txt: first",
        succeeded=True,
        arguments={"file_path": "alpha.txt"},
    )
    guard.record_tool_result(
        tool_name="read_file",
        observation="Content of beta.txt: second",
        succeeded=True,
        arguments={"file_path": "beta.txt"},
    )

    decision = guard.evaluate_completion(
        outcome="completed",
        summary="Both files were read: alpha first and beta second.",
        evidence="alpha.txt contains first; beta.txt contains second",
    )

    assert decision.allowed is True


def test_preservative_constraint_accepts_open_document_and_rejects_closed_state() -> None:
    open_document = ExecutionGuard(
        max_repeated_actions=2,
        evidence_min_chars=12,
        objective="Save the document without closing it",
    )
    open_document.note_perception(
        object(),
        "Document open | Status: Document saved",
    )
    accepted = open_document.evaluate_completion(
        outcome="completed",
        summary="The document is saved and open.",
        evidence="Document open with Status Document saved",
    )
    assert accepted.allowed is True

    closed_document = ExecutionGuard(
        max_repeated_actions=2,
        evidence_min_chars=12,
        objective="Save the document without closing it",
    )
    closed_document.note_perception(
        object(),
        "Document closed | Status: Document saved",
    )
    rejected = closed_document.evaluate_completion(
        outcome="completed",
        summary="The document is saved and closed.",
        evidence="Document closed with Status Document saved",
    )
    assert rejected.allowed is False
    assert "operator objective" in rejected.reason


def test_preservative_constraint_understands_keep_open_wording() -> None:
    objective = "Save the document while keeping it open"

    assert guard_module._objective_is_supported(
        objective,
        ["Document saved | Document remains open"],
    )
    assert not guard_module._objective_is_supported(
        objective,
        ["Document saved | Document closed"],
    )


def test_path_correlation_respects_platform_case_semantics(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(guard_module.os.path, "normcase", lambda value: value)

    assert not guard_module._same_path(
        str(tmp_path / "Report.txt"),
        str(tmp_path / "report.txt"),
    )


def test_browser_url_verifies_submit_but_not_plain_typing() -> None:
    plain_type = _guard()
    plain_type.note_perception(
        object(),
        "Page: Search | URL: https://example.test/search | Input: empty",
    )
    plain_type.record_tool_result(
        tool_name="browser_find_and_type",
        observation="Typed 5 characters.",
        succeeded=True,
        arguments={"query": "search", "text": "hello", "press_enter": False},
    )
    plain_type.note_perception(
        object(),
        "Page: Search | URL: https://example.test/search | Input: empty",
    )
    plain_type.record_tool_result(
        tool_name="browser_get_current_url",
        observation="Current URL: https://example.test/search",
        succeeded=True,
    )

    rejected = plain_type.evaluate_completion(
        outcome="completed",
        summary="The search was submitted.",
        evidence="Current URL: https://example.test/search",
    )
    assert rejected.allowed is False

    submitted = _guard()
    submitted.note_perception(
        object(),
        "Page: Search | URL: https://example.test/search | Input: empty",
    )
    submitted.record_tool_result(
        tool_name="browser_find_and_type",
        observation="Pressed Enter in the active browser element.",
        succeeded=True,
        arguments={"query": "search", "text": "hello", "press_enter": True},
    )
    submitted.note_perception(
        object(),
        "Page: Search | URL: https://example.test/search/results | Input: empty",
    )
    submitted.record_tool_result(
        tool_name="browser_get_current_url",
        observation="Current URL: https://example.test/search/results",
        succeeded=True,
    )

    accepted = submitted.evaluate_completion(
        outcome="completed",
        summary="The search results opened.",
        evidence="Current URL: https://example.test/search/results",
    )
    assert accepted.allowed is True


def test_unchanged_browser_url_cannot_verify_a_no_op_click() -> None:
    guard = _guard()
    guard.note_perception(
        object(),
        "Page: Dashboard | URL: https://example.test/dashboard | Button: Submit",
    )
    guard.record_tool_result(
        tool_name="browser_find_and_click",
        observation="Browser element clicked successfully.",
        succeeded=True,
        arguments={"query": "Submit"},
    )
    guard.note_perception(
        object(),
        "Page: Dashboard | URL: https://example.test/dashboard | Button: Submit",
    )
    guard.record_tool_result(
        tool_name="browser_get_current_url",
        observation="Current URL: https://example.test/dashboard",
        succeeded=True,
    )

    decision = guard.evaluate_completion(
        outcome="completed",
        summary="Dashboard submission completed.",
        evidence="Current URL: https://example.test/dashboard",
    )

    assert decision.allowed is False
    assert "did not change" in decision.reason


def test_changed_post_action_perception_allows_grounded_completion() -> None:
    guard = _guard()
    guard.note_perception(object(), "Dialog: Preferences | Button: Save")
    guard.record_tool_result(
        tool_name="click",
        observation="Clicked Save.",
        succeeded=True,
    )
    guard.note_perception(object(), "Dialog: Preferences | Status: Changes saved")

    decision = guard.evaluate_completion(
        outcome="completed",
        summary="Preferences saved.",
        evidence='Current UI label reads "Status: Changes saved".',
    )

    assert decision.allowed is True


def test_changed_frame_does_not_turn_an_action_acknowledgement_into_evidence() -> None:
    guard = _guard()
    guard.note_perception(object(), "Dialog: Preferences | Button: Save | Clock: 12:00")
    guard.record_tool_result(
        tool_name="click",
        observation="Clicked Save successfully.",
        succeeded=True,
    )
    guard.note_perception(object(), "Dialog: Preferences | Button: Save | Clock: 12:01")

    decision = guard.evaluate_completion(
        outcome="completed",
        summary="Preferences saved.",
        evidence="Clicked Save successfully.",
    )

    assert decision.allowed is False
    assert "evidence" in decision.reason


def test_dynamic_frame_change_cannot_reuse_preexisting_evidence() -> None:
    guard = _guard()
    guard.note_perception(
        object(),
        "Dialog: Preferences | Network: Online | Clock: frame-1200 | Button: Save",
    )
    guard.record_tool_result(
        tool_name="click",
        observation="Clicked Save.",
        succeeded=True,
        arguments={"element_id": "save"},
    )
    guard.note_perception(
        object(),
        "Dialog: Preferences | Network: Online | Clock: frame-1201 | Button: Save",
    )

    decision = guard.evaluate_completion(
        outcome="completed",
        summary="Preferences saved.",
        evidence="Preferences network clock frame-1201 is visible.",
    )

    assert decision.allowed is False
    assert "already present" in decision.reason


def test_self_verifying_command_and_in_memory_screenshot_can_complete() -> None:
    command = _guard()
    command.note_perception(object(), "Window: Terminal")
    command.record_tool_result(
        tool_name="run_shell_command",
        observation='{"stdout": "diagnostic healthy", "stderr": "", "return_code": 0}',
        succeeded=True,
        arguments={"command": "approved-diagnostic"},
    )
    command.note_perception(object(), "Window: Terminal")

    command_decision = command.evaluate_completion(
        outcome="completed",
        summary="The diagnostic is healthy.",
        evidence="stdout reports diagnostic healthy with return_code 0",
    )
    assert command_decision.allowed is True

    screenshot = _guard()
    screenshot.note_perception(object(), "Desktop: Ready")
    screenshot.record_tool_result(
        tool_name="take_screenshot",
        observation="Screenshot captured in memory (1920x1080); no file was written.",
        succeeded=True,
        arguments={"save_path": None},
    )
    screenshot_decision = screenshot.evaluate_completion(
        outcome="completed",
        summary="The screenshot was captured.",
        evidence="Screenshot captured in memory at 1920x1080.",
    )
    assert screenshot_decision.allowed is True


def test_latest_failed_tool_prevents_success() -> None:
    guard = _guard()
    guard.note_perception(object(), "Page: Report | Heading: Q2")
    guard.record_tool_result(
        tool_name="read_file",
        observation="Report heading: Q2",
        succeeded=True,
    )
    guard.record_tool_result(
        tool_name="read_file",
        observation="Error: report became unavailable",
        succeeded=False,
    )

    decision = guard.evaluate_completion(
        outcome="completed",
        summary="Report read.",
        evidence="Report heading: Q2",
    )

    assert decision.allowed is False
    assert "most recent" in decision.reason


def test_specific_blocker_is_a_distinct_terminal_outcome() -> None:
    guard = _guard()
    guard.note_perception(object(), "Window: Protected settings")

    decision = guard.evaluate_completion(
        outcome="blocked",
        summary="The configured tier excludes this action.",
        evidence="Permission tier observe does not expose the click tool.",
    )

    assert decision.allowed is True
    assert decision.outcome == "blocked"


def test_ungrounded_blocker_is_rejected() -> None:
    guard = _guard()
    guard.note_perception(object(), "Window: Editor | Status: Ready")

    decision = guard.evaluate_completion(
        outcome="blocked",
        summary="A remote approval is allegedly missing.",
        evidence="Finance director approval ticket 8821 is still pending.",
    )

    assert decision.allowed is False
    assert "blocker evidence" in decision.reason


def test_blocker_cannot_invent_the_permission_tier_or_hide_an_available_tool() -> None:
    guard = ExecutionGuard(
        max_repeated_actions=2,
        evidence_min_chars=12,
        trusted_context="permission tier interact; available tools: click, finish_task",
        permission_tier="interact",
        available_tool_names={"click", "finish_task"},
    )
    guard.note_perception(object(), "Window: Editor | Button: Save")

    wrong_tier = guard.evaluate_completion(
        outcome="blocked",
        summary="The permission tier prevents clicking.",
        evidence="Permission tier observe does not expose the click tool.",
    )
    hidden_tool = guard.evaluate_completion(
        outcome="blocked",
        summary="The click tool is unavailable.",
        evidence="The click tool is unavailable in Window Editor.",
    )

    assert wrong_tier.allowed is False
    assert "does not match" in wrong_tier.reason
    assert hidden_tool.allowed is False
    assert "available tool" in hidden_tool.reason


def test_permission_tier_claim_parser_handles_separators_without_backtracking() -> None:
    guard = _guard()

    for evidence in (
        "Permission tier is system.",
        "Permission tier: system.",
        "Permission tier = system.",
        "Permission tier system.",
    ):
        assert "does not match" in (guard._blocked_capability_conflict(evidence) or "")

    repeated_is = "Permission tier" + ("\t is" * 10_000) + " system."
    assert guard._blocked_capability_conflict(repeated_is) is None
