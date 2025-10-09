"""Prompt generation utilities for the Gemini client."""

from typing import Any, Dict, List, Optional

from src.core.actions import action_registry


def _join_sections(sections: List[str]) -> str:
    """Join non-empty prompt sections with readable spacing."""

    return "\n\n".join(section.strip() for section in sections if section and section.strip())


def _detect_complexity(request: str) -> str:
    """Detect task complexity from user request."""

    words = len(request.split())
    conditional_tokens = {"if", "when", "until", "while", "after", "before", "unless"}
    conjunction_tokens = {"and", "then", "followed", "next"}
    request_lower = request.lower()

    has_conditionals = any(token in request_lower for token in conditional_tokens)
    conjunction_count = sum(request_lower.count(token) for token in conjunction_tokens)

    if has_conditionals or conjunction_count >= 2 or words > 25:
        return "complex"
    if words > 12 or conjunction_count >= 1:
        return "medium"
    return "simple"


def _format_context(context: Dict[str, Any]) -> str:
    """Format runtime context for inclusion in prompts."""

    lines = ["CURRENT SYSTEM SNAPSHOT:"]

    active_window = context.get("active_window")
    if active_window:
        lines.append(f"- Active Window: {active_window}")

    screen_size = context.get("screen_size")
    if screen_size:
        lines.append(f"- Screen Size: {screen_size}")

    processes = context.get("running_processes", [])
    if processes:
        limited_processes = ", ".join(processes[:8])
        lines.append(f"- Running Apps: {limited_processes}")

    timestamp = context.get("timestamp")
    if timestamp:
        lines.append(f"- Timestamp: {timestamp}")

    agent_version = context.get("agent_version")
    if agent_version:
        lines.append(f"- Agent Version: {agent_version}")

    # Only add language if we have other context data
    if len(lines) > 1:
        try:
            import locale

            locale_info = locale.getlocale()[0] or "en_US"
            lines.append(f"- System Language: {locale_info}")
        except Exception:
            pass

    if len(lines) == 1:
        return ""

    return "\n".join(lines)


def _collect_system_configuration(context: Optional[Dict[str, Any]] = None) -> str:
    """Gather detailed Windows configuration information for prompt inclusion."""

    lines: List[str] = ["WINDOWS SYSTEM CONFIGURATION:"]

    try:
        import platform

        system = platform.system()
        release = platform.release()
        version = platform.version()
        architecture = platform.machine()
        if system:
            os_descriptor = f"{system} {release}".strip()
            if version:
                os_descriptor = f"{os_descriptor} (build {version})"
            lines.append(f"- Operating System: {os_descriptor}")
        if architecture:
            lines.append(f"- System Architecture: {architecture}")
        processor = platform.processor()
        if processor:
            lines.append(f"- Processor: {processor}")
        if hasattr(platform, "win32_edition"):
            try:
                edition = platform.win32_edition()
                if edition:
                    lines.append(f"- Windows Edition: {edition}")
            except Exception:
                pass
    except Exception:
        pass

    try:
        import locale

        language, encoding = locale.getlocale()
        if not language:
            language = locale.getdefaultlocale()[0]
        if language:
            lines.append(f"- System Language: {language}")
        preferred_encoding = encoding or locale.getpreferredencoding(False)
        if preferred_encoding:
            lines.append(f"- Preferred Encoding: {preferred_encoding}")
    except Exception:
        pass

    try:
        import time

        timezone = " ".join([tz for tz in time.tzname if tz])
        if timezone.strip():
            lines.append(f"- Time Zone: {timezone.strip()}")
    except Exception:
        pass

    try:
        import os

        shell_candidates = [
            os.getenv("SHELL"),
            os.getenv("ComSpec"),
            os.getenv("COMSPEC"),
            os.getenv("POWERSHELL_DISTRIBUTION_CHANNEL"),
        ]
        shell_names = [candidate for candidate in shell_candidates if candidate]
        if shell_names:
            lines.append("- Shell Candidates: " + ", ".join(dict.fromkeys(shell_names)))
        processor_identifier = os.getenv("PROCESSOR_IDENTIFIER")
        if processor_identifier:
            lines.append(f"- Processor Identifier: {processor_identifier}")
        user_locale_env = os.getenv("LANG") or os.getenv("LC_ALL") or os.getenv("LC_CTYPE")
        if user_locale_env:
            lines.append(f"- Environment Locale Variable: {user_locale_env}")
        if os.getenv("USERPROFILE"):
            lines.append(f"- User Profile Path: {os.getenv('USERPROFILE')}")
    except Exception:
        pass

    screen_size = None
    if context:
        screen_size = context.get("screen_size")
    if not screen_size:
        try:
            import ctypes

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            if hasattr(user32, "SetProcessDPIAware"):
                try:
                    user32.SetProcessDPIAware()
                except Exception:
                    pass
            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)
            if width and height:
                screen_size = (width, height)
        except Exception:
            screen_size = None
    if screen_size:
        lines.append(f"- Primary Screen Size: {screen_size}")

    if len(lines) == 1:
        return ""

    return "\n".join(lines)


