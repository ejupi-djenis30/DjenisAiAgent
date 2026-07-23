"""Browser-specific automation tools using Selenium WebDriver.

This module provides browser automation capabilities to overcome pywinauto's
limitations when interacting with web content. It uses Selenium to access the
browser's DOM directly, allowing reliable interaction with web elements.

Usage:
    1. Start browser with remote debugging:
       Edge: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" --remote-debugging-port=9222
       Chrome: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222

    2. Call browser_* functions when pywinauto fails inside a browser window.
"""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any, cast

from src.config import config
from src.redaction import safe_preview

logger = logging.getLogger(__name__)

# Track Selenium availability and runtime imports
SELENIUM_AVAILABLE = False
webdriver: Any = None
By: Any = None
Keys: Any = None
WebDriverWait: Any = None
EC: Any = None
TimeoutException: Any = None
WebDriverException: Any = None

try:
    from selenium import webdriver as selenium_webdriver
    from selenium.common.exceptions import TimeoutException as selenium_timeout_exception
    from selenium.common.exceptions import WebDriverException as selenium_webdriver_exception
    from selenium.webdriver.common.by import By as selenium_by
    from selenium.webdriver.common.keys import Keys as selenium_keys
    from selenium.webdriver.support import expected_conditions as selenium_expected_conditions
    from selenium.webdriver.support.ui import WebDriverWait as selenium_webdriver_wait

    webdriver = selenium_webdriver
    By = selenium_by
    Keys = selenium_keys
    WebDriverWait = selenium_webdriver_wait
    EC = selenium_expected_conditions
    TimeoutException = selenium_timeout_exception
    WebDriverException = selenium_webdriver_exception
    SELENIUM_AVAILABLE = True
except ImportError:
    logger.warning(
        "Selenium not available. Browser automation will be limited. "
        "Install with: pip install selenium"
    )
    webdriver = cast(Any, None)
    By = cast(Any, None)
    Keys = cast(Any, None)
    WebDriverWait = cast(Any, None)
    EC = cast(Any, None)
    TimeoutException = RuntimeError
    WebDriverException = RuntimeError

# Global driver instance (reused across calls)
_driver: Any | None = None
_driver_lock: Lock = Lock()


def _get_debugger_address() -> str:
    return f"{config.browser_debugging_host}:{config.browser_debugging_port}"


def get_browser_setup_hint() -> str:
    """Return the runtime-specific instructions required to connect Selenium."""

    if config.uses_remote_selenium():
        if config.selenium_remote_url.strip():
            return "Check that the configured remote Selenium service is reachable."
        return "Set SELENIUM_REMOTE_URL to use the remote browser runtime."
    return f"Start Chrome or Edge with --remote-debugging-port={config.browser_debugging_port}."


def _xpath_literal(value: str) -> str:
    """Encode an arbitrary string as a safe XPath 1.0 literal."""

    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'

    parts: list[str] = []
    segments = value.split("'")
    for index, segment in enumerate(segments):
        if segment:
            parts.append(f"'{segment}'")
        if index < len(segments) - 1:
            parts.append('"\'"')
    return f"concat({', '.join(parts)})"


def _get_or_create_driver() -> Any | None:
    """
    Get existing Selenium driver or create a new one by connecting to a browser
    instance running with remote debugging enabled.

    Returns:
        WebDriver instance or None if connection fails.
    """
    global _driver

    if not SELENIUM_AVAILABLE:
        logger.error("Selenium is not available")
        return None

    with _driver_lock:
        if _driver is not None:
            try:
                # Test if driver is still alive
                _ = _driver.title
                return _driver
            except WebDriverException:
                logger.warning("The cached browser driver is no longer valid; reconnecting")
                _driver = None

        # Use the configured browser connection strategy for this runtime.
        try:
            if config.uses_remote_selenium():
                remote_url = config.selenium_remote_url.strip()
                options = webdriver.ChromeOptions()
                _driver = webdriver.Remote(command_executor=remote_url, options=options)
                logger.info("Connected to the configured remote Selenium service")
                return _driver

            debugger_address = _get_debugger_address()
            options = webdriver.ChromeOptions()
            options.add_experimental_option("debuggerAddress", debugger_address)

            # Try Edge first (common on Windows 11)
            try:
                edge_options = webdriver.EdgeOptions()
                edge_options.add_experimental_option("debuggerAddress", debugger_address)
                _driver = webdriver.Edge(options=edge_options)
                logger.info("Connected to Edge through remote debugging at %s", debugger_address)
                return _driver
            except Exception as exc:
                logger.debug("Existing WebDriver health check failed: %s", exc)

            # Fallback to Chrome
            _driver = webdriver.Chrome(options=options)
            logger.info("Connected to Chrome through remote debugging at %s", debugger_address)
            return _driver

        except WebDriverException as e:
            logger.error(
                "Could not connect to the browser. %s Error: %s",
                get_browser_setup_hint(),
                safe_preview(e),
            )
            return None
        except Exception as e:
            logger.error("Unexpected browser connection error: %s", safe_preview(e))
            return None


def is_browser_available() -> bool:
    """Check if Selenium is installed and a browser connection can be established."""
    if not SELENIUM_AVAILABLE:
        return False
    return _get_or_create_driver() is not None


