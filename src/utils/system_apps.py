"""System applications discovery utilities for Windows."""

from __future__ import annotations

import logging
import os
import platform
import re
from pathlib import Path
from typing import Dict, Optional

if platform.system() != "Windows":  # pragma: no cover - Windows-specific module
    raise RuntimeError("system_apps utilities are only supported on Windows")

import winreg

logger = logging.getLogger(__name__)


class SystemAppsDiscovery:
    """Discover and catalog installed Windows applications."""

    COMMON_EXECUTABLES: Dict[str, str] = {
        "msedge.exe": "Microsoft Edge",
        "chrome.exe": "Google Chrome",
        "firefox.exe": "Mozilla Firefox",
        "opera.exe": "Opera",
        "vivaldi.exe": "Vivaldi",
        "brave.exe": "Brave Browser",
        "notepad.exe": "Notepad",
        "calc.exe": "Calculator",
        "mspaint.exe": "Paint",
        "write.exe": "WordPad",
        "explorer.exe": "File Explorer",
        "cmd.exe": "Command Prompt",
        "powershell.exe": "PowerShell",
        "pwsh.exe": "PowerShell (Core)",
        "taskmgr.exe": "Task Manager",
        "control.exe": "Control Panel",
        "mstsc.exe": "Remote Desktop",
        "snippingtool.exe": "Snipping Tool",
        "code.exe": "Visual Studio Code",
        "devenv.exe": "Visual Studio",
        "teams.exe": "Microsoft Teams",
        "outlook.exe": "Microsoft Outlook",
        "onedrive.exe": "Microsoft OneDrive",
        "steam.exe": "Steam",
        "discord.exe": "Discord",
        "slack.exe": "Slack",
        "spotify.exe": "Spotify",
        "zoom.exe": "Zoom",
    }

    REGISTRY_PATHS = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
    )

    COMMON_PROGRAM_DIRS = tuple(
        path
        for path in {
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("LOCALAPPDATA"),
        }
        if path
    )

    def __init__(self) -> None:
        self._catalog: Dict[str, str] = {}
        self._discovered = False

    def discover(self) -> None:
        """Populate catalog with available applications."""

        if self._discovered:
            return

        logger.info("Discovering installed Windows applications...")
        catalog: Dict[str, str] = {}
        catalog.update({k.lower(): v for k, v in self.COMMON_EXECUTABLES.items()})

        # Registry app paths entries provide explicit executable mapping
        for hive, path in self.REGISTRY_PATHS:
            try:
                with winreg.OpenKey(hive, path) as key:
                    index = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, index)
                        except OSError:
                            break

                        try:
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                exe_path, _ = winreg.QueryValueEx(subkey, "")
                        except OSError:
                            index += 1
                            continue

                        if exe_path and os.path.isfile(exe_path):
                            exe_name = Path(exe_path).name.lower()
                            friendly_name = self._friendly_from_registry(subkey_name, exe_name)
                            catalog.setdefault(exe_name, friendly_name)
                        index += 1
            except OSError:  # pragma: no cover - registry path may be missing
                continue

        # Search known directories for well-known executable names
        for base_dir in self.COMMON_PROGRAM_DIRS:
            self._scan_directory(Path(base_dir), catalog)

        self._catalog = dict(sorted(catalog.items()))
        self._discovered = True
        logger.info("System applications discovery complete (found %d entries)", len(self._catalog))

    def _scan_directory(self, base: Path, catalog: Dict[str, str]) -> None:
        """Scan directory heuristically for known executables."""

        if not base.exists():
            return

        known_patterns = {
            re.compile(pattern, re.IGNORECASE): name
            for pattern, name in {
                r"msedge\.exe$": "Microsoft Edge",
                r"chrome\.exe$": "Google Chrome",
                r"firefox\.exe$": "Mozilla Firefox",
                r"notepad\+\+\.exe$": "Notepad++",
                r"code\.exe$": "Visual Studio Code",
                r"discord\.exe$": "Discord",
                r"teams\.exe$": "Microsoft Teams",
                r"spotify\.exe$": "Spotify",
                r"slack\.exe$": "Slack",
                r"zoom\.exe$": "Zoom",
            }.items()
        }

        max_depth = 3
        base_depth = len(base.parts)

        try:
            for root, dirs, files in os.walk(base):
                current_depth = len(Path(root).parts) - base_depth
                if current_depth > max_depth:
                    dirs[:] = []
                    continue

                for file in files:
                    file_lower = file.lower()
                    for pattern, friendly_name in known_patterns.items():
                        if pattern.search(file_lower):
                            catalog.setdefault(file_lower, friendly_name)
                            break
        except PermissionError:  # pragma: no cover - depends on system permissions
            logger.debug("Permission denied while scanning %s", base)

    @staticmethod
    def _friendly_from_registry(subkey: str, exe_name: str) -> str:
        """Create friendly name from registry key."""

        base = subkey.replace(".exe", "")
        base = base.replace("_", " ").replace("-", " ").strip()
        if not base:
            base = exe_name.replace(".exe", "")
        return base.title()

    @property
    def catalog(self) -> Dict[str, str]:
        """Return catalog; triggers discovery if needed."""

        if not self._discovered:
            self.discover()
        return dict(self._catalog)

    def format_catalog(self) -> str:
        """Return formatted string of available applications."""

        entries = ["Available Windows applications (executable → name):"]
        for exe, name in self.catalog.items():
            entries.append(f"  • {exe:<25} → {name}")
        return "\n".join(entries)

    def resolve_executable(self, query: str) -> str:
        """Resolve a user-provided application name to an executable."""

        normalized = query.strip().lower()
        if not normalized:
            return query

        catalog = self.catalog

        if normalized in catalog:
            return normalized

        for exe, name in catalog.items():
            if normalized == name.lower():
                return exe

        for exe, name in catalog.items():
            if normalized in name.lower() or name.lower() in normalized:
                return exe

        for exe in catalog:
            if normalized in exe:
                return exe

        if not normalized.endswith(".exe"):
            normalized = f"{normalized}.exe"
        return normalized


_instance: Optional[SystemAppsDiscovery] = None


def _get_instance() -> SystemAppsDiscovery:
    global _instance
    if _instance is None:
        _instance = SystemAppsDiscovery()
    return _instance


def get_apps_catalog() -> Dict[str, str]:
    """Return mapping of executable name to friendly name."""

    return _get_instance().catalog


def get_apps_catalog_formatted() -> str:
    """Return formatted catalog string."""

    return _get_instance().format_catalog()


def find_executable(query: str) -> str:
    """Resolve user-provided application name to an executable."""

    return _get_instance().resolve_executable(query)
