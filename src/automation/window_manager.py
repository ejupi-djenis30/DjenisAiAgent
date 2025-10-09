"""Window management utilities for UI automation."""

from __future__ import annotations

import difflib
import time
from typing import Any, Dict, List, Optional

import psutil
from pywinauto import Application

from src.utils.logger import setup_logger


class WindowManager:
    """Encapsulates window discovery and focus strategies."""

    _PROCESS_NAME_ALIASES = {
        "calculator": "calculatorapp.exe",
        "calc": "calculatorapp.exe",
        "notepad": "notepad.exe",
        "paint": "mspaint.exe",
        "edge": "msedge.exe",
        "chrome": "chrome.exe",
        "firefox": "firefox.exe",
    }

    _SYSTEM_WINDOW_TITLES = {
        "Program Manager",
        "Microsoft Text Input Application",
        "Windows Input Experience",
        "MSCTFIME UI",
        "Default IME",
        "Task Switching",
        "",
    }

    _SYSTEM_WINDOW_KEYWORDS = {
        "ime ui",
        "input experience",
        "progman",
        "dde server",
    }

    def __init__(self, *, logger=None, gemini_client=None):
        self.logger = logger or setup_logger("WindowManager")
        self._gemini_client = gemini_client

    @staticmethod
    def _normalize_title(title: Optional[str]) -> str:
        """Return a normalized window title for matching."""

        return (title or "").strip()

    def _titles_match(self, candidate: str, target: str) -> bool:
        """Check whether two window titles refer to the same window."""

        candidate_norm = self._normalize_title(candidate).lower()
        target_norm = self._normalize_title(target).lower()

        if not candidate_norm or not target_norm:
            return False

        return target_norm in candidate_norm or candidate_norm in target_norm

    def get_active_window_title(self) -> Optional[str]:
        """Get the title of the currently active window."""

        try:
            import win32gui

            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            return title
        except Exception:
            try:
                app = Application(backend="uia").connect(active_only=True)
                title = app.top_window().window_text()
                return title
            except Exception:
                return None

    def _verify_focus(self, target_title: str, *, allow_partial: bool = True) -> bool:
        """Verify whether the active window matches the requested title."""

        active_title = self.get_active_window_title()
        if not active_title:
            return False

        if allow_partial:
            return self._titles_match(active_title, target_title)

        return (
            self._normalize_title(active_title).lower()
            == self._normalize_title(target_title).lower()
        )

    def _focus_window_handle(self, hwnd: int, *, expected_title: Optional[str] = None) -> bool:
        """Focus a window by handle and optionally verify the resulting title."""

        try:
            import win32con
            import win32gui

            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.4)

            if expected_title and not self._verify_focus(expected_title):
                self.logger.debug(
                    "Post-focus verification failed for handle %s (expected '%s')",
                    hwnd,
                    expected_title,
                )
                return False

            return True
        except Exception as exc:
            self.logger.debug("Failed to focus window handle %s: %s", hwnd, exc)
            return False

    def _focus_pywinauto_window(self, window: Any, *, expected_title: str) -> bool:
        """Focus a pywinauto window with verification."""

        try:
            window.set_focus()
            time.sleep(0.3)
        except Exception as exc:
            self.logger.debug("Pywinauto focus failed: %s", exc)
            return False

        if not self._verify_focus(expected_title):
            self.logger.debug(
                "Focused window did not match expectation (expected '%s')",
                expected_title,
            )
            return False

        return True

    def focus_window(self, title_pattern: str) -> bool:
        """Focus a window using deterministic fallbacks before AI assistance."""

        target = self._normalize_title(title_pattern)
        if not target:
            self.logger.warning("focus_window called with empty title pattern")
            return False

        if self._verify_focus(target):
            current = self.get_active_window_title()
            self.logger.info(
                "Window '%s' already has focus; skipping focus request for '%s'",
                current,
                target,
            )
            return True

        self.logger.info("Attempting to focus window: %s", target)

        try:
            if self._focus_direct(target):
                return True

            self.logger.info("Direct focus failed; enumerating open windows for deterministic selection")
            if self.focus_from_candidates(target, allow_ai=True):
                return True

            self.logger.warning("Window not found: %s", target)
            return False
        except Exception as exc:
            self.logger.error("Failed to focus window '%s': %s", target, exc)
            return False

    def _focus_direct(self, title_pattern: str) -> bool:
        """Attempt direct focus methods (exact match, regex, process, Win32)."""

        if self._focus_direct_by_exact_title(title_pattern):
            return True

        if self._focus_direct_by_regex(title_pattern):
            return True

        if self._focus_direct_by_process(title_pattern):
            return True

        if self._focus_direct_by_win32(title_pattern):
            return True

        self.logger.debug("Direct focus strategies exhausted for '%s'", title_pattern)
        return False

    def _focus_direct_by_exact_title(self, title_pattern: str) -> bool:
        """Focus window by exact title match using pywinauto."""

        try:
            app = Application(backend="uia").connect(title=title_pattern, timeout=2)
            top_window = app.top_window()
        except Exception as exc:
            self.logger.debug("Exact-title focus attempt failed: %s", exc)
            return False

        if self._focus_pywinauto_window(top_window, expected_title=title_pattern):
            self.logger.info("Focused window (exact match): %s", title_pattern)
            return True

        return False

    def _focus_direct_by_regex(self, title_pattern: str) -> bool:
        """Focus window using regex title matching."""

        try:
            app = Application(backend="uia").connect(title_re=f".*{title_pattern}.*", timeout=3)
            windows = app.windows()
        except Exception as exc:
            self.logger.debug("Regex focus attempt failed: %s", exc)
            return False

        visible_windows = [win for win in windows if getattr(win, "is_visible", lambda: True)()]
        candidates = visible_windows or windows

        for win in candidates:
            window_title = self._normalize_title(getattr(win, "window_text", lambda: "")()) or title_pattern
            if self._focus_pywinauto_window(win, expected_title=window_title):
                self.logger.info("Focused window (regex match): %s", window_title)
                return True

        return False

    def _focus_direct_by_process(self, title_pattern: str) -> bool:
        """Focus window by mapping common app names to process names."""

        lower_title = title_pattern.lower()

        for app_name, process_name in self._PROCESS_NAME_ALIASES.items():
            if app_name not in lower_title:
                continue

            try:
                app = Application(backend="uia").connect(process=process_name, timeout=2)
                windows = app.windows()
            except Exception as exc:
                self.logger.debug("Process focus attempt failed for %s: %s", process_name, exc)
                continue

            for win in windows:
                if not getattr(win, "is_visible", lambda: True)() and len(windows) > 1:
                    continue

                window_title = self._normalize_title(getattr(win, "window_text", lambda: "")()) or title_pattern
                if self._focus_pywinauto_window(win, expected_title=window_title):
                    self.logger.info("Focused window by process (%s): %s", process_name, window_title)
                    return True

        return False

    def _focus_direct_by_win32(self, title_pattern: str) -> bool:
        """Focus window using Win32 API enumeration."""

        try:
            import win32gui
        except Exception as exc:
            self.logger.debug("Win32 libraries unavailable for focus attempt: %s", exc)
            return False

        matches: List[Dict[str, Any]] = []

        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if self._titles_match(title, title_pattern):
                    windows.append({"hwnd": hwnd, "title": title})
            return True

        try:
            win32gui.EnumWindows(callback, matches)
        except Exception as exc:
            self.logger.debug("Win32 enumeration failed: %s", exc)
            return False

        if not matches:
            return False

        hwnd = matches[0]["hwnd"]
        title = matches[0]["title"]
        if self._focus_window_handle(hwnd, expected_title=title):
            self.logger.info("Focused window via Win32: %s", title)
            return True

        return False

    def focus_from_candidates(self, title_pattern: str, *, allow_ai: bool) -> bool:
        """Focus a window using deterministic heuristics with optional AI assistance."""

        candidates = self._enumerate_focus_candidates()
        if not candidates:
            self.logger.debug("No window candidates available for fallback focus")
            return False

        self.logger.debug(
            "Enumerated %d candidate windows for '%s'",
            len(candidates),
            title_pattern,
        )
        for index, candidate in enumerate(candidates[:5], start=1):
            self.logger.debug(
                "  %d. %s (process=%s, size=%dx%d)",
                index,
                candidate.get("title"),
                candidate.get("process_name"),
                candidate.get("width", 0),
                candidate.get("height", 0),
            )

        target_norm = self._normalize_title(title_pattern).lower()

        def _candidate_similarity(candidate: Dict[str, Any]) -> float:
            title_norm = self._candidate_title_norm(candidate)
            if not title_norm:
                return 0.0
            return difflib.SequenceMatcher(None, target_norm, title_norm).ratio()

        tried_handles = set()

        deterministic = self._deterministic_window_choice(title_pattern, candidates)
        if deterministic:
            hwnd = deterministic.get("hwnd")
            if hwnd:
                tried_handles.add(hwnd)
            if self._focus_candidate(
                deterministic,
                source="Deterministic fallback",
            ):
                return True
            self.logger.debug(
                "Deterministic candidate did not yield focus for '%s'", title_pattern
            )

        similarity_sorted = sorted(
            candidates,
            key=lambda candidate: (
                _candidate_similarity(candidate),
                candidate.get("width", 0) * candidate.get("height", 0),
            ),
            reverse=True,
        )

        for candidate in similarity_sorted:
            hwnd = candidate.get("hwnd")
            if not hwnd or hwnd in tried_handles:
                continue
            if self._focus_candidate(candidate, source="Similarity fallback"):
                return True
            tried_handles.add(hwnd)

        if allow_ai:
            selected = self._select_window_with_ai(title_pattern, candidates)
            if selected is None:
                for candidate in similarity_sorted:
                    hwnd = candidate.get("hwnd")
                    if hwnd and hwnd not in tried_handles:
                        selected = candidate
                        self.logger.info(
                            "AI selection unavailable; defaulting to best remaining candidate '%s'",
                            candidate.get("title"),
                        )
                        break

            if selected and self._focus_candidate(
                selected,
                source="AI-assisted selection" if selected not in similarity_sorted else "Heuristic fallback",
            ):
                return True

        return False

    def ai_identify_window(self, target_pattern: str) -> bool:
        """Backward-compatible entry point for AI window identification."""

        self.logger.info("Attempting AI-assisted window identification fallback")
        return self.focus_from_candidates(target_pattern, allow_ai=True)

    def _enumerate_focus_candidates(self) -> List[Dict[str, Any]]:
        """Return user-visible window candidates for fallback selection."""

        windows = self.get_all_open_windows()
        return [
            window
            for window in windows
            if window.get("title") and not self._is_system_window(window.get("title", ""))
        ]

    def _candidate_title_norm(self, candidate: Dict[str, Any]) -> str:
        """Return normalized lowercase title for a window candidate."""

        return self._normalize_title(candidate.get("title")).lower()

    def _deterministic_window_choice(
        self,
        target_pattern: str,
        candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Return a deterministic best-match window when possible."""

        if not candidates:
            return None

        target_norm = self._normalize_title(target_pattern).lower()
        if not target_norm:
            return None

        if target_norm.endswith(".exe"):
            process_matches = [
                candidate
                for candidate in candidates
                if (candidate.get("process_name") or "").lower() == target_norm
            ]

            if len(process_matches) == 1:
                self.logger.debug(
                    "Deterministic process match for '%s': %s",
                    target_pattern,
                    process_matches[0].get("title"),
                )
                return process_matches[0]

            if process_matches:
                self.logger.debug(
                    "Multiple process matches for '%s'; selecting largest visible window",
                    target_pattern,
                )
                return max(
                    process_matches,
                    key=lambda candidate: (candidate.get("width", 0) * candidate.get("height", 0)),
                )

        substring_matches = [
            candidate
            for candidate in candidates
            if target_norm in self._candidate_title_norm(candidate)
        ]

        if len(substring_matches) == 1:
            return substring_matches[0]

        inverse_matches = [
            candidate
            for candidate in candidates
            if self._candidate_title_norm(candidate) in target_norm
        ]

        if len(inverse_matches) == 1:
            return inverse_matches[0]

        process_matches = [
            candidate
            for candidate in candidates
            if target_norm in (candidate.get("process_name") or "").lower()
        ]

        if len(process_matches) == 1:
            return process_matches[0]

        titles = [candidate.get("title", "") for candidate in candidates]
        close_matches = difflib.get_close_matches(target_pattern, titles, n=2, cutoff=0.82)

        if len(close_matches) == 1:
            chosen_title = close_matches[0]
            return next(candidate for candidate in candidates if candidate.get("title") == chosen_title)

        if len(substring_matches) > 1:
            best = max(
                substring_matches,
                key=lambda candidate: difflib.SequenceMatcher(
                    None,
                    target_norm,
                    self._candidate_title_norm(candidate),
                ).ratio(),
            )
            return best

        if close_matches:
            chosen_title = close_matches[0]
            return next(candidate for candidate in candidates if candidate.get("title") == chosen_title)

        return None

    def _focus_candidate(self, candidate: Dict[str, Any], *, source: str) -> bool:
        """Attempt to focus the provided candidate with contextual logging."""

        title = candidate.get("title")
        process_name = candidate.get("process_name") or "unknown process"
        hwnd = candidate.get("hwnd")

        if not hwnd:
            self.logger.debug("%s candidate '%s' lacks window handle; skipping", source, title)
            return False

        if self._focus_window_handle(hwnd, expected_title=title):
            self.logger.info("%s focused window '%s' (%s)", source, title, process_name)
            return True

        self.logger.debug("%s focus attempt failed for '%s'", source, title)
        return False

    def _select_window_with_ai(
        self,
        target_pattern: str,
        candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Ask the language model to choose a window from the candidate list."""

        if not candidates:
            return None

        try:
            from src.core.prompts import prompt_builder
        except Exception as exc:
            self.logger.debug("AI-assisted selection unavailable: %s", exc)
            return None

        client = self._gemini_client
        if client is None:
            self.logger.warning("AI-assisted window selection skipped: Gemini client not provided")
            return None

        prompt = prompt_builder.build_window_selection_prompt(target_pattern, candidates)

        try:
            response_text = client.generate_text(prompt, max_tokens=8)
            selection = int(response_text.strip())
        except Exception as exc:
            self.logger.debug("AI window selection failed: %s", exc)
            return None

        if selection <= 0 or selection > len(candidates):
            self.logger.debug("AI returned invalid selection index: %s", selection)
            return None

        return candidates[selection - 1]

    def get_all_open_windows(self) -> List[Dict[str, Any]]:
        """Get metadata about all visible top-level windows."""

        windows: List[Dict[str, Any]] = []

        try:
            import win32gui
            import win32process

            def callback(hwnd, window_list):
                if not win32gui.IsWindowVisible(hwnd):
                    return True

                title = win32gui.GetWindowText(hwnd)
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                width = max(0, right - left)
                height = max(0, bottom - top)

                process_name = ""
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid:
                        process = psutil.Process(pid)
                        process_name = process.name()
                except Exception:
                    process_name = ""

                window_list.append(
                    {
                        "title": title,
                        "hwnd": hwnd,
                        "x": left,
                        "y": top,
                        "width": width,
                        "height": height,
                        "process_name": process_name,
                    }
                )
                return True

            win32gui.EnumWindows(callback, windows)
            return windows

        except ImportError:
            try:
                import pygetwindow as gw

                for window in gw.getAllWindows():
                    title = window.title
                    if not title:
                        continue
                    windows.append(
                        {
                            "title": title,
                            "hwnd": getattr(window, "_hWnd", 0),
                            "x": window.left,
                            "y": window.top,
                            "width": window.width,
                            "height": window.height,
                            "process_name": "",
                        }
                    )

                return windows
            except Exception:
                self.logger.warning("Could not enumerate windows (win32gui not available)")
                return []

    @staticmethod
    def _is_system_window(title: str) -> bool:
        """Check if a window title is a system window that should be ignored."""

        title_lower = title.lower()

        if title in WindowManager._SYSTEM_WINDOW_TITLES:
            return True

        return any(keyword in title_lower for keyword in WindowManager._SYSTEM_WINDOW_KEYWORDS)

    def get_running_processes(self) -> List[str]:
        """Get list of running process names."""

        return [proc.name() for proc in psutil.process_iter(["name"])]

    def is_application_running(self, app_name: str) -> bool:
        """Check if an application is running."""

        processes = self.get_running_processes()
        return any(app_name.lower() in proc.lower() for proc in processes)
