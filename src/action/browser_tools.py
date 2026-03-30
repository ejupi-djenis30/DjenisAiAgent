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
        "Install with: pip install selenium webdriver-manager"
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
        remote_url = config.selenium_remote_url.strip()
        if remote_url:
            return "Verifica che il servizio Selenium remoto sia raggiungibile su " f"{remote_url}."
        return "Imposta SELENIUM_REMOTE_URL per usare il runtime browser remoto."
    return "Avvia Chrome o Edge con " f"--remote-debugging-port={config.browser_debugging_port}."


def _get_or_create_driver() -> Any | None:
    """
    Get existing Selenium driver or create a new one by connecting to a browser
    instance running with remote debugging enabled.

    Returns:
        WebDriver instance or None if connection fails.
    """
    global _driver

    if not SELENIUM_AVAILABLE:
        logger.error("Selenium non disponibile")
        return None

    with _driver_lock:
        if _driver is not None:
            try:
                # Test if driver is still alive
                _ = _driver.title
                return _driver
            except WebDriverException:
                logger.warning("Driver esistente non valido, riconnessione...")
                _driver = None

        # Use the configured browser connection strategy for this runtime.
        try:
            if config.uses_remote_selenium():
                remote_url = config.selenium_remote_url.strip()
                options = webdriver.ChromeOptions()
                _driver = webdriver.Remote(command_executor=remote_url, options=options)
                logger.info("✅ Connesso a Selenium remoto: %s", remote_url)
                return _driver

            debugger_address = _get_debugger_address()
            options = webdriver.ChromeOptions()
            options.add_experimental_option("debuggerAddress", debugger_address)

            # Try Edge first (common on Windows 11)
            try:
                from selenium.webdriver.edge.options import Options as EdgeOptions

                edge_options = EdgeOptions()
                edge_options.add_experimental_option("debuggerAddress", debugger_address)
                _driver = webdriver.Edge(options=edge_options)
                logger.info("✅ Connesso a Edge tramite debugger remoto %s", debugger_address)
                return _driver
            except Exception:
                pass

            # Fallback to Chrome
            _driver = webdriver.Chrome(options=options)
            logger.info("✅ Connesso a Chrome tramite debugger remoto %s", debugger_address)
            return _driver

        except WebDriverException as e:
            logger.error(
                "❌ Impossibile connettersi al browser. %s Errore: %s", get_browser_setup_hint(), e
            )
            return None
        except Exception as e:
            logger.error(f"❌ Errore inaspettato nella connessione al browser: {e}")
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
        return "❌ Selenium non installato. Esegui: pip install selenium webdriver-manager"

    driver = _get_or_create_driver()
    if driver is None:
        return f"❌ Impossibile connettersi al browser. {get_browser_setup_hint()}"

    try:
        logger.info(f"🔍 Ricerca elemento browser: '{query}'")

        # Multiple search strategies (from most specific to most general)
        strategies = [
            (By.NAME, query),
            (By.ID, query),
            (By.CSS_SELECTOR, f"input[name*='{query}' i]"),
            (By.CSS_SELECTOR, f"input[placeholder*='{query}' i]"),
            (By.CSS_SELECTOR, f"button[aria-label*='{query}' i]"),
            (
                By.XPATH,
                f"//*[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{query.lower()}')]",
            ),
            (
                By.XPATH,
                f"//*[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{query.lower()}')]",
            ),
            (
                By.XPATH,
                f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{query.lower()}')]",
            ),
        ]

        for by, value in strategies:
            try:
                element = WebDriverWait(driver, timeout / len(strategies)).until(
                    EC.element_to_be_clickable((by, value))
                )
                element.click()
                logger.info(f"✅ Browser: Cliccato su '{query}' usando strategia {by}")
                return f"✅ Elemento '{query}' cliccato con successo nel browser"
            except TimeoutException:
                continue
            except Exception as e:
                logger.debug(f"Strategia {by} fallita: {e}")
                continue

        return f"❌ Elemento '{query}' non trovato nel browser dopo {timeout}s. Prova con un altro termine di ricerca."

    except Exception as e:
        logger.error(f"Errore durante click nel browser: {e}")
        return f"❌ Errore browser: {e!s}"


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
        return "❌ Selenium non disponibile"

    driver = _get_or_create_driver()
    if driver is None:
        return "❌ Impossibile connettersi al browser"

    try:
        active_element = driver.switch_to.active_element

        if clear_first:
            # Clear existing content
            active_element.clear()

        active_element.send_keys(text)
        logger.info(f"✅ Browser: Digitato '{text}' nell'elemento attivo")
        return f"✅ Testo '{text}' digitato con successo nel browser"

    except Exception as e:
        logger.error(f"Errore durante digitazione nel browser: {e}")
        return f"❌ Errore: {e!s}"


def browser_press_enter() -> str:
    """
    Press Enter key in the browser's currently focused element.

    Returns:
        Success message or error description
    """
    if not SELENIUM_AVAILABLE:
        return "❌ Selenium non disponibile"

    driver = _get_or_create_driver()
    if driver is None:
        return "❌ Impossibile connettersi al browser"

    try:
        active_element = driver.switch_to.active_element
        active_element.send_keys(Keys.RETURN)
        logger.info("✅ Browser: Premuto Enter")
        return "✅ Enter premuto con successo nel browser"

    except Exception as e:
        logger.error(f"Errore durante pressione Enter nel browser: {e}")
        return f"❌ Errore: {e!s}"


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
    if "❌" in result:
        return result

    # Then type the text
    result = browser_type_text(text, clear_first=True)
    if "❌" in result:
        return result

    # Optionally press enter
    if press_enter:
        return browser_press_enter()

    return f"✅ Digitato '{text}' in '{query}'" + (" e premuto Enter" if press_enter else "")


def browser_get_current_url() -> str:
    """
    Get the current URL of the active browser tab.

    Returns:
        Current URL or error message
    """
    if not SELENIUM_AVAILABLE:
        return "❌ Selenium non disponibile"

    driver = _get_or_create_driver()
    if driver is None:
        return "❌ Impossibile connettersi al browser"

    try:
        url = driver.current_url
        logger.info(f"📍 URL corrente: {url}")
        return f"URL corrente: {url}"
    except Exception as e:
        return f"❌ Errore: {e!s}"


def browser_close_connection() -> None:
    """Close the Selenium driver connection (does not close the browser itself)."""
    global _driver
    with _driver_lock:
        if _driver is not None:
            try:
                _driver.quit()
                logger.info("✅ Connessione Selenium chiusa")
            except Exception as e:
                logger.warning(f"Errore durante chiusura driver: {e}")
            finally:
                _driver = None
