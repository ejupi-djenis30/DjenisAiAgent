"""Unit tests for src/action/browser_tools.py."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from PIL import Image

from src.action import browser_tools as browser_module


class _FakeChromeOptions:
    def __init__(self) -> None:
        self.experimental_options: dict[str, str] = {}

    def add_experimental_option(self, key: str, value: str) -> None:
        self.experimental_options[key] = value


class _FakeWait:
    def __init__(self, result=None, exception: Exception | None = None) -> None:
        self.result = result
        self.exception = exception

    def until(self, _condition):
        if self.exception is not None:
            raise self.exception
        return self.result


@pytest.fixture(autouse=True)
def reset_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(browser_module, "_driver", None)
    monkeypatch.setattr(browser_module, "require_safe_url", MagicMock())
    monkeypatch.setattr(browser_module, "validate_url_network_policy", MagicMock())


class TestDriverLifecycle:
    def test_returns_none_when_selenium_is_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", False)

        assert browser_module._get_or_create_driver() is None

    def test_reuses_existing_live_driver(self, monkeypatch: pytest.MonkeyPatch) -> None:
        driver = MagicMock()
        driver.title = "Example"
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_driver", driver)

        assert browser_module._get_or_create_driver() is driver

    def test_reconnects_with_edge_when_cached_driver_is_dead(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class DeadDriver:
            @property
            def title(self) -> str:
                raise RuntimeError("dead")

        edge_driver = MagicMock()
        webdriver_ns = SimpleNamespace(
            ChromeOptions=_FakeChromeOptions,
            EdgeOptions=_FakeChromeOptions,
            Edge=MagicMock(return_value=edge_driver),
            Chrome=MagicMock(),
        )

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "WebDriverException", RuntimeError)
        monkeypatch.setattr(browser_module, "_driver", DeadDriver())
        monkeypatch.setattr(browser_module, "webdriver", webdriver_ns)

        assert browser_module._get_or_create_driver() is edge_driver
        webdriver_ns.Edge.assert_called_once()

    def test_falls_back_to_chrome_when_edge_connection_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chrome_driver = MagicMock()
        webdriver_ns = SimpleNamespace(
            ChromeOptions=_FakeChromeOptions,
            EdgeOptions=_FakeChromeOptions,
            Edge=MagicMock(side_effect=RuntimeError("edge unavailable")),
            Chrome=MagicMock(return_value=chrome_driver),
        )

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "webdriver", webdriver_ns)
        monkeypatch.setattr(browser_module, "WebDriverException", RuntimeError)

        assert browser_module._get_or_create_driver() is chrome_driver
        webdriver_ns.Chrome.assert_called_once()

    def test_handles_webdriver_exception_during_connection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        webdriver_ns = SimpleNamespace(
            ChromeOptions=_FakeChromeOptions,
            EdgeOptions=_FakeChromeOptions,
            Edge=MagicMock(side_effect=RuntimeError("edge unavailable")),
            Chrome=MagicMock(side_effect=RuntimeError("cannot connect")),
        )

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "webdriver", webdriver_ns)
        monkeypatch.setattr(browser_module, "WebDriverException", RuntimeError)

        assert browser_module._get_or_create_driver() is None

    def test_uses_remote_selenium_when_remote_url_is_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        remote_driver = MagicMock()
        webdriver_ns = SimpleNamespace(
            ChromeOptions=_FakeChromeOptions,
            Remote=MagicMock(return_value=remote_driver),
        )

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "webdriver", webdriver_ns)
        monkeypatch.setattr(
            browser_module.config, "selenium_remote_url", "http://chrome:4444/wd/hub"
        )
        monkeypatch.setattr(browser_module.config, "browser_connection_mode", "remote-selenium")

        assert browser_module._get_or_create_driver() is remote_driver
        webdriver_ns.Remote.assert_called_once()


class TestBrowserActions:
    def test_is_browser_available_checks_driver(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: object())

        assert browser_module.is_browser_available() is True

    def test_find_and_click_returns_install_hint_when_selenium_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", False)

        assert "selenium" in browser_module.browser_find_and_click("search").lower()

    def test_find_and_click_returns_connection_error_when_driver_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: None)

        assert "Could not connect" in browser_module.browser_find_and_click("search")

    def test_get_browser_setup_hint_uses_remote_selenium_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            browser_module.config, "selenium_remote_url", "http://chrome:4444/wd/hub"
        )
        monkeypatch.setattr(browser_module.config, "browser_connection_mode", "remote-selenium")

        hint = browser_module.get_browser_setup_hint()

        assert "Selenium" in hint
        assert "http://chrome:4444/wd/hub" not in hint

    def test_xpath_literal_handles_both_quote_types(self) -> None:
        literal = browser_module._xpath_literal('Djenis\' "project"')

        assert literal.startswith("concat(")
        assert "Djenis" in literal

    def test_find_and_click_rejects_empty_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)

        assert "cannot be empty" in browser_module.browser_find_and_click("   ")

    def test_find_and_click_uses_first_clickable_match(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        element = MagicMock()
        driver = MagicMock()

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)
        monkeypatch.setattr(
            browser_module,
            "By",
            SimpleNamespace(NAME="NAME", ID="ID", CSS_SELECTOR="CSS", XPATH="XPATH"),
        )
        monkeypatch.setattr(
            browser_module, "EC", SimpleNamespace(element_to_be_clickable=lambda locator: locator)
        )
        monkeypatch.setattr(browser_module, "TimeoutException", RuntimeError)
        monkeypatch.setattr(
            browser_module, "WebDriverWait", lambda driver, timeout: _FakeWait(result=element)
        )

        result = browser_module.browser_find_and_click("Search")

        assert "clicked" in result.lower()
        element.click.assert_called_once()

    def test_find_and_click_returns_not_found_after_all_timeouts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        driver = MagicMock()
        timeout_error = RuntimeError("timeout")

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)
        monkeypatch.setattr(
            browser_module,
            "By",
            SimpleNamespace(NAME="NAME", ID="ID", CSS_SELECTOR="CSS", XPATH="XPATH"),
        )
        monkeypatch.setattr(
            browser_module, "EC", SimpleNamespace(element_to_be_clickable=lambda locator: locator)
        )
        monkeypatch.setattr(browser_module, "TimeoutException", RuntimeError)
        monkeypatch.setattr(
            browser_module,
            "WebDriverWait",
            lambda driver, timeout: _FakeWait(exception=timeout_error),
        )

        result = browser_module.browser_find_and_click("Search", timeout=5.0)

        assert "not found" in result.lower()

    def test_browser_type_text_types_into_active_element(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        element = MagicMock()
        driver = SimpleNamespace(
            current_url="https://example.com/form",
            switch_to=SimpleNamespace(active_element=element),
        )

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)

        result = browser_module.browser_type_text("hello", clear_first=True)

        assert "typed 5 characters" in result.lower()
        assert "hello" not in result
        element.clear.assert_called_once()
        element.send_keys.assert_called_once_with("hello")

    def test_browser_press_enter_sends_return_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        element = MagicMock()
        driver = SimpleNamespace(
            current_url="https://example.com/form",
            switch_to=SimpleNamespace(active_element=element),
        )

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "Keys", SimpleNamespace(RETURN="ENTER"))
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)

        result = browser_module.browser_press_enter()

        assert "enter" in result.lower()
        element.send_keys.assert_called_once_with("ENTER")

    def test_browser_find_and_type_stops_on_lookup_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(browser_module, "browser_find_and_click", lambda query, timeout: "nope")

        assert browser_module.browser_find_and_type("q", "text") == "nope"

    def test_browser_find_and_type_can_press_enter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            browser_module,
            "browser_find_and_click",
            lambda query, timeout: "Browser element clicked successfully.",
        )
        monkeypatch.setattr(
            browser_module,
            "browser_type_text",
            lambda text, clear_first=True: "Typed 4 characters into the active browser element.",
        )
        monkeypatch.setattr(
            browser_module,
            "browser_press_enter",
            lambda: "Pressed Enter in the active browser element.",
        )

        assert (
            browser_module.browser_find_and_type("q", "term", press_enter=True)
            == "Pressed Enter in the active browser element."
        )

    def test_browser_get_current_url_returns_driver_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        driver = SimpleNamespace(current_url="https://example.com")

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)

        assert browser_module.browser_get_current_url() == "Current URL: https://example.com"

    def test_close_connection_quits_driver_and_resets_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        driver = MagicMock()
        monkeypatch.setattr(browser_module, "_driver", driver)

        browser_module.browser_close_connection()

        driver.quit.assert_called_once()
        assert browser_module._driver is None


class TestBrowserNavigationAndContext:
    def test_navigate_applies_policy_before_connecting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        policy = MagicMock(side_effect=browser_module.ToolPermissionError("blocked by policy"))
        connect = MagicMock()
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "require_safe_url", policy)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", connect)

        result = browser_module.browser_navigate("file:///etc/passwd")

        assert result == "Error: blocked by policy"
        policy.assert_called_once_with("file:///etc/passwd")
        connect.assert_not_called()

    def test_navigate_calls_driver_and_verifies_final_url_and_title(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        driver = SimpleNamespace(
            get=MagicMock(),
            current_url="https://example.com/final",
            title="Example page",
        )
        policy = MagicMock()
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "require_safe_url", policy)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)

        result = browser_module.browser_navigate(" https://example.com/start ")

        driver.get.assert_called_once_with("https://example.com/start")
        assert policy.call_args_list == [
            call("https://example.com/start"),
            call("https://example.com/final"),
        ]
        assert "completed successfully" in result
        assert "Current URL: https://example.com/final" in result
        assert "Page title: Example page" in result

    def test_navigate_rejects_an_unsafe_redirect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        driver = SimpleNamespace(
            get=MagicMock(),
            current_url="http://internal.example/admin",
            title="Admin",
        )
        policy = MagicMock(
            side_effect=[None, browser_module.ToolPermissionError("blocked redirect")]
        )
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "require_safe_url", policy)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)

        result = browser_module.browser_navigate("https://example.com/redirect")

        assert "unsafe current page" in result
        assert "completed successfully" not in result
        assert driver.get.call_args_list[-1] == call("about:blank")

    def test_navigate_does_not_report_success_when_title_cannot_be_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Driver:
            current_url = "https://example.com"

            @property
            def title(self) -> str:
                raise RuntimeError("title unavailable")

            def get(self, url: str) -> None:
                del url

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "require_safe_url", MagicMock())
        monkeypatch.setattr(browser_module, "_get_or_create_driver", Driver)

        result = browser_module.browser_navigate("https://example.com")

        assert result == "Browser navigation failed. Check the application logs for details."

    def test_capture_browser_context_returns_rgb_image_and_bounded_snapshot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        png = BytesIO()
        Image.new("RGBA", (3, 2), (10, 20, 30, 128)).save(png, format="PNG")
        driver = SimpleNamespace(
            get_screenshot_as_png=lambda: png.getvalue(),
            current_url="https://example.com/" + ("u" * 4_000),
            title="T" * 2_000,
            execute_script=lambda script, limit: ("<main>" + ("content" * 10_000) + "</main>")[
                :limit
            ],
        )
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)

        screenshot, context = browser_module.capture_browser_context()

        assert screenshot.mode == "RGB"
        assert screenshot.size == (3, 2)
        assert screenshot.getpixel((0, 0)) == (10, 20, 30)
        assert len(context) <= browser_module.MAX_BROWSER_CONTEXT_CHARS
        assert "URL: https://example.com/" in context
        assert "Title: " in context
        assert "Visible page snapshot:" in context
        assert "[truncated" in context

    def test_page_snapshot_uses_visible_content_and_excludes_secret_dom_sources(self) -> None:
        captured_script = ""

        def execute_script(script: str, limit: int) -> str:
            nonlocal captured_script
            captured_script = script
            return "Visible text:\nPublic status"[:limit]

        snapshot = browser_module._capture_bounded_page_snapshot(
            SimpleNamespace(execute_script=execute_script)
        )

        assert "Public status" in snapshot
        assert "outerHTML" not in captured_script
        assert "innerHTML" not in captured_script
        assert "document.body.innerText" in captured_script
        assert '"hidden", "password"' in captured_script

    def test_observe_tier_can_capture_a_network_safe_remote_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        png = BytesIO()
        Image.new("RGB", (2, 2), "navy").save(png, format="PNG")
        driver = SimpleNamespace(
            get_screenshot_as_png=lambda: png.getvalue(),
            current_url="https://example.com/",
            title="Example",
            execute_script=lambda script, limit: "<main>safe observation</main>"[:limit],
        )
        action_policy = MagicMock(
            side_effect=AssertionError("capture must not require interact permission")
        )
        network_policy = MagicMock()
        monkeypatch.setattr(browser_module.config, "permission_tier", "observe")
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)
        monkeypatch.setattr(browser_module, "require_safe_url", action_policy)
        monkeypatch.setattr(browser_module, "validate_url_network_policy", network_policy)

        image, context = browser_module.capture_browser_context()

        assert image.size == (2, 2)
        assert "safe observation" in context
        assert network_policy.call_args_list == [
            call("https://example.com/"),
            call("https://example.com/"),
        ]
        action_policy.assert_not_called()

    def test_capture_browser_context_degrades_safely_per_component(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        driver = SimpleNamespace(
            get_screenshot_as_png=MagicMock(side_effect=RuntimeError("sensitive details")),
            current_url="https://example.com",
            title="Example",
            execute_script=lambda script, limit: "<main>still available</main>"[:limit],
        )
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)

        screenshot, context = browser_module.capture_browser_context()

        assert screenshot.size == (1280, 720)
        assert screenshot.getpixel((0, 0)) == (0, 0, 0)
        assert "screenshot unavailable (RuntimeError)" in context
        assert "<main>still available</main>" in context
        assert "sensitive details" not in context

    def test_capture_browser_context_handles_missing_driver(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: None)

        screenshot, context = browser_module.capture_browser_context()

        assert screenshot.size == (1280, 720)
        assert "Remote browser context unavailable" in context

    def test_capture_blocks_unsafe_page_before_reading_pixels_or_dom(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        screenshot = MagicMock()

        class Driver:
            current_url = "http://169.254.169.254/latest/meta-data"
            get = MagicMock()
            get_screenshot_as_png = screenshot

            @property
            def title(self) -> str:
                raise AssertionError("title must not be read")

            @property
            def page_source(self) -> str:
                raise AssertionError("DOM must not be read")

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", Driver)
        monkeypatch.setattr(
            browser_module,
            "validate_url_network_policy",
            MagicMock(side_effect=browser_module.ToolPermissionError("non-public host")),
        )

        image, context = browser_module.capture_browser_context()

        assert image.size == (1280, 720)
        assert "unsafe current page" in context
        screenshot.assert_not_called()
        Driver.get.assert_called_once_with("about:blank")

    def test_capture_discards_frame_when_page_becomes_unsafe_mid_capture(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        png = BytesIO()
        Image.new("RGB", (2, 2), "red").save(png, format="PNG")

        class Driver:
            get = MagicMock()
            get_screenshot_as_png = MagicMock(return_value=png.getvalue())
            title = "Private metadata"

            def __init__(self) -> None:
                self.urls = iter(
                    (
                        "https://example.com/safe",
                        "http://169.254.169.254/latest/meta-data",
                    )
                )

            @property
            def current_url(self) -> str:
                return next(self.urls)

            def execute_script(self, script: str, limit: int) -> str:
                del script
                return "<main>sensitive-private-dom</main>"[:limit]

        driver = Driver()
        network_policy = MagicMock(
            side_effect=[
                None,
                browser_module.ToolPermissionError("non-public host"),
            ]
        )
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)
        monkeypatch.setattr(browser_module, "validate_url_network_policy", network_policy)

        image, context = browser_module.capture_browser_context()

        assert image.getpixel((0, 0)) == (0, 0, 0)
        assert "sensitive-private-dom" not in context
        assert "unsafe current page" in context
        driver.get.assert_called_once_with("about:blank")

    def test_oversized_viewport_is_rejected_before_screenshot_transport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        screenshot = MagicMock()
        driver = SimpleNamespace(
            current_url="https://example.com",
            title="Example",
            get_window_size=lambda: {"width": 10_000, "height": 10_000},
            get_screenshot_as_png=screenshot,
            execute_script=lambda script, limit: "<main>bounded</main>"[:limit],
        )
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)

        image, context = browser_module.capture_browser_context()

        assert image.getpixel((0, 0)) == (0, 0, 0)
        assert "screenshot unavailable (ValueError)" in context
        assert "<main>bounded</main>" in context
        screenshot.assert_not_called()

    def test_find_and_click_rejects_unsafe_explicit_link_before_click(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        element = MagicMock()
        element.get_attribute.side_effect = lambda name: (
            "http://127.0.0.1/admin" if name == "href" else None
        )
        driver = SimpleNamespace(current_url="https://example.com", get=MagicMock())
        policy = MagicMock(
            side_effect=[
                None,
                browser_module.ToolPermissionError("non-public target"),
            ]
        )
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "require_safe_url", policy)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)
        monkeypatch.setattr(
            browser_module,
            "By",
            SimpleNamespace(NAME="NAME", ID="ID", XPATH="XPATH"),
        )
        monkeypatch.setattr(
            browser_module,
            "EC",
            SimpleNamespace(element_to_be_clickable=lambda locator: locator),
        )
        monkeypatch.setattr(
            browser_module,
            "WebDriverWait",
            lambda selected_driver, timeout: _FakeWait(result=element),
        )

        result = browser_module.browser_find_and_click("Admin")

        assert "target is blocked" in result
        element.click.assert_not_called()

    def test_find_and_click_clamps_model_timeout_to_host_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        observed_timeouts: list[float] = []
        driver = MagicMock()
        driver.current_url = "https://example.com"
        monkeypatch.setattr(browser_module.config, "action_timeout", 6)
        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)
        monkeypatch.setattr(
            browser_module,
            "By",
            SimpleNamespace(NAME="NAME", ID="ID", XPATH="XPATH"),
        )
        monkeypatch.setattr(
            browser_module,
            "EC",
            SimpleNamespace(element_to_be_clickable=lambda locator: locator),
        )
        monkeypatch.setattr(browser_module, "TimeoutException", RuntimeError)

        def wait(_driver: object, timeout: float) -> _FakeWait:
            observed_timeouts.append(timeout)
            return _FakeWait(exception=RuntimeError("timeout"))

        monkeypatch.setattr(browser_module, "WebDriverWait", wait)

        result = browser_module.browser_find_and_click("missing", timeout=10_000)

        assert "within 6 seconds" in result
        assert observed_timeouts == [2.0, 2.0, 2.0]
