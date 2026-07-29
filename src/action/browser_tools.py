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
import math
from io import BytesIO
from threading import Lock
from typing import Any, cast
from urllib.parse import urljoin

from PIL import Image

from src.action.permissions import (
    ToolPermissionError,
    require_safe_url,
    validate_url_network_policy,
)
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


MAX_BROWSER_DOM_CHARS = 20_000
MAX_BROWSER_URL_CHARS = 2_048
MAX_BROWSER_TITLE_CHARS = 512
MAX_BROWSER_CONTEXT_CHARS = 24_000
MAX_BROWSER_SCREENSHOT_BYTES = 20 * 1024 * 1024
MAX_BROWSER_SCREENSHOT_PIXELS = 25_000_000
MAX_BROWSER_QUERY_CHARS = 512
_BROWSER_FALLBACK_SIZE = (1280, 720)


def _bounded_browser_text(value: Any, limit: int) -> str:
    """Return text whose truncation marker is included in the declared limit."""
    text = "" if value is None else str(value)
    text = text.replace("\x00", "�")
    if len(text) <= limit:
        return text

    marker = f"\n...[truncated to {limit} characters]"
    if len(marker) >= limit:
        return text[:limit]
    return f"{text[: limit - len(marker)]}{marker}"


def _bounded_browser_metadata(value: Any, limit: int) -> str:
    """Normalize untrusted browser metadata to a bounded single line."""
    return _bounded_browser_text(" ".join(str(value or "").split()), limit)


def _blank_browser_screenshot() -> Image.Image:
    return Image.new("RGB", _BROWSER_FALLBACK_SIZE, color="black")


def _unavailable_browser_context(reason: str) -> tuple[Image.Image, str]:
    context = _bounded_browser_text(
        f"Remote browser context unavailable. Reason: {reason}",
        MAX_BROWSER_CONTEXT_CHARS,
    )
    return _blank_browser_screenshot(), context


def _decode_browser_screenshot(payload: Any) -> Image.Image:
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise ValueError("WebDriver returned an empty or invalid screenshot payload.")
    if len(payload) > MAX_BROWSER_SCREENSHOT_BYTES:
        raise ValueError("WebDriver screenshot exceeded the configured size limit.")

    with Image.open(BytesIO(bytes(payload))) as source:
        width, height = source.size
        if width <= 0 or height <= 0 or width * height > MAX_BROWSER_SCREENSHOT_PIXELS:
            raise ValueError("WebDriver screenshot dimensions are outside the supported limits.")
        source.load()
        return source.convert("RGB")


def _capture_browser_screenshot(driver: Any) -> Image.Image:
    get_window_size = getattr(driver, "get_window_size", None)
    if callable(get_window_size):
        size = get_window_size()
        if isinstance(size, dict):
            width = size.get("width")
            height = size.get("height")
            if (
                isinstance(width, int)
                and isinstance(height, int)
                and (width <= 0 or height <= 0 or width * height > MAX_BROWSER_SCREENSHOT_PIXELS)
            ):
                raise ValueError("WebDriver viewport dimensions are outside the supported limits.")
    return _decode_browser_screenshot(driver.get_screenshot_as_png())


def _capture_bounded_page_snapshot(driver: Any) -> str:
    """Extract rendered text and visible controls without serializing hidden DOM data."""

    execute_script = getattr(driver, "execute_script", None)
    if not callable(execute_script):
        raise RuntimeError("WebDriver does not support bounded page extraction.")
    value = execute_script(
        """
        const limit = arguments[0];
        const visible = (element) => {
          if (element instanceof HTMLInputElement
              && ["hidden", "password"].includes(element.type.toLowerCase())) {
            return false;
          }
          const style = window.getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return style.display !== "none"
            && style.visibility !== "hidden"
            && Number(style.opacity || "1") !== 0
            && rect.width > 0
            && rect.height > 0;
        };
        const bodyText = document.body ? document.body.innerText.trim() : "";
        const selector = [
          "a[href]", "button", "input:not([type='hidden']):not([type='password'])",
          "select", "textarea", "[role]", "[aria-label]", "[contenteditable='true']"
        ].join(",");
        const controls = Array.from(document.querySelectorAll(selector))
          .filter(visible)
          .slice(0, 250)
          .map((element, index) => {
            const tag = element.tagName.toLowerCase();
            const role = element.getAttribute("role") || "";
            const label = element.getAttribute("aria-label") || "";
            const placeholder = element.getAttribute("placeholder") || "";
            const name = element.getAttribute("name") || "";
            const text = (element.innerText || "").trim().slice(0, 200);
            const value = ("value" in element ? String(element.value || "") : "").slice(0, 200);
            return [
              `${index + 1}. ${tag}`,
              role && `role=${role}`,
              label && `label=${label}`,
              name && `name=${name}`,
              placeholder && `placeholder=${placeholder}`,
              text && `text=${text}`,
              value && `value=${value}`
            ].filter(Boolean).join(" | ");
          });
        return [
          "Visible text:",
          bodyText,
          "Visible interactive elements:",
          controls.join("\\n")
        ].join("\\n").slice(0, limit);
        """,
        MAX_BROWSER_DOM_CHARS + 1,
    )
    return _bounded_browser_text(value, MAX_BROWSER_DOM_CHARS)


