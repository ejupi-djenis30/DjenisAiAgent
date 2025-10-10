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
from typing import TYPE_CHECKING, Any, Optional, Union

logger = logging.getLogger(__name__)

# Type checking imports (only for type hints, not runtime)
if TYPE_CHECKING:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException,
        NoSuchElementException,
        WebDriverException,
    )

# Track Selenium availability and runtime imports
SELENIUM_AVAILABLE = False
webdriver: Any = None
By: Any = None
Keys: Any = None
WebDriverWait: Any = None
EC: Any = None
TimeoutException: Any = None
NoSuchElementException: Any = None
WebDriverException: Any = None

try:
    from selenium import webdriver  # type: ignore[assignment]
    from selenium.webdriver.common.by import By  # type: ignore[assignment]
    from selenium.webdriver.common.keys import Keys  # type: ignore[assignment]
    from selenium.webdriver.support.ui import WebDriverWait  # type: ignore[assignment]
    from selenium.webdriver.support import expected_conditions as EC  # type: ignore[assignment]
    from selenium.common.exceptions import (  # type: ignore[assignment]
        TimeoutException,
        NoSuchElementException,
        WebDriverException,
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    logger.warning(
        "Selenium not available. Browser automation will be limited. "
        "Install with: pip install selenium webdriver-manager"
    )

# Global driver instance (reused across calls)
_driver: Optional[Any] = None
_remote_debugging_port = 9222


def _get_or_create_driver() -> Optional[Any]:
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
    
    if _driver is not None:
        try:
            # Test if driver is still alive
            _driver.title
            return _driver
        except WebDriverException:
            logger.warning("Driver esistente non valido, riconnessione...")
            _driver = None
    
    # Try to connect to existing browser with remote debugging
    try:
        options = webdriver.ChromeOptions()
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{_remote_debugging_port}")
        
        # Try Edge first (common on Windows 11)
        try:
            from selenium.webdriver.edge.service import Service as EdgeService
            from selenium.webdriver.edge.options import Options as EdgeOptions
            
            edge_options = EdgeOptions()
            edge_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{_remote_debugging_port}")
            _driver = webdriver.Edge(options=edge_options)
            logger.info(f"✅ Connesso a Edge tramite porta {_remote_debugging_port}")
            return _driver
        except Exception:
            pass
        
        # Fallback to Chrome
        _driver = webdriver.Chrome(options=options)
        logger.info(f"✅ Connesso a Chrome tramite porta {_remote_debugging_port}")
        return _driver
        
    except WebDriverException as e:
        logger.error(
            f"❌ Impossibile connettersi al browser. "
            f"Assicurati che sia stato avviato con --remote-debugging-port={_remote_debugging_port}. "
            f"Errore: {e}"
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
        return "❌ Impossibile connettersi al browser. Avvialo con --remote-debugging-port=9222"
    
    try:
        logger.info(f"🔍 Ricerca elemento browser: '{query}'")
        
        # Multiple search strategies (from most specific to most general)
        strategies = [
            (By.NAME, query),
            (By.ID, query),
            (By.CSS_SELECTOR, f"input[name*='{query}' i]"),
            (By.CSS_SELECTOR, f"input[placeholder*='{query}' i]"),
            (By.CSS_SELECTOR, f"button[aria-label*='{query}' i]"),
            (By.XPATH, f"//*[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{query.lower()}')]"),
            (By.XPATH, f"//*[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{query.lower()}')]"),
            (By.XPATH, f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{query.lower()}')]"),
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
        return f"❌ Errore browser: {str(e)}"


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
        return f"❌ Errore: {str(e)}"


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
        return f"❌ Errore: {str(e)}"


def browser_find_and_type(query: str, text: str, timeout: float = 10.0, press_enter: bool = False) -> str:
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
        return f"❌ Errore: {str(e)}"


def browser_close_connection() -> None:
    """Close the Selenium driver connection (does not close the browser itself)."""
    global _driver
    if _driver is not None:
        try:
            _driver.quit()
            logger.info("✅ Connessione Selenium chiusa")
        except Exception as e:
            logger.warning(f"Errore durante chiusura driver: {e}")
        finally:
            _driver = None