def browser_find_and_click(query: str, timeout: float = 10.0) -> str:
    """
    Find and click an element in the active browser tab using Selenium.

    Searches for elements by multiple strategies: name, ID, placeholder,
    aria-label, and visible text.

    Args:
        query: Text to search for (case-insensitive)
        timeout: Maximum wait time in seconds

    Returns:
        Success message or error description
    """
    if not SELENIUM_AVAILABLE:
        return "Selenium is not installed. Run: pip install selenium"

    normalized_query = query.strip()
    if not normalized_query:
        return "Browser element query cannot be empty."

    driver = _get_or_create_driver()
    if driver is None:
        return f"Could not connect to the browser. {get_browser_setup_hint()}"

    try:
        logger.info("Searching for a browser element (%d characters)", len(normalized_query))

        uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        lowercase = "abcdefghijklmnopqrstuvwxyz"
        needle = _xpath_literal(normalized_query.casefold())
        xpath = (
            "//*["
            f"contains(translate(string(@placeholder), '{uppercase}', '{lowercase}'), {needle}) or "
            f"contains(translate(string(@aria-label), '{uppercase}', '{lowercase}'), {needle}) or "
            f"contains(translate(normalize-space(string(.)), '{uppercase}', '{lowercase}'), {needle})"
            "]"
        )

        # Multiple search strategies (from most specific to most general)
        strategies = [
            (By.NAME, normalized_query),
            (By.ID, normalized_query),
            (By.XPATH, xpath),
        ]

        for by, value in strategies:
            try:
                element = WebDriverWait(driver, timeout / len(strategies)).until(
                    EC.element_to_be_clickable((by, value))
                )
                element.click()
                logger.info("Browser element clicked using strategy %s", by)
                return "Browser element clicked successfully."
            except TimeoutException:
                continue
            except Exception as e:
                logger.debug("Browser lookup strategy %s failed: %s", by, safe_preview(e))
                continue

        return f"Browser element not found within {timeout:g} seconds. Try a different label."

    except Exception as e:
        logger.error("Browser click failed: %s", safe_preview(e))
        return "Browser click failed. Check the application logs for details."


def browser_type_text(text: str, clear_first: bool = True) -> str:
    """
    Type text in the browser's currently focused element (e.g., search bar).

    Args:
        text: Text to type
        clear_first: If True, clear existing content before typing

    Returns:
        Success message or error description
    """
    if not SELENIUM_AVAILABLE:
        return "Selenium is not available."

    driver = _get_or_create_driver()
    if driver is None:
        return "Could not connect to the browser."

    try:
        active_element = driver.switch_to.active_element

        if clear_first:
            # Clear existing content
            active_element.clear()

        active_element.send_keys(text)
        logger.info("Typed %d characters into the active browser element", len(text))
        return f"Typed {len(text)} characters into the active browser element."

    except Exception as e:
        logger.error("Browser typing failed: %s", safe_preview(e))
        return "Browser typing failed. Check the application logs for details."


def browser_press_enter() -> str:
    """
    Press Enter key in the browser's currently focused element.

    Returns:
        Success message or error description
    """
    if not SELENIUM_AVAILABLE:
        return "Selenium is not available."

    driver = _get_or_create_driver()
    if driver is None:
        return "Could not connect to the browser."

    try:
        active_element = driver.switch_to.active_element
        active_element.send_keys(Keys.RETURN)
        logger.info("Pressed Enter in the active browser element")
        return "Pressed Enter in the active browser element."

    except Exception as e:
        logger.error("Browser Enter keypress failed: %s", safe_preview(e))
        return "Browser keypress failed. Check the application logs for details."


def browser_find_and_type(
    query: str, text: str, timeout: float = 10.0, press_enter: bool = False
) -> str:
    """
    Find an input element and type text into it (combined operation).

    Args:
        query: Element to search for (name, placeholder, etc.)
        text: Text to type
        timeout: Maximum wait time to find element
        press_enter: If True, press Enter after typing

    Returns:
        Success message or error description
    """
    # First, find and click the element
    result = browser_find_and_click(query, timeout)
    if not result.startswith("Browser element clicked"):
        return result

    # Then type the text
    result = browser_type_text(text, clear_first=True)
    if not result.startswith("Typed "):
        return result

    # Optionally press enter
    if press_enter:
        return browser_press_enter()

    return f"Typed {len(text)} characters into the selected browser element."


def browser_get_current_url() -> str:
    """
    Get the current URL of the active browser tab.

    Returns:
        Current URL or error message
    """
    if not SELENIUM_AVAILABLE:
        return "Selenium is not available."

    driver = _get_or_create_driver()
    if driver is None:
        return "Could not connect to the browser."

    try:
        url = driver.current_url
        logger.info("Current URL: %s", safe_preview(url))
        return f"Current URL: {url}"
    except Exception as e:
        logger.error("Could not read the current browser URL: %s", safe_preview(e))
        return "Could not read the current browser URL."


def browser_close_connection() -> None:
    """Close the Selenium driver connection (does not close the browser itself)."""
    global _driver
    with _driver_lock:
        if _driver is not None:
            try:
                _driver.quit()
                logger.info("Closed the Selenium connection")
            except Exception as e:
                logger.warning("Could not close the browser driver: %s", safe_preview(e))
            finally:
                _driver = None