def _configure_driver_timeouts(driver: Any) -> None:
    """Apply the host action budget to WebDriver navigation and scripts."""

    timeout = float(config.action_timeout)
    for method_name in ("set_page_load_timeout", "set_script_timeout"):
        method = getattr(driver, method_name, None)
        if callable(method):
            try:
                method(timeout)
            except Exception as exc:
                logger.warning(
                    "Could not configure WebDriver %s: %s",
                    method_name,
                    safe_preview(exc),
                )


def _clear_unsafe_browser_state(driver: Any) -> None:
    """Best-effort removal of a page rejected by the network policy."""

    try:
        driver.get("about:blank")
    except Exception as exc:
        logger.error("Could not clear an unsafe browser page: %s", safe_preview(exc))


def _enforce_current_url_policy(
    driver: Any,
    *,
    operation: str,
    require_interact: bool = False,
) -> tuple[str | None, str | None]:
    """Validate the current page before it is acted on or exported."""

    try:
        current_url = str(driver.current_url or "").strip()
    except Exception as exc:
        logger.warning("Could not read the browser URL during %s: %s", operation, safe_preview(exc))
        return None, f"Browser {operation} could not verify the current URL."

    if not current_url:
        return None, f"Browser {operation} could not verify the current URL."
    try:
        if require_interact:
            require_safe_url(current_url)
        else:
            validate_url_network_policy(current_url)
    except ToolPermissionError as exc:
        logger.warning(
            "Browser %s rejected the current page by URL policy: %s",
            operation,
            safe_preview(exc),
        )
        _clear_unsafe_browser_state(driver)
        return None, f"Error: Browser {operation} blocked an unsafe current page. {exc}"
    return current_url, None


def _validate_element_navigation_target(element: Any, current_url: str) -> str | None:
    """Reject explicit link/form targets that violate the URL policy before activation."""

    for attribute in ("href", "formaction"):
        try:
            raw_target = element.get_attribute(attribute)
        except Exception as exc:
            logger.debug(
                "Could not inspect browser element attribute %s: %s",
                attribute,
                safe_preview(exc),
            )
            raw_target = None
        if not isinstance(raw_target, str) or not raw_target.strip():
            continue
        target = urljoin(current_url, raw_target.strip())
        try:
            require_safe_url(target)
        except ToolPermissionError as exc:
            return f"Error: Browser interaction target is blocked by URL policy. {exc}"
    return None


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
                _configure_driver_timeouts(_driver)
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
                _configure_driver_timeouts(_driver)
                logger.info("Connected to Edge through remote debugging at %s", debugger_address)
                return _driver
            except Exception as exc:
                logger.debug("Existing WebDriver health check failed: %s", exc)

            # Fallback to Chrome
            _driver = webdriver.Chrome(options=options)
            _configure_driver_timeouts(_driver)
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


def browser_navigate(url: str) -> str:
    """Navigate Selenium to an HTTP(S) URL and verify the resulting page state."""
    if not SELENIUM_AVAILABLE:
        return "Selenium is not installed. Run: pip install selenium"
    if not isinstance(url, str):
        return "Browser URL must be a string."

    normalized_url = url.strip()
    if not normalized_url:
        return "Browser URL cannot be empty."

    try:
        require_safe_url(normalized_url)
    except ToolPermissionError as exc:
        logger.warning("Browser navigation rejected by the URL policy: %s", safe_preview(exc))
        return f"Error: {exc}"

    driver = _get_or_create_driver()
    if driver is None:
        return f"Could not connect to the browser. {get_browser_setup_hint()}"

    try:
        logger.info("Navigating the browser to %s", safe_preview(normalized_url))
        _configure_driver_timeouts(driver)
        driver.get(normalized_url)

        final_url, policy_error = _enforce_current_url_policy(
            driver,
            operation="navigation",
            require_interact=True,
        )
        if policy_error:
            return policy_error
        if final_url is None:
            return "Browser navigation failed because the final URL could not be verified."
        title = _bounded_browser_metadata(driver.title, MAX_BROWSER_TITLE_CHARS)

        bounded_url = _bounded_browser_metadata(final_url, MAX_BROWSER_URL_CHARS)
        logger.info(
            "Browser navigation completed at %s with title %s",
            safe_preview(bounded_url),
            safe_preview(title),
        )
        return (
            "Browser navigation completed successfully.\n"
            f"Current URL: {bounded_url}\n"
            f"Page title: {title or '[untitled]'}"
        )
    except WebDriverException as exc:
        logger.error("Browser navigation failed: %s", safe_preview(exc))
        return "Browser navigation failed. Check the application logs for details."
    except Exception as exc:
        logger.error("Unexpected browser navigation error: %s", safe_preview(exc))
        return "Browser navigation failed. Check the application logs for details."


