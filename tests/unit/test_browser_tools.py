"""Unit tests for src/action/browser_tools.py."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

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

        assert "Impossibile connettersi" in browser_module.browser_find_and_click("search")

    def test_get_browser_setup_hint_uses_remote_selenium_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            browser_module.config, "selenium_remote_url", "http://chrome:4444/wd/hub"
        )
        monkeypatch.setattr(browser_module.config, "browser_connection_mode", "remote-selenium")

        hint = browser_module.get_browser_setup_hint()

        assert "SELENIUM" in hint or "Selenium remoto" in hint
        assert "http://chrome:4444/wd/hub" in hint

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

        assert "cliccato" in result.lower()
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

        assert "non trovato" in result.lower()

    def test_browser_type_text_types_into_active_element(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        element = MagicMock()
        driver = SimpleNamespace(switch_to=SimpleNamespace(active_element=element))

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)

        result = browser_module.browser_type_text("hello", clear_first=True)

        assert "digitato" in result.lower()
        element.clear.assert_called_once()
        element.send_keys.assert_called_once_with("hello")

    def test_browser_press_enter_sends_return_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        element = MagicMock()
        driver = SimpleNamespace(switch_to=SimpleNamespace(active_element=element))

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "Keys", SimpleNamespace(RETURN="ENTER"))
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)

        result = browser_module.browser_press_enter()

        assert "enter" in result.lower()
        element.send_keys.assert_called_once_with("ENTER")

    def test_browser_find_and_type_stops_on_lookup_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            browser_module, "browser_find_and_click", lambda query, timeout: "❌ nope"
        )

        assert browser_module.browser_find_and_type("q", "text") == "❌ nope"

    def test_browser_find_and_type_can_press_enter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            browser_module, "browser_find_and_click", lambda query, timeout: "✅ found"
        )
        monkeypatch.setattr(
            browser_module, "browser_type_text", lambda text, clear_first=True: "✅ typed"
        )
        monkeypatch.setattr(browser_module, "browser_press_enter", lambda: "✅ pressed")

        assert browser_module.browser_find_and_type("q", "term", press_enter=True) == "✅ pressed"

    def test_browser_get_current_url_returns_driver_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        driver = SimpleNamespace(current_url="https://example.com")

        monkeypatch.setattr(browser_module, "SELENIUM_AVAILABLE", True)
        monkeypatch.setattr(browser_module, "_get_or_create_driver", lambda: driver)

        assert browser_module.browser_get_current_url() == "URL corrente: https://example.com"

    def test_close_connection_quits_driver_and_resets_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        driver = MagicMock()
        monkeypatch.setattr(browser_module, "_driver", driver)

        browser_module.browser_close_connection()

        driver.quit.assert_called_once()
        assert browser_module._driver is None