class PromptBuilder:
    """Build optimized prompts for Gemini API calls."""

    TASK_PLANNING_SYSTEM = (
        "You are a specialized Windows UI Automation Agent with the following capabilities:\n"
        "ROLE: Execute complex multi-step UI automation tasks on Windows 10/11 systems.\n"
        "CAPABILITIES: Computer vision (screenshot analysis), mouse control (click/drag/scroll), "
        "keyboard input (type/hotkeys), window management (focus/minimize/maximize), system commands.\n"
        "OUTPUT: Structured JSON plans with executable actions, coordinates, timing, and verification steps.\n"
        "GOAL: Transform natural language requests into precise, reliable automation sequences."
    )

    WINDOWS_CONTEXT = (
        "═══════════════════════════════════════════════════════════\n"
        "WINDOWS UI AUTOMATION ENVIRONMENT - TECHNICAL SPECIFICATIONS\n"
        "═══════════════════════════════════════════════════════════\n\n"
        
    "COORDINATE SYSTEM:\n"
        "  • Origin: (0, 0) at top-left corner of primary screen\n"
        "  • X-axis: Increases left → right (horizontal)\n"
        "  • Y-axis: Increases top → bottom (vertical)\n"
        "  • Units: Pixels (integer values only)\n"
        "  • Multi-monitor: Each screen has independent coordinate space\n"
        "  • Example: Center of 1920×1080 screen = (~960, ~540)\n\n"
        
    "EXECUTION REQUIREMENTS:\n"
        "  • Window Focus: MANDATORY before ANY keyboard/typing action\n"
        "  • Timing: Add 0.5-1s wait after window switches, 1-2s after app launches\n"
        "  • Verification: Take screenshot after critical actions to confirm state\n"
        "  • Precision: Mouse coordinates accurate within ±5px margin\n"
        "  • Reliability: Always provide fallback alternatives for failure scenarios\n\n"
        
    "APPLICATION IDENTIFICATION:\n"
        "  • By Window Title: Partial matches allowed (\"Chrome\" matches \"Google Chrome - YouTube\")\n"
        "  • By Process Name: Exact process name (\"chrome.exe\", \"notepad.exe\")\n"
        "  • Case Sensitivity: Window titles are case-insensitive\n"
        "  • Multi-instance: If multiple windows, focus most recent or specify criteria\n\n"
        
    "KEYBOARD SHORTCUTS (Windows Standard):\n"
        "  • Win: Open Start Menu\n"
        "  • Win+R: Run dialog (fastest app launcher)\n"
        "  • Win+D: Show Desktop (minimize all)\n"
        "  • Alt+Tab: Switch between windows\n"
        "  • Alt+F4: Close active window\n"
        "  • Ctrl+Shift+Esc: Task Manager\n"
        "  • Ctrl+C/V/X/A/Z: Copy/Paste/Cut/Select All/Undo\n"
        "  • F5: Refresh (browsers/explorer)\n"
        "  • Ctrl+F: Find/Search\n"
        "  • Ctrl+T: New tab (browsers)\n"
        "  • Ctrl+W: Close tab/window\n\n"
        
    "ELEMENT TARGETING HIERARCHY (Preference Order):\n"
        "  1. KEYBOARD SHORTCUT (Most reliable, no coordinates needed)\n"
        "     Example: Use Ctrl+T instead of clicking \"New Tab\"\n"
        "  2. TAB + ENTER NAVIGATION (Accessible, no vision needed)\n"
        "     Example: Tab 3 times, press Enter\n"
        "  3. TEXT-BASED SEARCH (Use app's search if available)\n"
        "     Example: Ctrl+F → type query → Enter\n"
        "  4. VISUAL ELEMENT LOCATION (Requires screenshot analysis)\n"
        "     Example: Identify button via vision, click at (~x, ~y)\n"
        "  5. COORDINATE ESTIMATION (Last resort, lowest reliability)\n"
        "     Example: Click at (~100, ~50) for top-left area\n\n"
        
    "SCREEN ANALYSIS CAPABILITIES:\n"
        "  • Vision Model: Google Gemini (image understanding)\n"
        "  • Input: PIL Image screenshots (RGB/RGBA)\n"
        "  • Output: Element locations, text content, UI state\n"
        "  • Accuracy: ±10-20px typical, confidence scores provided\n"
        "  • Limitations: Small text may be unclear, overlapping elements challenging\n\n"
        
    "TIMING GUIDELINES:\n"
        "  • Application Launch: 2-5 seconds (add 2s wait minimum)\n"
        "  • Window Focus Switch: 0.5-1 second (add 0.5s wait)\n"
        "  • Page Load (Browser): 2-10 seconds (verify loaded state)\n"
        "  • File Dialog Open: 1-2 seconds\n"
        "  • Context Menu: 0.3-0.5 seconds\n"
        "  • Typing Speed: 50-100ms per character (configurable)\n\n"
        
    "COMMON FAILURE MODES & SOLUTIONS:\n"
        "  • App Already Running: Check running processes → focus existing window\n"
        "  • Wrong Window Focus: Verify active window title → refocus if needed\n"
        "  • Element Not Found: Take screenshot → locate visually → adjust coordinates\n"
        "  • Slow Loading: Add wait step → verify state → retry if needed\n"
        "  • Coordinates Drift: UI scaling/DPI affects coordinates → use relative positioning\n"
        "  • Popup Blocking: Check for unexpected dialogs → handle or dismiss\n"
    )

    EXECUTION_STRATEGIES = (
        "═══════════════════════════════════════════════════════════\n"
        "EXECUTION STRATEGY FRAMEWORK - STEP-BY-STEP METHODOLOGY\n"
        "═══════════════════════════════════════════════════════════\n\n"
        
    "PRE-EXECUTION CHECKLIST:\n"
    "  - Identify current system state (active window, running apps)\n"
    "  - Verify prerequisites (required apps installed, files exist)\n"
    "  - Plan verification points (how to confirm each step succeeded)\n"
    "  - Define success criteria (final state description)\n"
    "  - Prepare fallback strategies (what to do if step fails)\n\n"
        
    "ACTION EXECUTION PRINCIPLES:\n"
        "  1. ATOMICITY: Each step should be a single, verifiable action\n"
    "     Bad example: \"Open browser and search\"\n"
    "     Good example: Step 1: \"Open browser\", Step 2: \"Navigate to search\", Step 3: \"Type query\"\n\n"
        
        "  2. DETERMINISM: Prefer actions with predictable outcomes\n"
        "     Priority: Keyboard shortcuts > Tab navigation > Text search > Visual click > Coordinate guess\n\n"
        
        "  3. VERIFICATION: After each critical action, verify state changed\n"
        "     Example: After \"open notepad\" → verify window title contains \"Notepad\"\n\n"
        
        "  4. TIMING: Always include wait steps where needed\n"
        "     • After launch: wait 2s\n"
        "     • After focus: wait 0.5s\n"
        "     • After click: wait 0.3s\n"
        "     • Before typing: verify focus + wait 0.5s\n\n"
        
        "  5. PRECISION: For coordinate-based actions, provide confidence\n"
        "     Format: {\"x\": 960, \"y\": 540, \"confidence\": 85, \"margin\": 10}\n\n"
        
    "ADAPTIVE FAILURE HANDLING:\n"
        "  IF action fails THEN:\n"
        "    1. Analyze failure mode (timeout, not found, wrong state)\n"
        "    2. Take screenshot to assess current state\n"
        "    3. Choose recovery strategy:\n"
        "       • App launch fail → Check if running → Focus existing OR Launch via Win+R\n"
        "       • Click miss → Retry with adjusted coords (±20px) OR Use keyboard alternative\n"
        "       • Typing fail → Verify focus → Clear field (Ctrl+A, Delete) → Retry\n"
        "       • Window not found → Wait 2s → Enumerate windows → Match by partial title\n"
        "       • Element hidden → Scroll to view → Retry locate → Use alternative path\n"
        "    4. Update plan with recovery step\n"
        "    5. Continue OR abort if unrecoverable\n\n"
        
    "VERIFICATION STRATEGIES:\n"
        "  • Window Title Check: Active window title contains expected text\n"
        "  • Visual Confirmation: Screenshot analysis shows expected element/state\n"
        "  • Process Check: Target process running in process list\n"
        "  • File System: Expected file exists at path\n"
        "  • Clipboard: Clipboard contains expected content\n"
        "  • State Indicator: Button/menu state changed (enabled/disabled/checked)\n\n"
        
    "RISK MITIGATION:\n"
        "  • ALWAYS verify window focus before keyboard input (prevents typing in wrong window)\n"
        "  • NEVER assume state (always verify with screenshot or query)\n"
        "  • ALWAYS provide fallback for coordinate-based actions\n"
        "  • LIMIT retry attempts (max 3) to avoid infinite loops\n"
        "  • HANDLE unexpected dialogs (OK/Cancel/Close popups)\n"
        "  • ESCAPE hatch: If stuck, press Esc or close window and restart\n\n"
        
    "OPTIMIZATION TECHNIQUES:\n"
        "  • Batch operations: Group similar actions (type entire sentence vs char-by-char)\n"
        "  • Parallel preparation: While waiting, plan next steps\n"
        "  • State caching: Remember window positions, element locations\n"
        "  • Smart waiting: Poll for state change vs fixed wait\n"
        "  • Shortcut chains: Win+R → \"notepad\" → Enter (faster than Start menu)\n\n"
        
    "ACTION SPECIFICATION FORMAT:\n"
        "  Every action MUST include:\n"
        "  {\n"
        "    \"action\": \"<action_name>\",           // From available actions registry\n"
        "    \"target\": \"<target_description>\",   // What to interact with\n"
        "    \"parameters\": {                      // Action-specific params\n"
        "      \"x\": 960,                          // Coordinate X (if applicable)\n"
        "      \"y\": 540,                          // Coordinate Y (if applicable)\n"
        "      \"text\": \"hello\",                  // Text to type (if applicable)\n"
        "      \"confidence\": 85                   // Your confidence 0-100\n"
        "    },\n"
        "    \"expected_outcome\": \"<what should happen>\",\n"
        "    \"verification\": \"<how to verify success>\",\n"
        "    \"fallback\": \"<alternative if fails>\",\n"
        "    \"estimated_time\": \"<duration in seconds>\"\n"
        "  }\n"
    )

    TASK_PLANNING_RULES = (
        "═══════════════════════════════════════════════════════════\n"
        "TASK PLANNING METHODOLOGY - SYSTEMATIC APPROACH\n"
        "═══════════════════════════════════════════════════════════\n\n"
        
    "COGNITIVE PROCESS (Execute in order):\n"
        "  1. UNDERSTAND: Parse user intent, identify key actions and goals\n"
        "  2. DECOMPOSE: Break complex task into atomic, executable steps\n"
        "  3. SEQUENCE: Order steps logically with dependencies\n"
        "  4. SPECIFY: For each step, define action, target, parameters, verification\n"
        "  5. VALIDATE: Check plan completeness, feasibility, edge cases\n"
        "  6. OPTIMIZE: Combine steps where safe, add parallelization opportunities\n\n"
        
    "STEP REQUIREMENTS (Each step MUST have):\n"
        "  • Unique step_number (sequential integers starting from 1)\n"
        "  • Valid action name (from provided actions registry)\n"
        "  • Clear target description (window name, element, coordinates)\n"
        "  • Complete parameters object (all required fields for action)\n"
        "  • Expected outcome (what should happen if successful)\n"
        "  • Verification method (how to confirm step worked)\n"
        "  • Fallback strategy (what to try if step fails)\n"
        "  • Time estimate (realistic duration in seconds)\n\n"
        
    "REASONING REQUIREMENTS:\n"
        "  • Be EXPLICIT: State your assumptions and logic\n"
        "  • Be CONCISE: Avoid unnecessary verbosity\n"
        "  • Be TECHNICAL: Use precise terminology (window focus, process name, coordinates)\n"
        "  • Be REALISTIC: Consider Windows UI limitations and timing\n"
        "  • Be DEFENSIVE: Anticipate failures and plan mitigations\n\n"
        
    "ACTIONS REGISTRY USAGE:\n"
        "  • ONLY use actions from the provided registry\n"
        "  • Match action names EXACTLY (case-sensitive)\n"
        "  • Provide ALL required parameters for each action\n"
        "  • Reference examples to understand proper usage\n"
        "  • If uncertain, choose simpler action (keyboard over mouse)\n\n"
        
    "COMPLEXITY ASSESSMENT:\n"
        "  • SIMPLE: 1-3 steps, single app, no branching (e.g., \"open calculator\")\n"
        "  • MEDIUM: 4-8 steps, multiple apps or navigation (e.g., \"open browser, search, click result\")\n"
        "  • COMPLEX: 9+ steps, conditionals, verification loops (e.g., \"search, filter, extract data, save file\")\n\n"
        
    "SUCCESS CRITERIA DEFINITION:\n"
    "  Define OBSERVABLE, VERIFIABLE conditions that indicate task completion:\n"
    "  - Example success criterion: \"Edge browser is closed (not visible in window list)\"\n"
    "  - Example success criterion: \"YouTube video is playing (audio detected or visual confirmation)\"\n"
    "  - Example of insufficient criterion: \"Task is done\"\n"
    "  - Example of insufficient criterion: \"Everything worked\"\n\n"
        
    "PREREQUISITE IDENTIFICATION:\n"
        "  List what MUST be true before task can start:\n"
        "  • Required applications installed (e.g., \"Edge browser must be installed\")\n"
        "  • Network connectivity (e.g., \"Internet connection required for YouTube\")\n"
        "  • Permissions (e.g., \"Administrator rights for system settings\")\n"
        "  • Files/folders exist (e.g., \"Download folder must be accessible\")\n"
        "  • Screen state (e.g., \"Desktop visible, no fullscreen apps blocking\")\n\n"
        
    "RISK ASSESSMENT:\n"
        "  Identify potential_issues that could cause failure:\n"
        "  • UI timing (app slow to load, page slow to render)\n"
        "  • Coordinate accuracy (button moved, window resized)\n"
        "  • State assumptions (app already open, unexpected dialog)\n"
        "  • External factors (network latency, system performance)\n"
        "  • User interruption (focus stolen by notification/popup)\n"
    )

    TASK_PLANNING_OUTPUT = (
        "Return JSON only matching this schema:\n"
        "{\n"
        "  \"understood\": bool,\n"
        "  \"confidence\": int (0-100),\n"
        "  \"task_summary\": string,\n"
        "  \"complexity\": \"simple\"|\"medium\"|\"complex\",\n"
        "  \"estimated_duration\": string (e.g., \"2 minutes\"),\n"
        "  \"success_criteria\": [string],\n"
        "  \"prerequisites\": [string],\n"
        "  \"steps\": [\n"
        "    {\n"
        "      \"step_number\": int,\n"
        "      \"action\": string,\n"
        "      \"target\": string,\n"
        "      \"parameters\": object,\n"
        "      \"expected_outcome\": string,\n"
        "      \"verification\": string,\n"
        "      \"fallback\": string,\n"
        "      \"estimated_time\": string\n"
        "    }\n"
        "  ],\n"
        "  \"potential_issues\": [string],\n"
        "  \"adaptive_strategies\": [string],\n"
        "  \"clarification_needed\": string|null\n"
        "}"
    )

    CHAIN_OF_THOUGHT = (
        "═══════════════════════════════════════════════════════════\n"
        "STRUCTURED REASONING PROTOCOL - THINK BEFORE YOU ACT\n"
        "═══════════════════════════════════════════════════════════\n\n"
        
        "Before generating your JSON plan, reason through these phases:\n\n"
        
        "PHASE 1 - TASK COMPREHENSION:\n"
        "  → What is the user asking me to do? (Goal identification)\n"
        "  → What are the key verbs/actions? (open, search, click, type, close)\n"
        "  → What are the target objects? (applications, URLs, elements)\n"
        "  → What are the constraints? (timing, order, conditions)\n"
        "  → What is the desired end state? (Success definition)\n"
        "  Example: \"Open Edge and search YouTube for cat videos\"\n"
        "    → Goal: Navigate to YouTube, search for content\n"
        "    → Actions: open, navigate, search, input\n"
        "    → Targets: Edge browser, youtube.com, search bar\n"
        "    → End state: YouTube search results for 'cat videos' displayed\n\n"
        
        "PHASE 2 - STATE ANALYSIS:\n"
        "  → What is the current system state? (from context)\n"
        "  → Which applications are running?\n"
        "  → What window is active?\n"
        "  → Screen resolution and layout?\n"
        "  → Any blockers or prerequisites missing?\n"
        "  Example Context: {active_window: 'Desktop', running: ['explorer.exe']}\n"
        "    → Currently on desktop, no apps open\n"
        "    → Need to launch Edge from scratch\n"
        "    → Screen space available for new window\n\n"
        
        "PHASE 3 - GAP ANALYSIS:\n"
        "  → What needs to change to reach goal? (Delta from current to desired state)\n"
        "  → Which intermediate states must we pass through?\n"
        "  → What are the dependencies between states?\n"
        "  Example: Current=Desktop, Goal=YouTube search results\n"
        "    → Gap 1: No browser open → Need to launch Edge\n"
        "    → Gap 2: At start page → Need to navigate to youtube.com\n"
        "    → Gap 3: At homepage → Need to locate search, type query\n"
        "    → Gap 4: Query typed → Need to submit search\n"
        "    → Gap 5: Results showing → Goal achieved\n\n"
        
        "PHASE 4 - ACTION SELECTION:\n"
        "  → For each gap, what actions bridge it?\n"
        "  → Which action type is most reliable? (Refer to targeting hierarchy)\n"
        "  → What parameters does each action need?\n"
        "  → What could go wrong with each action?\n"
        "  Example: Gap 1 (Launch Edge)\n"
        "    → Option A: open_application (target='edge') - BEST (simple, reliable)\n"
        "    → Option B: Win+R → type 'msedge' → Enter - ALTERNATIVE (if A fails)\n"
        "    → Option C: Click Start → search → click icon - LAST RESORT (slow)\n"
        "    → Chosen: open_application with fallback to Option B\n\n"
        
        "PHASE 5 - RISK & FALLBACK PLANNING:\n"
        "  → What can fail at each step?\n"
        "  → How will I detect failure?\n"
        "  → What's the recovery strategy?\n"
        "  → When should I abort vs. retry?\n"
        "  Example Risks:\n"
        "    → Edge launch fails: Check if already running → focus existing OR use Win+R\n"
        "    → Navigation slow: Add wait step → verify page loaded → timeout after 10s\n"
        "    → Search not found: Take screenshot → locate visually → use keyboard nav (Tab)\n"
        "    → Click wrong element: Verify outcome → undo if possible → retry with adjusted coords\n\n"
        
        "PHASE 6 - VERIFICATION STRATEGY:\n"
        "  → After each step, how do I confirm success?\n"
        "  → What should I observe in screenshot?\n"
        "  → What window title should appear?\n"
        "  → What elements should be visible?\n"
        "  → How do I know the ENTIRE task succeeded?\n"
        "  Example Verifications:\n"
        "    → After launch Edge: Window title contains \"Microsoft Edge\"\n"
        "    → After navigate: URL bar shows \"youtube.com\"\n"
        "    → After search: Results list visible, video thumbnails present\n"
        "    → Task complete: Specific video playing OR results page stable for 2s\n\n"
        
    "LEARNING FROM EXAMPLES:\n"
        "  Study the provided action examples to understand:\n"
        "  • Correct parameter formats\n"
        "  • Expected input/output patterns\n"
        "  • Common use cases and variations\n"
        "  • How to combine actions into workflows\n\n"
        
        "After completing all phases, synthesize your reasoning into the JSON plan.\n"
    )

    # Common UI automation patterns for specific scenarios
    BROWSER_AUTOMATION_GUIDE = (
    "BROWSER AUTOMATION PATTERNS:\n"
        "  Navigation:\n"
        "    1. Open browser → wait 2s for launch\n"
        "    2. Focus address bar (Ctrl+L or Alt+D)\n"
        "    3. Type URL → press Enter\n"
        "    4. Wait for page load (2-10s, verify by checking for element)\n"
        "  \n"
        "  Searching:\n"
        "    1. Locate search box (visual or Ctrl+F)\n"
        "    2. Click to focus OR use Tab navigation\n"
        "    3. Type search query\n"
        "    4. Press Enter OR click search button\n"
        "    5. Wait for results (verify by checking for result items)\n"
        "  \n"
        "  Clicking Elements:\n"
        "    1. Take screenshot of current page\n"
        "    2. Locate element visually (get coordinates)\n"
        "    3. Scroll into view if needed\n"
        "    4. Click at coordinates with margin\n"
        "    5. Verify action (check URL change, new content appears)\n"
        "  \n"
        "  Common Issues:\n"
        "    • Lazy loading: Wait for content → scroll to trigger load\n"
        "    • Popups/Cookies: Dismiss with Esc or locate 'Accept/Close' button\n"
        "    • Redirects: Allow time for redirect, verify final URL\n"
    )

    FILE_OPERATIONS_GUIDE = (
    "FILE & FOLDER OPERATIONS:\n"
        "  Opening Files:\n"
        "    Method 1 (Direct): Win+R → type full path → Enter\n"
        "    Method 2 (Explorer): Open explorer → navigate → double-click file\n"
        "    Method 3 (App): Open app → Ctrl+O → navigate → select → open\n"
        "  \n"
        "  Saving Files:\n"
        "    1. Ctrl+S to open save dialog\n"
        "    2. Wait for dialog (1-2s)\n"
        "    3. Type filename in name field\n"
        "    4. Navigate to folder if needed (click folders or type path)\n"
        "    5. Click Save button OR press Enter\n"
        "    6. Verify file exists (check file system or title bar update)\n"
        "  \n"
        "  File Dialog Navigation:\n"
        "    • Address bar: Click → type path → Enter (fastest)\n"
        "    • Folder tree: Click folder icons to expand/navigate\n"
        "    • Quick access: Use pinned folders on left sidebar\n"
        "    • Recent files: Look in Recent Files section\n"
    )

    TEXT_EDITING_GUIDE = (
    "TEXT EDITING PATTERNS:\n"
        "  Entering Text:\n"
        "    1. Focus target window (focus_window action)\n"
        "    2. Click text field OR Tab to it\n"
        "    3. Verify cursor in field (check for blinking cursor)\n"
        "    4. Type text (use type_text action)\n"
        "    5. Verify text appears (visual check)\n"
        "  \n"
        "  Editing Existing Text:\n"
        "    1. Select all (Ctrl+A) OR triple-click\n"
        "    2. Delete (Backspace) OR just start typing (overwrites)\n"
        "    3. Use Ctrl+Z to undo if needed\n"
        "  \n"
        "  Common Shortcuts:\n"
        "    • Ctrl+A: Select all\n"
        "    • Ctrl+C/V/X: Copy/Paste/Cut\n"
        "    • Ctrl+Z/Y: Undo/Redo\n"
        "    • Ctrl+F: Find\n"
        "    • Ctrl+Home/End: Jump to start/end\n"
    )

    WINDOW_MANAGEMENT_GUIDE = (
    "WINDOW MANAGEMENT STRATEGIES:\n"
        "  Finding Windows:\n"
        "    1. Query running processes (get list of .exe)\n"
        "    2. Query window titles (get all open windows)\n"
        "    3. Match by partial title (case-insensitive)\n"
        "    4. If multiple matches, choose most recent OR specific criteria\n"
        "  \n"
        "  Focusing Windows:\n"
        "    Method 1: focus_window action with title\n"
        "    Method 2: Alt+Tab to cycle (if you know position)\n"
        "    Method 3: Click taskbar icon (requires coordinates)\n"
        "  \n"
        "  Arranging Windows:\n"
        "    • Snap left: Win+Left Arrow\n"
        "    • Snap right: Win+Right Arrow\n"
        "    • Maximize: Win+Up Arrow OR double-click title bar\n"
        "    • Minimize: Win+Down Arrow OR click minimize button\n"
        "  \n"
        "  Closing Windows:\n"
        "    Priority:\n"
        "      1. Alt+F4 (closes active window, reliable)\n"
        "      2. close_application action (by name)\n"
        "      3. Click X button (requires coordinates)\n"
    )

    SCREEN_ANALYSIS_TEMPLATE = (
        "═══════════════════════════════════════════════════════════\n"
        "WINDOWS UI SCREEN ANALYSIS - VISION TASK\n"
        "═══════════════════════════════════════════════════════════\n\n"
        
        "You are analyzing a Windows desktop screenshot for UI automation purposes.\n"
        "Your goal: Provide actionable information for a bot to interact with this screen.\n\n"
        
        "ANALYSIS STRUCTURE (Use this exact format):\n\n"
        
    "### PRIMARY CONTEXT\n"
        "1-2 sentences describing what is visible and happening on screen.\n"
        "Example: \"Microsoft Edge browser is open showing YouTube homepage. Search bar is visible at top center.\"\n\n"
        
    "### APPLICATION DETAILS\n"
        "  • Application: [Name and version if visible]\n"
        "  • Window Title: [Exact title bar text]\n"
        "  • Window State: [Maximized/Windowed/Minimized]\n"
        "  • Focus State: [Active/Inactive]\n"
        "  • Visible Area: [Approximate percentage of screen]\n\n"
        
    "### INTERACTIVE ELEMENTS\n"
        "List ALL interactive elements with precise details:\n"
        "Format: [Type] \"Text/Label\" at (~X, ~Y) - [State] - [Confidence%]\n"
        "Examples:\n"
        "  • Button \"Search\" at (~1200, ~150) - Enabled - 95%\n"
        "  • Text Field \"Enter query\" at (~600, ~200) - Empty, Focused - 90%\n"
        "  • Checkbox \"Remember me\" at (~400, ~500) - Unchecked - 85%\n"
        "  • Link \"Sign In\" at (~1400, ~80) - Clickable - 98%\n"
        "  • Dropdown \"Language\" at (~1500, ~100) - Collapsed - 92%\n\n"
        
        "Element Types to identify:\n"
        "  - Buttons (regular, icon, toggle)\n"
        "  - Text fields (input, password, search, textarea)\n"
        "  - Links (hyperlinks, navigation)\n"
        "  - Checkboxes and radio buttons\n"
        "  - Dropdowns and combo boxes\n"
        "  - Menus (menu bar, context menu, dropdown menu)\n"
        "  - Tabs and navigation items\n"
        "  - Icons and toolbar items\n"
        "  - Scroll bars\n\n"
        
    "### ACTIONABLE ITEMS (Priority Order)\n"
        "List top 5-10 actions bot could take RIGHT NOW:\n"
        "Format: [Priority] [Action] on [Target] at (~X, ~Y) → [Outcome] [Confidence%]\n"
        "Examples:\n"
        "  1. CLICK on \"Search\" button at (~1200, ~150) → Open search → 95%\n"
        "  2. TYPE in search field at (~600, ~200) → Enter search query → 90%\n"
        "  3. HOTKEY Ctrl+T → Open new tab → 100%\n"
        "  4. SCROLL down 500px → View more content → 85%\n"
        "  5. CLICK on video thumbnail at (~400, ~600) → Play video → 88%\n\n"
        
        "Action Methods:\n"
        "  - CLICK: Direct mouse click at coordinates\n"
        "  - DOUBLE_CLICK: Double-click for opening items\n"
        "  - RIGHT_CLICK: Context menu\n"
        "  - TYPE: Keyboard input into focused field\n"
        "  - HOTKEY: Keyboard shortcut (most reliable)\n"
        "  - TAB: Navigate to element via Tab key\n"
        "  - SCROLL: Scroll viewport\n"
        "  - DRAG: Drag and drop operation\n\n"
        
    "### COORDINATE ANCHORS\n"
        "List 5-10 reliable reference points for navigation:\n"
        "Format: (~X, ~Y) - [Description] - [Reliability]\n"
        "Examples:\n"
        "  • (~0, ~0) - Top-left corner of window - 100%\n"
        "  • (~960, ~540) - Screen center (1920×1080) - 100%\n"
        "  • (~1200, ~150) - Search button center - 95%\n"
        "  • (~50, ~100) - Window icon/menu area - 98%\n"
        "  • (~1400, ~80) - Top-right corner utilities - 90%\n\n"
        
        "Coordinate Guidelines:\n"
        "  - Origin (0,0) is top-left of PRIMARY screen\n"
        "  - X increases left to right\n"
        "  - Y increases top to bottom\n"
        "  - Always provide center point of element (not edge)\n"
        "  - Include margin of error (typically ±5-20px)\n"
        "  - Flag low confidence (<70%) coordinates\n\n"
        
    "### STATIC TEXT CONTENT\n"
        "List important text visible on screen:\n"
        "  • Page Title: [Main heading]\n"
        "  • Key Labels: [Important text labels]\n"
        "  • Status Messages: [Any status/error messages]\n"
        "  • Instructions: [User-facing instructions]\n\n"
        
    "### AUTOMATION CONSIDERATIONS\n"
        "Risks, challenges, and recommendations:\n"
        "  • Element Overlap: [Any elements obscuring others?]\n"
        "  • Dynamic Content: [Loading indicators, animations?]\n"
        "  • Timing Issues: [Delays expected before interaction?]\n"
        "  • Accessibility: [Can element be reached via keyboard?]\n"
        "  • State Dependencies: [Prerequisites before action?]\n"
        "  • Verification Points: [How to confirm action succeeded?]\n"
        "  • Alternative Paths: [Backup methods if primary fails?]\n\n"
        
    "CRITICAL RULES:\n"
    "  - Estimate coordinates as accurately as possible\n"
    "  - Provide confidence scores (0-100%) for all estimates\n"
    "  - Flag elements that are partially visible or unclear\n"
    "  - Note any pop-ups, dialogs, or overlays\n"
    "  - Identify fastest or most reliable interaction method\n"
    "  - Consider keyboard alternatives for every mouse action\n"
    "  - Be specific about element states (enabled, disabled, focused)\n"
    )

    ELEMENT_LOCATION_TEMPLATE = (
        "You are a spatial reasoning assistant. Return JSON with: reasoning {search_strategy, identification, confidence_basis, "
        "alternatives_considered}, found (bool), confidence (0-100), x, y (pixel center), margin_of_error_px, element_type, "
        "position {description}, pixel_estimate {width_px, height_px}, visual_characteristics {visible_text, icon_description, "
        "color, styling}, surrounding_context {above, below, left, right}, interaction_guidance {click_target, hover_sensitive, "
        "keyboard_alternative}, risks (list), suggestions (list). If not found set found=false, confidence=0, explain why, and "
        "suggest how to reveal it or alternatives."
    )

    VERIFICATION_TEMPLATE = (
        "You are verifying whether an action achieved the expected change. Compare BEFORE vs AFTER. "
        "Return JSON with keys: success (bool), confidence (0-100), issue (blank if success), observed_state (short summary), "
        "evidence {supporting, missing}, next_step. Mark success false if evidence is incomplete or ambiguous."
    )

    NEXT_ACTION_TEMPLATE = (
        "You are an adaptive planner. Use current state and recent history to choose the safest next action. Return JSON with: "
        "reasoning {situation_summary, progress_estimate, analysis, strategy, alternatives_considered, decision_rationale}, "
        "action, target, parameters, expected_outcome, verification {method, success_indicators, failure_indicators}, "
        "fallback_plan {if_fails, alternative_sequence}, confidence, estimated_remaining_steps, adaptive_notes. "
        "Avoid repeating the same failed action without a change in approach."
    )

    @staticmethod
    def build_task_planning_prompt(
        user_request: str,
        context: Optional[Dict[str, Any]] = None,
        *,
        complexity_hint: str = "auto",
        include_examples: bool = True,
    ) -> str:
        """Build a comprehensive task-planning prompt with specialized guidance."""

        if complexity_hint == "auto":
            complexity = _detect_complexity(user_request)
        else:
            complexity = complexity_hint

        # Analyze request for specialized guidance
        request_lower = user_request.lower()
        needs_browser_guide = any(word in request_lower for word in 
                                   ['browser', 'edge', 'chrome', 'firefox', 'youtube', 'google', 
                                    'search', 'website', 'url', 'navigate', 'web', 'page', 'link'])
        needs_file_guide = any(word in request_lower for word in 
                                ['file', 'folder', 'save', 'open', 'document', 'explorer', 
                                 'directory', 'path', 'download'])
        needs_text_guide = any(word in request_lower for word in 
                                ['type', 'write', 'text', 'notepad', 'edit', 'word', 'input', 
                                 'typing', 'enter'])
        needs_window_guide = any(word in request_lower for word in 
                                  ['window', 'close', 'minimize', 'maximize', 'focus', 'switch',
                                   'alt+tab', 'taskbar'])

        sections = [PromptBuilder.TASK_PLANNING_SYSTEM]

        system_configuration = _collect_system_configuration(context)
        if system_configuration:
            sections.append(system_configuration)

        sections.extend([
            PromptBuilder.WINDOWS_CONTEXT,
            PromptBuilder.TASK_PLANNING_RULES,
            f"═══════════════════════════════════════════════════════════\n"
            f"USER REQUEST: \"{user_request}\"\n"
            f"═══════════════════════════════════════════════════════════",
        ])

        if context:
            formatted_context = _format_context(context)
            if formatted_context:
                sections.append(formatted_context)

        # Add specialized guides based on task type OR if specific keywords detected
        if complexity in {"medium", "complex"} or any([needs_browser_guide, needs_file_guide, 
                                                         needs_text_guide, needs_window_guide]):
            if complexity not in {"medium", "complex"}:
                # Add execution strategies for keyword-triggered guides
                sections.append(PromptBuilder.EXECUTION_STRATEGIES)
            
            # Add relevant specialized guides
            if needs_browser_guide:
                sections.append(PromptBuilder.BROWSER_AUTOMATION_GUIDE)
            if needs_file_guide:
                sections.append(PromptBuilder.FILE_OPERATIONS_GUIDE)
            if needs_text_guide:
                sections.append(PromptBuilder.TEXT_EDITING_GUIDE)
            if needs_window_guide:
                sections.append(PromptBuilder.WINDOW_MANAGEMENT_GUIDE)

        if complexity == "complex":
            sections.append(PromptBuilder.CHAIN_OF_THOUGHT)

        sections.append(PromptBuilder.TASK_PLANNING_OUTPUT)

        if complexity == "simple":
            sections.append(action_registry.to_compact_prompt_string())
        else:
            sections.append(
                action_registry.to_prompt_string(
                    max_per_category=10 if complexity == "complex" else 6,
                    include_examples=include_examples,
                )
            )

        return _join_sections(sections)

    @staticmethod
    def build_screen_analysis_prompt(
        question: Optional[str] = None,
        *,
        focus_area: Optional[str] = None,
    ) -> str:
        """Build a screen analysis prompt."""

        focus_map = {
            "center": "Focus on the central 60% of the screen where interaction is likely.",
            "top": "Focus on the top 25% of the screen (menu bars, navigation headers).",
            "bottom": "Focus on the bottom 25% (status bars, footers).",
            "left": "Focus on the left third (navigation panels).",
            "right": "Focus on the right third (details panels).",
            "full": "Analyze the entire screen from edge to edge.",
        }

        focus_note = focus_map.get(focus_area or "", "")
        question_note = f"Answer this question explicitly: {question}" if question else ""
        sections = [
            PromptBuilder.SCREEN_ANALYSIS_TEMPLATE,
            "Estimate coordinates in pixels from the top-left origin, e.g., (~960,~180), and flag low confidence.",
            focus_note,
            question_note,
        ]
        return _join_sections(sections)

    @staticmethod
    def build_element_location_prompt(element_description: str) -> str:
        """Build a locator prompt for a specific UI element."""

        sections = [
            PromptBuilder.ELEMENT_LOCATION_TEMPLATE,
            f"Target description: \"{element_description}\".",
            "Report JSON only.",
        ]
        return _join_sections(sections)

    @staticmethod
    def build_verification_prompt(expected_change: str) -> str:
        """Build a verification prompt for before/after comparison."""

        sections = [
            PromptBuilder.VERIFICATION_TEMPLATE,
            f"Expected change: \"{expected_change}\".",
            "Return JSON only; default to failure if evidence is unclear.",
        ]
        return _join_sections(sections)

    @staticmethod
    def build_next_action_prompt(current_state: str, goal: str, history: List[str]) -> str:
        """Build a next-action selection prompt."""

        recent_history = history[-5:] if history else []
        history_block = "\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(recent_history)) or "None"

        sections = [
            PromptBuilder.NEXT_ACTION_TEMPLATE,
            f"Goal: {goal}",
            f"Current state summary: {current_state}",
            f"Recent actions:\n{history_block}",
            "Return JSON only.",
        ]
        return _join_sections(sections)


class PromptOptimizer:
    """Lightweight helpers for prompt manipulation."""

    @staticmethod
    def compress_context(context: Dict[str, Any], max_items: int = 10) -> Dict[str, Any]:
        """Trim large context payloads to the most relevant data."""

        compressed = dict(context)
        if "running_processes" in compressed:
            compressed["running_processes"] = compressed["running_processes"][:max_items]
        return compressed

    @staticmethod
    def add_few_shot_examples(prompt: str, examples: List[Dict[str, str]]) -> str:
        """Append few-shot examples to a prompt when needed."""

        if not examples:
            return prompt

        example_lines = ["EXAMPLES:"]
        for index, example in enumerate(examples, start=1):
            example_lines.append(f"Example {index}:")
            example_lines.append(f"Request: {example.get('request', '')}")
            example_lines.append(f"Response: {example.get('response', '')}\n")

        return prompt + "\n\n" + "\n".join(example_lines)


prompt_builder = PromptBuilder()