def capture_browser_context() -> tuple[Image.Image, str]:
    """Capture a bounded screenshot and visible page snapshot from Selenium."""
    if not SELENIUM_AVAILABLE:
        return _unavailable_browser_context("Selenium is not available.")

    driver = _get_or_create_driver()
    if driver is None:
        return _unavailable_browser_context("Could not connect to the browser.")

    current_url, policy_error = _enforce_current_url_policy(driver, operation="context capture")
    if policy_error:
        return _unavailable_browser_context(policy_error)
    if current_url is None:
        return _unavailable_browser_context("The current browser URL could not be verified.")
    initial_url = current_url

    failures: list[str] = []
    screenshot = _blank_browser_screenshot()

    try:
        screenshot = _capture_browser_screenshot(driver)
    except Exception as exc:
        logger.warning("Could not capture the browser screenshot: %s", safe_preview(exc))
        failures.append(f"screenshot unavailable ({type(exc).__name__})")

    current_url = _bounded_browser_metadata(current_url, MAX_BROWSER_URL_CHARS)

    try:
        title = _bounded_browser_metadata(driver.title, MAX_BROWSER_TITLE_CHARS)
    except Exception as exc:
        logger.warning("Could not read the browser title: %s", safe_preview(exc))
        failures.append(f"title unavailable ({type(exc).__name__})")
        title = ""

    try:
        page_snapshot = _capture_bounded_page_snapshot(driver)
    except Exception as exc:
        logger.warning("Could not capture the visible browser page: %s", safe_preview(exc))
        failures.append(f"page snapshot unavailable ({type(exc).__name__})")
        page_snapshot = ""

    final_url, final_policy_error = _enforce_current_url_policy(
        driver,
        operation="context capture",
    )
    if final_policy_error:
        return _unavailable_browser_context(final_policy_error)
    if final_url != initial_url:
        return _unavailable_browser_context(
            "The browser URL changed while the frame was being captured; the frame was discarded."
        )

    context_parts = [
        "Remote browser context",
        f"URL: {current_url or '[unavailable]'}",
        f"Title: {title or '[untitled]'}",
    ]
    if failures:
        context_parts.append(f"Capture warnings: {'; '.join(failures)}")
    context_parts.extend(("Visible page snapshot:", page_snapshot or "[empty]"))
    context = _bounded_browser_text("\n".join(context_parts), MAX_BROWSER_CONTEXT_CHARS)
    return screenshot, context


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
    if len(normalized_query) > MAX_BROWSER_QUERY_CHARS:
        return f"Browser element query exceeds {MAX_BROWSER_QUERY_CHARS} characters."
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int | float)
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        return "Browser element timeout must be a positive finite number."
    effective_timeout = min(float(timeout), float(config.action_timeout))

    driver = _get_or_create_driver()
    if driver is None:
        return f"Could not connect to the browser. {get_browser_setup_hint()}"
    current_url, policy_error = _enforce_current_url_policy(
        driver,
        operation="click",
        require_interact=True,
    )
    if policy_error:
        return policy_error
    if current_url is None:
        return "Browser click failed because the current URL could not be verified."

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
                element = WebDriverWait(driver, effective_timeout / len(strategies)).until(
                    EC.element_to_be_clickable((by, value))
                )
                target_error = _validate_element_navigation_target(element, current_url)
                if target_error:
                    return target_error
                element.click()
                _, policy_error = _enforce_current_url_policy(
                    driver,
                    operation="click",
                    require_interact=True,
                )
                if policy_error:
                    return policy_error
                logger.info("Browser element clicked using strategy %s", by)
                return "Browser element clicked successfully."
            except TimeoutException:
                continue
            except Exception as e:
                logger.debug("Browser lookup strategy %s failed: %s", by, safe_preview(e))
                continue

        return (
            f"Browser element not found within {effective_timeout:g} seconds. "
            "Try a different label."
        )

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
    _, policy_error = _enforce_current_url_policy(
        driver,
        operation="typing",
        require_interact=True,
    )
    if policy_error:
        return policy_error

    try:
        active_element = driver.switch_to.active_element

        if clear_first:
            # Clear existing content
            active_element.clear()

        active_element.send_keys(text)
        _, policy_error = _enforce_current_url_policy(
            driver,
            operation="typing",
            require_interact=True,
        )
        if policy_error:
            return policy_error
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
    current_url, policy_error = _enforce_current_url_policy(
        driver,
        operation="keypress",
        require_interact=True,
    )
    if policy_error:
        return policy_error
    if current_url is None:
        return "Browser keypress failed because the current URL could not be verified."

    try:
        active_element = driver.switch_to.active_element
        target_error = _validate_element_navigation_target(active_element, current_url)
        if target_error:
            return target_error
        active_element.send_keys(Keys.RETURN)
        _, policy_error = _enforce_current_url_policy(
            driver,
            operation="keypress",
            require_interact=True,
        )
        if policy_error:
            return policy_error
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
        url, policy_error = _enforce_current_url_policy(driver, operation="URL read")
        if policy_error:
            return policy_error
        if url is None:
            return "Could not read the current browser URL."
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
