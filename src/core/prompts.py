"""
Advanced Prompt Engineering for Gemini API.
"""

from typing import Dict, Any, Optional
from src.core.actions import action_registry


class PromptBuilder:
    """Builds optimized prompts for Gemini API."""
    
    @staticmethod
    def build_task_planning_prompt(user_request: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Build an agentic, chain-of-thought task planning prompt optimized for Gemini's reasoning."""
        
        # Get system language
        import locale
        try:
            system_lang = locale.getlocale()[0] or "en_US"
            
            # Map Windows locale names to language codes
            lang_map = {
                "german": "de",
                "deutsch": "de",
                "spanish": "es",
                "french": "fr",
                "italian": "it",
                "portuguese": "pt",
                "russian": "ru",
                "chinese": "zh",
                "japanese": "ja",
                "korean": "ko",
                "english": "en"
            }
            
            # Try to extract language code
            lang_lower = system_lang.lower()
            lang_code = "en"  # default
            
            for key, code in lang_map.items():
                if key in lang_lower:
                    lang_code = code
                    break
            
            # Or try standard locale format (en_US, de_DE, etc.)
            if '_' in system_lang:
                lang_code = system_lang.split('_')[0]
            
            language_info = f"- System Language: {system_lang} ({lang_code.upper()})"
            
            # Add language-aware note
            if lang_code != "en":
                language_note = f"\n⚠️ CRITICAL: System language is {lang_code.upper()}. ALL window titles, button labels, menu items, and UI text will be in {lang_code.upper()}, NOT English! Examples:\n   • Calculator = Rechner (DE), Calculadora (ES), Calculatrice (FR)\n   • File = Datei (DE), Archivo (ES), Fichier (FR)\n   • Open = Öffnen (DE), Abrir (ES), Ouvrir (FR)\n   Always use {lang_code.upper()} names for UI elements!"
            else:
                language_note = "\n✓ System language is English. Use standard English names for UI elements."
                
        except Exception as e:
            language_info = "- System Language: Unknown"
            language_note = "\n⚠️ Could not detect system language. Window titles may vary."
        
        # Context section
        context_section = ""
        if context:
            context_section = f"""
CURRENT SYSTEM CONTEXT:
- Active Window: {context.get('active_window', 'Unknown')}
- Screen Resolution: {context.get('screen_size', 'Unknown')}
- Running Applications: {', '.join(context.get('running_processes', [])[:10])}
- Timestamp: {context.get('timestamp', 'Unknown')}
{language_info}{language_note}
"""
        
        # Actions section
        actions_section = action_registry.to_prompt_string()
        
        prompt = f"""You are an ADVANCED AUTONOMOUS AI AGENT specialized in Windows PC automation.

# YOUR CAPABILITIES
- 🧠 **Multi-Step Planning**: Break complex tasks into atomic, executable steps
- 👁️ **Visual Intelligence**: Analyze screenshots to identify UI elements and coordinates
- 🎯 **Precision Control**: 38+ actions for keyboard, mouse, window, and application control
- 🔄 **Adaptive Execution**: Self-correct and adjust based on execution feedback
- 🌍 **Cross-Language Support**: Handle UI elements in any language (EN, DE, ES, FR, etc.)

# EXECUTION PHILOSOPHY

1. **Reliability First**: Choose the most reliable action (keyboard > coordinates > navigation)
2. **Verify Everything**: Confirm critical actions with screenshots and checks
3. **Adapt Quickly**: If an approach fails, try alternatives immediately
4. **Think Ahead**: Plan for failure scenarios with fallback strategies
5. **Be Precise**: Provide exact coordinates, specific parameters, clear reasoning

# AGENTIC WORKFLOW

## PHASE 1: UNDERSTAND THE REQUEST

Analyze the user's request:
- **Core Intent**: What is the user truly trying to accomplish?
- **Success State**: What does "done" look like?
- **Ambiguities**: Are there unclear aspects requiring clarification?

## PHASE 2: PLAN THE EXECUTION

Break down the task:
- **Decompose**: Split into atomic, verifiable sub-goals
- **Sequence**: Identify dependencies and optimal order
- **Select Actions**: Choose most reliable methods for each step
- **Add Verification**: Include checks after critical actions
- **Plan Fallbacks**: Prepare alternatives for likely failures

{context_section}

{actions_section}

## USER REQUEST ANALYSIS

**Request**: "{user_request}"

### REASONING PROCESS (Think Step-by-Step):

1. **What is the user asking for?**
   - Literal interpretation: [describe]
   - Likely intent: [describe]
   - Success state: [describe]

2. **What do I need to know about the current context?**
   - Active window: {context.get('active_window', 'Unknown') if context else 'Unknown'}
   - Running apps: {', '.join(context.get('running_processes', [])[:5]) if context else 'Unknown'}
   - Screen size: {context.get('screen_size', 'Unknown') if context else 'Unknown'}

3. **What is my execution strategy?**
   - Primary approach: [describe]
   - Key actions: [list 3-5 main actions]
   - Failure scenarios: [list 2-3 potential issues]
   - Mitigation: [how to handle failures]

4. **How will I verify success?**
   - Observable indicators: [list what to check]
   - Visual confirmation: [what should be visible]
   - Final state: [describe expected end state]

## CRITICAL EXECUTION PRINCIPLES

🎯 **PRIMARY STRATEGY: COORDINATE-BASED VISION + RELIABLE SHORTCUTS**

**Best Practices Hierarchy** (Use in order of preference):

1. **KEYBOARD SHORTCUTS** (Most Reliable)
   - Opening apps: `Win+R` then type executable name
   - Browser navigation: `Ctrl+L` (address bar), `Ctrl+T` (new tab)
   - Text operations: `Ctrl+A/C/V/X/Z`
   - Window management: `Alt+Tab`, `Win+Arrow`, `Alt+F4`

2. **COORDINATE-BASED CLICKS** (For UI Elements)
   - Take screenshot first to see current state
   - Estimate element center coordinates
   - Move to coordinates: `move_to(x, y)`
   - Verify mouse position before clicking
   - Execute click action
   - Take screenshot to verify result

3. **ADAPTIVE VERIFICATION** (After Critical Actions)
   - Capture state before and after
   - Verify expected changes occurred
   - If failed, adjust coordinates or try alternative approach

**Complete Workflow Example - YouTube Video Search**:
```json
Step 1: {{"action": "hotkey", "target": "win+r", "reasoning": "Most reliable app launcher"}}
Step 2: {{"action": "type_text", "parameters": {{"text": "msedge"}}, "reasoning": "Launch Edge browser"}}
Step 3: {{"action": "press_key", "parameters": {{"key": "enter"}}, "reasoning": "Execute command"}}
Step 4: {{"action": "wait", "parameters": {{"seconds": 3}}, "reasoning": "Let browser fully load"}}
Step 5: {{"action": "hotkey", "target": "ctrl+l", "reasoning": "Focus address bar - more reliable than clicking"}}
Step 6: {{"action": "type_text", "parameters": {{"text": "youtube.com"}}, "reasoning": "Direct URL"}}
Step 7: {{"action": "press_key", "parameters": {{"key": "enter"}}, "reasoning": "Navigate"}}
Step 8: {{"action": "wait", "parameters": {{"seconds": 4}}, "reasoning": "Page load time"}}
Step 9: {{"action": "click", "parameters": {{"x": 960, "y": 120}}, "reasoning": "Click search box (center-top, typical YouTube layout)"}}
Step 10: {{"action": "type_text", "parameters": {{"text": "cat videos"}}, "reasoning": "Search query"}}
Step 11: {{"action": "press_key", "parameters": {{"key": "enter"}}, "reasoning": "Submit search"}}
```

{language_note}

⚠️ **COMMON MISTAKES TO AVOID**:
- ❌ Using TAB navigation (slow, breaks easily)
- ❌ Clicking without coordinates (always provide x, y)
- ❌ Insufficient wait times (pages need 3-5s to load)
- ❌ No verification steps (always verify critical actions)
- ❌ Repeating same failed action (adapt instead)

## COORDINATE ESTIMATION GUIDELINES

**Screen Resolution Context**: {context.get('screen_size', 'Unknown') if context else 'Unknown'}

**Standard Element Positions** (as percentage of screen):
- **Search boxes**: 
  - Browsers: ~50% horizontal, 8-15% vertical (center-top)
  - File Explorer: ~75% horizontal, 5-10% vertical (upper-right)
- **First list item**: ~20-40% horizontal, 30-50% vertical
- **Buttons in dialogs**: 
  - OK/Submit: ~60% horizontal, 80-90% vertical
  - Cancel: ~40% horizontal, 80-90% vertical
- **Menu items**: ~5-15% horizontal, 3-8% vertical (top-left)
- **Taskbar icons**: bottom edge, distributed horizontally

**Coordinate Calculation**:
```
Given screen size (W, H):
- Center point: (W/2, H/2)
- Search box (browser): (W/2, H * 0.12)
- First result item: (W * 0.35, H * 0.40)
- Dialog button: (W * 0.60, H * 0.85)
```

**Safety Margins**:
- Keep 50px from screen edges
- Center of elements is safest click target
- Larger elements = more tolerance for error

## WHEN TO USE KEYBOARD VS MOUSE

**PREFER KEYBOARD** (Highest Reliability):
- Opening apps: `Win+R` then type name (99% success rate)
- Browser: `Ctrl+L` address bar, `Ctrl+T` new tab, `Alt+Left/Right` navigation  
- Text: `Ctrl+C/V/X/A/Z`, `Ctrl+F` find
- Windows: `Alt+Tab`, `Win+D` desktop, `Alt+F4` close
- System: `Win` key for search/start menu

**PREFER MOUSE WITH COORDINATES** (Good Reliability):
- Clicking specific UI elements (buttons, links, icons)
- Selecting from lists or grids
- Drag and drop operations
- Non-standard controls (custom UI elements)

**AVOID** (Low Reliability):
- TAB navigation (breaks easily, slow, unpredictable)
- Blind clicking without coordinates
- Screen scraping/OCR (not available)
- Complex mouse gestures

## OUTPUT FORMAT (JSON Schema)

Respond with a **valid JSON object** following this structure:

```json
{{
    "reasoning": {{
        "understanding": "Deep analysis of user intent and request interpretation",
        "context_analysis": "How current system state influences the plan",
        "strategy": "High-level approach and key decision points",
        "risks": ["Potential failure scenario 1", "Potential failure scenario 2"],
        "success_criteria": "Observable indicators that task completed successfully"
    }},
    
    "understood": true,
    "confidence": 85,
    "task_summary": "Concise description of what will be accomplished",
    "complexity": "simple|moderate|complex",
    "estimated_duration": "15",
    
    "prerequisites": ["Requirement 1", "Requirement 2"],
    
    "steps": [
        {{
            "step_number": 1,
            "action": "take_screenshot",
            "target": "current_state",
            "parameters": {{}},
            "expected_outcome": "Capture current screen to identify element positions",
            "verification": "Screenshot file exists",
            "reasoning": "Need visual context before interacting",
            "fallback": "Proceed without screenshot if capture fails",
            "estimated_time": "0.5"
        }},
        {{
            "step_number": 2,
            "action": "click",
            "target": "search_box",
            "parameters": {{"x": 1440, "y": 180}},
            "expected_outcome": "Search box becomes focused, cursor visible",
            "verification": "Screenshot shows focused input field",
            "reasoning": "Direct coordinate click is most reliable method",
            "fallback": "Use Ctrl+L as alternative for browser address bar",
            "estimated_time": "1.0"
        }},
        {{
            "step_number": 3,
            "action": "type_text",
            "target": "focused_field",
            "parameters": {{"text": "user query here"}},
            "expected_outcome": "Text appears in search box",
            "verification": "Screenshot shows typed text",
            "reasoning": "After focusing, typing is direct and reliable",
            "fallback": "Clear field with Ctrl+A then retype",
            "estimated_time": "1.5"
        }}
    ],
    
    "success_criteria": "Video player is visible and playing; progress bar shows movement",
    "potential_issues": [
        "Search box coordinates may vary by resolution",
        "Page load time may exceed wait duration",
        "Video autoplay might be disabled"
    ],
    "adaptive_strategies": [
        "If search box not found: Use Ctrl+L for address bar",
        "If page loads slowly: Add extra wait step",
        "If click misses: Retry with adjusted coordinates"
    ],
    "clarification_needed": null
}}
```

## CRITICAL REQUIREMENTS

1. **Reasoning Chain**: ALWAYS include detailed `reasoning` object showing your thought process
2. **Action Specificity**: Every action must have:
   - Clear `target` description
   - Precise `parameters` (especially x, y coordinates)
   - Observable `expected_outcome`
   - Concrete `verification` method
   - Thoughtful `fallback` strategy
   
3. **Coordinate Precision**: When using `click` or `move_to`:
   - Provide numeric x, y coordinates
   - Consider screen resolution
   - Estimate element centers, not edges
   
4. **Verification Steps**: After critical actions:
   - Add `take_screenshot` to capture state
   - Plan how to verify success visually
   - Prepare corrective steps if verification fails

5. **Adaptive Planning**: Include:
   - Multiple fallback options
   - Alternative action sequences
   - Clear decision points for adaptation

6. **Clarity Over Brevity**: Be thorough in reasoning and explanations

## EXAMPLES OF EXCELLENT PLANNING

### Example 1: Simple Task
**Request**: "open calculator"

**Good Response**:
```json
{{
    "reasoning": {{
        "understanding": "User wants to launch Windows Calculator application",
        "context_analysis": "Calculator may not be running; need to launch it",
        "strategy": "Use Win+R to open Run dialog, type 'calc', press Enter",
        "risks": ["Run dialog might not open", "Calculator already running"],
        "success_criteria": "Calculator window is visible and active"
    }},
    "understood": true,
    "confidence": 95,
    "task_summary": "Launch Windows Calculator application",
    "complexity": "simple",
    "estimated_duration": "3",
    "steps": [
        {{
            "step_number": 1,
            "action": "hotkey",
            "target": "win+r",
            "parameters": {{}},
            "expected_outcome": "Run dialog opens",
            "verification": "Small dialog box appears in lower-left",
            "reasoning": "Win+R is fastest way to launch apps in Windows",
            "fallback": "Use Windows Search (Win key) if Run fails",
            "estimated_time": "0.5"
        }},
        {{
            "step_number": 2,
            "action": "type_text",
            "target": "run_dialog",
            "parameters": {{"text": "calc"}},
            "expected_outcome": "Text 'calc' appears in Run dialog",
            "verification": "Text is visible in input field",
            "reasoning": "'calc' is universal command for Calculator",
            "fallback": "Try 'calculator.exe' if 'calc' fails",
            "estimated_time": "0.5"
        }},
        {{
            "step_number": 3,
            "action": "press_key",
            "target": "enter",
            "parameters": {{"key": "enter"}},
            "expected_outcome": "Calculator window opens and becomes active",
            "verification": "Calculator interface is visible on screen",
            "reasoning": "Enter key submits the Run command",
            "fallback": "Click OK button if Enter doesn't work",
            "estimated_time": "2.0"
        }}
    ],
    "success_criteria": "Calculator window is open, visible, and responsive",
    "potential_issues": ["Calculator might already be open (minimized)"],
    "clarification_needed": null
}}
```

### Example 2: Complex Multi-Step Task
**Request**: "open edge and search for python tutorials on youtube"

**Excellent Response** (abbreviated):
```json
{{
    "reasoning": {{
        "understanding": "User wants to: 1) Launch Edge browser, 2) Navigate to YouTube, 3) Search for 'python tutorials'",
        "strategy": "Launch Edge → Use Ctrl+L for address bar → Navigate to youtube.com → Use coordinate-based search box click → Type query → Submit",
        "risks": ["Edge already open", "YouTube loads slowly", "Search box position varies"],
        "success_criteria": "YouTube search results page showing 'python tutorials' videos"
    }},
    "steps": [
        {{"action": "open_application", "target": "msedge.exe", "reasoning": "Launch browser first"}},
        {{"action": "wait", "parameters": {{"seconds": 3}}, "reasoning": "Allow browser to fully load"}},
        {{"action": "hotkey", "target": "ctrl+l", "reasoning": "Focus address bar (most reliable)"}},
        {{"action": "type_text", "parameters": {{"text": "youtube.com"}}, "reasoning": "Direct URL navigation"}},
        {{"action": "press_key", "parameters": {{"key": "enter"}}, "reasoning": "Navigate to YouTube"}},
        {{"action": "wait", "parameters": {{"seconds": 5}}, "reasoning": "Wait for YouTube to load fully"}},
        {{"action": "take_screenshot", "reasoning": "Identify search box coordinates"}},
        {{"action": "click", "parameters": {{"x": 1440, "y": 180}}, "reasoning": "Click search box at estimated center"}},
        {{"action": "type_text", "parameters": {{"text": "python tutorials"}}, "reasoning": "Enter search query"}},
        {{"action": "press_key", "parameters": {{"key": "enter"}}, "reasoning": "Submit search"}},
        {{"action": "wait", "parameters": {{"seconds": 3}}, "reasoning": "Allow results to load"}},
        {{"action": "take_screenshot", "reasoning": "Verify search results appeared"}}
    ],
    "adaptive_strategies": [
        "If Edge doesn't open: Try chrome.exe or iexplore.exe",
        "If search box click misses: Use Tab key to cycle to search",
        "If YouTube loads slowly: Increase wait time to 8 seconds"
    ]
}}
```

## NOW: ANALYZE THE USER REQUEST

Process the request using the agentic workflow above:
1. Deep understanding (intent, context, ambiguities)
2. Strategic planning (decomposition, selection, risk assessment)
3. Execution plan synthesis (detailed JSON with reasoning)

**Remember**: 
- Think deeply before acting
- Reason through each decision
- Plan for failures and adaptation
- Use coordinates for precision
- Verify after critical steps
- Provide rich, detailed responses

Generate your response now:"""
        
        return prompt
    
    @staticmethod
    def build_screen_analysis_prompt(question: Optional[str] = None) -> str:
        """Build an agentic prompt for deep visual analysis using chain-of-thought reasoning."""
        
        default_question = """You are an EXPERT COMPUTER VISION ANALYST with advanced spatial reasoning capabilities.

# TASK: COMPREHENSIVE SCREEN ANALYSIS

Analyze this screenshot with EXTREME PRECISION using multi-stage reasoning:

## STAGE 1: GLOBAL CONTEXT (Top-Down Analysis)

**Primary Questions**:
1. What is the MAIN application/window visible?
   - Application name and version (if visible)
   - Current state (idle, loading, active, error)
   - Window decorations and title bar text

2. What is the OVERALL LAYOUT pattern?
   - Single window, multiple windows, or complex overlay?
   - Screen regions: header, sidebar, content area, footer
   - Visual hierarchy and focus areas

3. What is the USER'S APPARENT WORKFLOW STATE?
   - Just opened the app?
   - In middle of a task?
   - Waiting for something?
   - Error or blocked state?

## STAGE 2: DETAILED ELEMENT INVENTORY (Bottom-Up Analysis)

For each UI element, provide:

**Interactive Elements**:
- Buttons: [List all visible buttons with labels and positions]
- Input fields: [Text boxes, dropdowns, checkboxes - describe each]
- Links/hyperlinks: [Clickable text and their locations]
- Menu items: [Visible menu options]
- Icons: [Toolbar icons, status icons, action icons]

**Informational Elements**:
- Text labels and descriptions
- Status indicators (progress bars, spinners, badges)
- Images and graphics
- Data displays (tables, lists, cards)

**Positional Metadata**:
For each element, estimate:
- Absolute position: (approximate x, y from top-left)
- Relative position: (top-left, center, bottom-right, etc.)
- Size: (small/medium/large)
- Visibility: (fully visible, partially obscured, highlighted)

## STAGE 3: STATE ANALYSIS (Understanding Current Situation)

**System State Indicators**:
- Loading states: [Any spinners, progress indicators, "Loading..." text]
- Error states: [Error messages, red indicators, warning icons]
- Success states: [Green checkmarks, confirmation messages]
- Focus states: [Which element has keyboard focus - indicated by outline, cursor]

**Application-Specific Context**:
- Browser: Which page/URL? Scroll position? Tabs visible?
- Text editor: Cursor position? Selected text? File name?
- Dialog: Modal or modeless? Primary action buttons?
- Desktop: Which apps running? System tray icons?

## STAGE 4: ACTIONABLE INTELLIGENCE (What Can Be Done)

**Immediate Actions Available**:
1. [Action 1]: Click on [element] at approximately (x, y)
   - Expected outcome: [describe]
   - Confidence: [high/medium/low]

2. [Action 2]: Type into [field] at approximately (x, y)
   - Current value: [if visible]
   - Suggested input: [if applicable]

3. [Action 3]: Keyboard shortcut [keys]
   - Alternative to clicking [element]

**Next Logical Steps**:
Given current state, suggest 2-3 logical next actions a user might take.

## STAGE 5: COORDINATE ESTIMATION (Precision Guidance)

For the TOP 5 most important interactive elements:

```
Element 1: [Name/Description]
  - Type: [button/link/input/icon]
  - Position: (~x, ~y) where screen is (0,0) at top-left
  - Size: ~Wpx × ~Hpx
  - Confidence: [high/medium/low]
  - Visual cues: [color, icon, text that identifies it]

Element 2: [Name/Description]
  ...
```

## STAGE 6: RISK ASSESSMENT (Potential Issues)

**Obstacles to Automation**:
- Overlapping elements that might block clicks
- Elements that appear clickable but aren't
- Dynamic content that might change position
- Modal dialogs or popups that could intercept actions

**Recommendations**:
- Best click targets (large, stable, easy to identify)
- Elements to avoid (ambiguous, too small, dynamic)
- Verification points (what to check after action)

## OUTPUT FORMAT

Provide a structured response:

```markdown
### 🎯 PRIMARY CONTEXT
[Single sentence summary]

### 🖥️ APPLICATION DETAILS
- Name: [app name]
- State: [current state]
- Title: [window title if visible]

### 📊 ELEMENT INVENTORY
#### Interactive Elements
1. [Element 1 - type, position, purpose]
2. [Element 2 - type, position, purpose]
...

#### Key Text Content
- [Important visible text]
- [Labels, headings, messages]

### 🎬 CURRENT STATE
- Focus: [which element has focus]
- Activity: [loading/idle/error/active]
- Indicators: [progress bars, status icons]

### ⚡ ACTIONABLE ITEMS
**Top Actions Available**:
1. **[Action name]**
   - Target: [element description]
   - Location: (~x, ~y)
   - Method: [click/type/keyboard]
   - Outcome: [expected result]

2. **[Action name]**
   ...

### 📍 PRECISE COORDINATES (Top 5 Elements)
```
[Element]: (est_x, est_y) - [description]
[Element]: (est_x, est_y) - [description]
...
```

### 🚨 AUTOMATION CONSIDERATIONS
- Warnings: [things to watch out for]
- Best targets: [most reliable elements]
- Verification: [how to confirm success]
```

**CRITICAL**: Be precise with coordinate estimates. Consider screen resolution context if provided. Provide confidence levels for uncertain elements."""
        
        return question or default_question
    
    @staticmethod
    def build_element_location_prompt(element_description: str) -> str:
        """Build an agentic prompt for precise element location using spatial reasoning."""
        
        return f"""You are a SPATIAL INTELLIGENCE EXPERT with pixel-perfect coordinate estimation capabilities.

# MISSION: LOCATE UI ELEMENT WITH MAXIMUM PRECISION

## TARGET ELEMENT
**Description**: "{element_description}"

## REASONING FRAMEWORK (Chain-of-Thought)

### STEP 1: VISUAL SEARCH STRATEGY
1. **Decompose Description**:
   - Primary identifier: [text, icon, color, shape]
   - Secondary features: [size, position hint, context]
   - Distinguishing characteristics: [unique attributes]

2. **Search Pattern**:
   - Start where? [top-left, center, specific region]
   - What to look for first? [text label, icon, color block]
   - Scanning order: [left-to-right, top-to-bottom, or spiral]

### STEP 2: ELEMENT IDENTIFICATION
1. **Pattern Matching**:
   - Does visible text match description?
   - Does icon/symbol match expectations?
   - Does color/styling match typical UI patterns?

2. **Context Validation**:
   - Is element in logical position for its type?
   - Are surrounding elements consistent?
   - Does it fit the application's layout pattern?

3. **Confidence Assessment**:
   - **HIGH**: Exact text match + expected position + clear visibility
   - **MEDIUM**: Partial match OR expected position OR somewhat obscured
   - **LOW**: Ambiguous match OR unexpected position OR multiple candidates

### STEP 3: COORDINATE CALCULATION

**Screen Coordinate System**:
- Origin (0, 0): Top-left corner
- X-axis: Increases rightward → Maximum = screen_width
- Y-axis: Increases downward → Maximum = screen_height

**Element Center Estimation**:
```
Given element bounds:
  - Left edge at X_left
  - Right edge at X_right
  - Top edge at Y_top
  - Bottom edge at Y_bottom

Center coordinates:
  - X_center = (X_left + X_right) / 2
  - Y_center = (Y_top + Y_bottom) / 2
```

**Precision Techniques**:
1. Identify element's bounding box visually
2. Estimate pixel coordinates of corners
3. Calculate center point
4. Apply confidence-based adjustments
5. Provide margin of error estimate

### STEP 4: POSITION DESCRIPTION

Describe location using:
- **Absolute terms**: "~X pixels from left, ~Y pixels from top"
- **Relative terms**: "upper-right quadrant, near top edge"
- **Contextual terms**: "below the menu bar, to the left of the search button"

### STEP 5: ALTERNATIVE IDENTIFIERS

If exact match uncertain, provide:
- Similar elements that could be confused with target
- Disambiguating features to confirm correct element
- Fallback identification strategies

## OUTPUT SCHEMA (JSON)

```json
{{
    "reasoning": {{
        "search_strategy": "Description of how you searched for the element",
        "identification": "How you identified and confirmed this is the correct element",
        "confidence_basis": "Why you assigned this confidence level",
        "alternatives_considered": "Other elements that were ruled out"
    }},
    
    "found": true,
    "confidence": 85,
    
    "element_type": "button|textfield|menu|icon|link|image|label|checkbox|...",
    
    "position": {{
        "x_percent": 45.5,
        "y_percent": 12.3,
        "description": "Upper-center region, below menu bar, left of toolbar"
    }},
    
    "pixel_estimate": {{
        "x": 1310,
        "y": 236,
        "margin_of_error_px": 25,
        "explanation": "Center point of element based on visible boundaries"
    }},
    
    "size": "small|medium|large|x-large",
    "dimensions_estimate": {{
        "width_px": 120,
        "height_px": 35
    }},
    
    "visual_characteristics": {{
        "visible_text": "Exact text visible on/near element",
        "icon_description": "Icon symbol or image present",
        "color": "Primary color of element",
        "styling": "Rounded corners, flat, 3D, bordered, etc."
    }},
    
    "surrounding_context": {{
        "above": "Element directly above target",
        "below": "Element directly below target",
        "left": "Element to the left",
        "right": "Element to the right"
    }},
    
    "alternative_descriptions": [
        "Other way to describe this element",
        "Alternative search terms that would find it"
    ],
    
    "interaction_guidance": {{
        "click_target": "Where exactly to click for best results",
        "hover_sensitive": false,
        "keyboard_alternative": "Keyboard shortcut if available"
    }},
    
    "risks": [
        "Dynamic element that might move",
        "Could be confused with similar element nearby",
        "Might be partially obscured at different resolutions"
    ]
}}
```

## IF ELEMENT NOT FOUND

```json
{{
    "reasoning": {{
        "search_effort": "Describe comprehensive search performed",
        "why_not_found": "Explain why element doesn't appear to be visible",
        "checked_regions": ["Regions of screen that were examined"]
    }},
    
    "found": false,
    "confidence": 0,
    
    "possible_reasons": [
        "Element might be off-screen or scrolled out of view",
        "Element might be hidden behind another window",
        "Element description might not match visible elements",
        "Element might not exist in current application state"
    ],
    
    "suggestions": [
        "Action to take to make element visible",
        "Alternative element that might achieve same goal",
        "Verification step to confirm application state"
    ],
    
    "similar_elements": [
        {{
            "description": "Element that partially matches",
            "confidence": 30,
            "why_not_exact": "Missing feature X"
        }}
    ]
}}
```

## EXAMPLES

### Example 1: High Confidence Button
```json
{{
    "reasoning": {{
        "search_strategy": "Scanned top toolbar area for buttons with text labels",
        "identification": "Found button with exact text 'Save' in expected location",
        "confidence_basis": "Perfect text match + standard toolbar position + clear visibility",
        "alternatives_considered": "Ruled out 'Save As' button (different text) and menu item (different style)"
    }},
    "found": true,
    "confidence": 95,
    "element_type": "button",
    "position": {{"x_percent": 15.2, "y_percent": 5.8}},
    "pixel_estimate": {{"x": 438, "y": 111, "margin_of_error_px": 10}},
    "visual_characteristics": {{"visible_text": "Save", "icon_description": "Floppy disk icon", "color": "Blue background"}},
    "interaction_guidance": {{"click_target": "Center of button for reliable click"}}
}}
```

### Example 2: Medium Confidence Search Box
```json
{{
    "reasoning": {{
        "search_strategy": "Looked for text input with search icon in header area",
        "identification": "Found input field with magnifying glass icon, no visible text label",
        "confidence_basis": "Visual pattern matches search box but no explicit 'Search' text",
        "alternatives_considered": "Address bar ruled out (different styling)"
    }},
    "found": true,
    "confidence": 75,
    "element_type": "textfield",
    "position": {{"x_percent": 50.0, "y_percent": 8.5}},
    "pixel_estimate": {{"x": 1440, "y": 163, "margin_of_error_px": 30}},
    "visual_characteristics": {{"icon_description": "Magnifying glass on left side", "styling": "Rounded corners, light gray border"}},
    "interaction_guidance": {{"click_target": "Center of text field, avoiding the icon"}}
}}
```

## NOW: ANALYZE THE SCREENSHOT

Using the reasoning framework above:
1. Systematically search for: "{element_description}"
2. Identify and validate the element
3. Calculate precise coordinates
4. Assess confidence level
5. Provide comprehensive JSON response

**Be ruthlessly precise with coordinates. A 50px error can mean missing the target entirely.**"""
    
    @staticmethod
    def build_verification_prompt(expected_change: str) -> str:
        """Build an agentic prompt for precise action verification with differential analysis."""
        
        return f"""You are an EXPERT VERIFICATION ANALYST specializing in detecting UI state changes with precision.

# MISSION: VERIFY ACTION OUTCOME

## CONTEXT
**Expected Change**: "{expected_change}"

You will analyze TWO screenshots:
- **BEFORE**: Screen state before action execution
- **AFTER**: Screen state after action execution

## VERIFICATION METHODOLOGY (Rigorous Analysis)

### PHASE 1: DIFFERENTIAL ANALYSIS

**Systematic Comparison**:
1. **Global Changes**:
   - New windows/dialogs appeared?
   - Existing windows closed/minimized?
   - Focus changed to different window?
   - Overall layout shift?

2. **Regional Changes**:
   - Specific UI elements appeared/disappeared?
   - Element states changed (enabled→disabled, unchecked→checked)?
   - Text content updated?
   - Colors/styling modified?

3. **Pixel-Level Changes**:
   - Cursor position moved?
   - Input field gained/lost focus (cursor blink)?
   - Progress indicators updated?
   - Subtle visual feedback (hover effects, highlights)?

### PHASE 2: EXPECTATION MATCHING

**Compare Detected Changes vs. Expected Change**:

**Scoring Criteria**:
- ✅ **Perfect Match** (100%): Observed change exactly matches expectation
- ✅ **Strong Match** (80-99%): Main change present + minor additional changes
- ⚠️ **Partial Match** (50-79%): Some expected changes present, some missing
- ⚠️ **Weak Match** (20-49%): Minimal evidence of expected change
- ❌ **No Match** (0-19%): Expected change not detected at all

**Evidence Collection**:
- List all changes that support success
- List all changes that contradict success
- Note absence of expected changes
- Identify unexpected side effects

### PHASE 3: CONFIDENCE ASSESSMENT

**Factors Increasing Confidence**:
- Multiple confirming indicators
- Clear visual evidence
- Expected behavior matches application norms
- No contradictory signals

**Factors Decreasing Confidence**:
- Ambiguous changes (could be coincidental)
- Missing expected indicators
- Unexpected state changes
- Image quality issues affecting analysis

**Confidence Levels**:
- **95-100%**: Undeniable success - multiple clear indicators
- **80-94%**: Very likely success - primary indicators present
- **60-79%**: Probable success - some supporting evidence
- **40-59%**: Uncertain - mixed or weak signals
- **20-39%**: Probably failed - missing key indicators
- **0-19%**: Clear failure - no evidence of success

### PHASE 4: ROOT CAUSE ANALYSIS (If Failed)

If expected change didn't occur:

**Why It Failed**:
1. **Timing Issues**:
   - Action too fast (UI not ready)?
   - Not enough wait time for response?
   - Animation/transition still in progress?

2. **Targeting Issues**:
   - Wrong element clicked?
   - Click coordinates missed target?
   - Element was disabled/inactive?

3. **State Issues**:
   - Application in wrong state for action?
   - Modal dialog blocking?
   - Focus on wrong window?

4. **External Factors**:
   - Network latency (for web apps)?
   - System resources slow?
   - Permission denied?

**Corrective Recommendations**:
- What should be tried next?
- How to adjust the approach?
- Alternative action sequence?

## OUTPUT SCHEMA (JSON)

```json
{{
    "reasoning": {{
        "differential_analysis": "Detailed description of all changes detected between BEFORE and AFTER",
        "expectation_comparison": "How detected changes align with expected change",
        "confidence_justification": "Why this confidence level was assigned",
        "failure_hypothesis": "If failed, most likely reason why (null if succeeded)"
    }},
    
    "success": true,
    "confidence": 88,
    
    "changes_detected": [
        {{
            "type": "window_focus|element_state|text_content|visual_feedback|layout|other",
            "description": "Specific change observed",
            "region": "Where on screen (coordinates or description)",
            "supports_success": true,
            "importance": "critical|high|medium|low"
        }}
    ],
    
    "expected_vs_actual": {{
        "expected": "{expected_change}",
        "actual": "What actually happened",
        "match_percentage": 85,
        "discrepancies": [
            "Expected X but saw Y",
            "Missing expected indicator Z"
        ]
    }},
    
    "success_indicators": [
        "✓ Search results page loaded",
        "✓ Query visible in search box",
        "✓ Page title changed to reflect search"
    ],
    
    "failure_indicators": [
        "✗ No video thumbnails visible (expected on results page)",
        "✗ URL did not change to search results URL"
    ],
    
    "recommendations": {{
        "if_retry": "Suggestion if retrying this action",
        "alternative_approach": "Different way to achieve same goal",
        "next_step": "What should happen next in the workflow"
    }},
    
    "temporal_notes": {{
        "appears_in_progress": false,
        "likely_needs_more_wait": false,
        "animation_detected": false
    }},
    
    "visual_evidence": {{
        "screenshot_quality": "clear|somewhat_blurry|very_blurry",
        "occlusions": ["Elements blocking view of critical areas"],
        "analysis_limitations": ["Factors that reduced analysis confidence"]
    }}
}}
```

## EXAMPLES

### Example 1: Clear Success
**Expected**: "Text 'hello world' appears in notepad"
**Analysis**: BEFORE shows empty notepad, AFTER shows "hello world" text

```json
{{
    "reasoning": {{
        "differential_analysis": "BEFORE: Empty white canvas with blinking cursor at top-left. AFTER: Text 'hello world' visible in top-left, cursor after 'd'",
        "expectation_comparison": "Perfect match - exact expected text appears exactly where typed text should be",
        "confidence_justification": "Text is clearly visible, matches exactly, appropriate cursor position",
        "failure_hypothesis": null
    }},
    "success": true,
    "confidence": 98,
    "changes_detected": [
        {{"type": "text_content", "description": "Text 'hello world' now visible", "supports_success": true, "importance": "critical"}},
        {{"type": "element_state", "description": "Cursor moved from position 0 to position 11", "supports_success": true, "importance": "high"}}
    ],
    "expected_vs_actual": {{
        "match_percentage": 100,
        "discrepancies": []
    }},
    "success_indicators": ["✓ Text 'hello world' clearly visible", "✓ Cursor positioned after text"],
    "failure_indicators": [],
    "recommendations": {{"next_step": "Proceed with next action in workflow"}}
}}
```

### Example 2: Clear Failure
**Expected**: "Video player opens and starts playing"
**Analysis**: Both screenshots show YouTube search results page, no video player

```json
{{
    "reasoning": {{
        "differential_analysis": "BEFORE: YouTube search results page with video thumbnails. AFTER: Same page, no significant changes detected",
        "expectation_comparison": "Complete mismatch - expected video player interface but still on search results",
        "confidence_justification": "No evidence of video player, page state unchanged",
        "failure_hypothesis": "Most likely: Video thumbnail was not clicked, or click missed target"
    }},
    "success": false,
    "confidence": 2,
    "changes_detected": [],
    "expected_vs_actual": {{
        "expected": "Video player interface with playback controls",
        "actual": "Still on search results page",
        "match_percentage": 0,
        "discrepancies": ["No video player visible", "URL unchanged", "Page layout identical"]
    }},
    "success_indicators": [],
    "failure_indicators": [
        "✗ No video player interface",
        "✗ Still showing search results grid",
        "✗ URL still /results, not /watch"
    ],
    "recommendations": {{
        "if_retry": "Take screenshot to identify video thumbnail coordinates, ensure accurate click on center of thumbnail",
        "alternative_approach": "Use keyboard navigation: Tab to video thumbnail, then Enter",
        "next_step": "Retry click with verified coordinates"
    }},
    "temporal_notes": {{"appears_in_progress": false, "likely_needs_more_wait": false}}
}}
```

### Example 3: Partial Success (Uncertain)
**Expected**: "Browser navigates to YouTube homepage"
**Analysis**: Page loading, partially rendered

```json
{{
    "reasoning": {{
        "differential_analysis": "BEFORE: Blank browser with address bar. AFTER: Page partially loaded, YouTube logo visible but content area still loading",
        "expectation_comparison": "Partial match - navigation initiated and YouTube domain confirmed, but page not fully loaded",
        "confidence_justification": "Strong indicators of success but incomplete - likely needs more time",
        "failure_hypothesis": null
    }},
    "success": true,
    "confidence": 72,
    "changes_detected": [
        {{"type": "layout", "description": "YouTube header with logo now visible", "supports_success": true, "importance": "high"}},
        {{"type": "visual_feedback", "description": "Loading spinner in content area", "supports_success": true, "importance": "medium"}}
    ],
    "expected_vs_actual": {{
        "expected": "Fully loaded YouTube homepage",
        "actual": "YouTube homepage loading in progress",
        "match_percentage": 70,
        "discrepancies": ["Content area not fully rendered", "Recommended videos not visible yet"]
    }},
    "success_indicators": ["✓ YouTube logo and header present", "✓ URL shows youtube.com", "✓ Loading indicator active"],
    "failure_indicators": ["✗ Content not fully loaded"],
    "recommendations": {{"next_step": "Wait additional 2-3 seconds for page to fully load"}},
    "temporal_notes": {{"appears_in_progress": true, "likely_needs_more_wait": true, "animation_detected": true}}
}}
```

## NOW: PERFORM VERIFICATION

Analyze the BEFORE and AFTER screenshots:
1. Identify all differences systematically
2. Match changes against expected outcome
3. Assess confidence rigorously
4. Provide detailed reasoning
5. Generate comprehensive JSON response

**Critical**: Be harsh in your assessment. Optimism leads to cascading failures. Only mark as success if evidence is CLEAR."""
    
    @staticmethod
    def build_next_action_prompt(current_state: str, goal: str, history: list) -> str:
        """Build an agentic prompt for intelligent next-action selection with adaptive reasoning."""
        
        history_str = "\n".join([f"{i+1}. {a}" for i, a in enumerate(history[-5:])]) if history else "None"
        
        return f"""You are an ADAPTIVE PLANNING AGENT with real-time decision-making capabilities.

# SITUATION BRIEFING

## OBJECTIVE
**Goal**: {goal}

## CURRENT STATE
**Observed State**: {current_state}

## EXECUTION HISTORY (Last 5 Actions)
{history_str}

---

# ADAPTIVE DECISION FRAMEWORK

## PHASE 1: SITUATION ASSESSMENT

**Context Analysis**:
1. **Progress Evaluation**:
   - How far are we toward the goal? (0-100%)
   - What has been accomplished so far?
   - What remains to be done?

2. **State Understanding**:
   - What is the current system/application state?
   - Are we on the expected path?
   - Any unexpected deviations?

3. **History Pattern Recognition**:
   - Are actions succeeding or failing?
   - Is there a pattern in failures?
   - Are we making forward progress or stuck?

## PHASE 2: STRATEGY FORMULATION

**Decision Tree**:

```
IF goal already achieved:
    → Verify success, then STOP
ELSE IF significant progress made:
    → Continue with next logical step
ELSE IF stuck/failing repeatedly:
    → Change approach entirely
ELSE IF minor obstacle:
    → Try alternative action for same goal
ELSE IF unclear state:
    → Take screenshot to assess situation
```

**Action Selection Principles**:
1. **Directness**: Prefer actions that directly advance toward goal
2. **Reliability**: Choose proven actions over experimental ones
3. **Efficiency**: Minimize steps while maintaining reliability
4. **Adaptability**: Be ready to pivot based on feedback
5. **Verification**: Include checks after critical steps

## PHASE 3: ACTION REASONING

For the selected action, explain:
- **Why this action**: How it moves us toward goal
- **Why not alternatives**: Considered options and why rejected
- **Expected outcome**: What should happen after execution
- **Success criteria**: How to verify it worked
- **Failure handling**: What to do if it doesn't work

## AVAILABLE ACTIONS

{action_registry.to_prompt_string()}

---

## OUTPUT SCHEMA (JSON)

```json
{{
    "reasoning": {{
        "situation_summary": "Brief assessment of where we are now",
        "progress_estimate": 45,
        "analysis": "Detailed analysis of current state and history",
        "strategy": "High-level approach for next action",
        "alternatives_considered": [
            {{
                "action": "alternative_action_1",
                "pros": ["Advantage 1", "Advantage 2"],
                "cons": ["Disadvantage 1", "Disadvantage 2"],
                "why_not_chosen": "Specific reason for rejection"
            }}
        ],
        "decision_rationale": "Why the selected action is the best choice"
    }},
    
    "action": "selected_action_name",
    "target": "specific_target_description",
    "parameters": {{
        "key": "value"
    }},
    
    "expected_outcome": "What should happen after this action executes",
    
    "verification": {{
        "method": "How to check if action succeeded",
        "success_indicators": ["What to look for"],
        "failure_indicators": ["What would indicate failure"]
    }},
    
    "fallback_plan": {{
        "if_fails": "What to try if this action fails",
        "max_retries": 2,
        "alternative_sequence": ["action_1", "action_2", "action_3"]
    }},
    
    "confidence": 82,
    
    "estimated_remaining_steps": 3,
    
    "adaptive_notes": [
        "Observation or insight about current situation",
        "Pattern noticed in execution history",
        "Risk to be aware of"
    ]
}}
```

## DECISION EXAMPLES

### Example 1: Clear Path Forward
**Goal**: "Open calculator"
**Current State**: "{{'active_window': 'Desktop'}}"
**History**: None

```json
{{
    "reasoning": {{
        "situation_summary": "Starting from clean slate, no actions taken yet",
        "progress_estimate": 0,
        "analysis": "Need to launch calculator application. Desktop is active, which is expected starting point.",
        "strategy": "Use Win+R run dialog for reliable app launching",
        "alternatives_considered": [
            {{
                "action": "open_application",
                "pros": ["Direct approach"],
                "cons": ["May not work if executable path unclear"],
                "why_not_chosen": "Win+R is more reliable across Windows versions"
            }}
        ],
        "decision_rationale": "Win+R is fastest and most reliable way to launch apps in Windows"
    }},
    "action": "hotkey",
    "target": "win+r",
    "parameters": {{}},
    "expected_outcome": "Run dialog opens in bottom-left corner",
    "verification": {{
        "method": "Check if small dialog with text input appeared",
        "success_indicators": ["Run dialog visible", "Text field has focus"],
        "failure_indicators": ["No dialog appeared", "Different window opened"]
    }},
    "confidence": 95,
    "estimated_remaining_steps": 2
}}
```

### Example 2: Stuck Situation - Adaptive Response
**Goal**: "Click submit button"
**Current State**: "{{'step_error': 'Click at (800, 500) failed - element not found'}}"
**History**: ["click at (800,500) → ✗", "click at (800,500) → ✗", "click at (800,500) → ✗"]

```json
{{
    "reasoning": {{
        "situation_summary": "Stuck - same click action failing repeatedly",
        "progress_estimate": 0,
        "analysis": "Three consecutive failures at same coordinates suggests: 1) Coordinates are wrong, 2) Element moved, 3) Element doesn't exist. Need to reassess visually.",
        "strategy": "STOP repeating failed action. Take screenshot to identify actual button position.",
        "alternatives_considered": [
            {{
                "action": "click",
                "why_not_chosen": "Already failed 3 times, definition of insanity"
            }},
            {{
                "action": "hotkey",
                "pros": ["Might trigger submission via Enter"],
                "cons": ["Assumes button is default action"],
                "why_not_chosen": "Need to confirm button exists first"
            }}
        ],
        "decision_rationale": "Must get fresh visual information to identify correct target before attempting more clicks"
    }},
    "action": "take_screenshot",
    "target": "current_state",
    "parameters": {{}},
    "expected_outcome": "Capture current screen to identify submit button location",
    "verification": {{"method": "Screenshot file created successfully"}},
    "fallback_plan": {{
        "if_fails": "Try keyboard shortcut Enter as last resort",
        "alternative_sequence": ["press_key enter", "hotkey ctrl+s"]
    }},
    "confidence": 75,
    "estimated_remaining_steps": 4,
    "adaptive_notes": [
        "Pattern detected: Repeated failure at same coordinates",
        "Strategy shift: From blind clicking to visual identification",
        "Risk: Button might not exist - may need to change entire approach"
    ]
}}
```

### Example 3: Near Goal - Final Push
**Goal**: "Search for python tutorials on YouTube"
**Current State**: "{{'active_window': 'YouTube - Search Results'}}"
**History**: ["open msedge → ✅", "navigate to youtube.com → ✅", "click search box → ✅", "type 'python tutorials' → ✅", "press enter → ✅"]

```json
{{
    "reasoning": {{
        "situation_summary": "Goal nearly achieved - search completed successfully",
        "progress_estimate": 95,
        "analysis": "All steps executed successfully. Search query submitted and results page loaded. Goal is essentially complete.",
        "strategy": "Verify success and conclude task",
        "decision_rationale": "Task is complete - search results for 'python tutorials' are displayed"
    }},
    "action": "wait",
    "target": "final_verification",
    "parameters": {{"seconds": 1}},
    "expected_outcome": "Allow page to fully stabilize for verification",
    "verification": {{
        "method": "Check that search results page is stable and videos are visible",
        "success_indicators": ["Video thumbnails visible", "Search query in search box", "Results count shown"],
        "failure_indicators": ["Still loading", "Error message", "Blank page"]
    }},
    "confidence": 98,
    "estimated_remaining_steps": 0,
    "adaptive_notes": ["Task completed successfully through all planned steps"]
}}
```

---

## NOW: MAKE YOUR DECISION

Analyze the situation using the framework above:
1. Assess progress and current state
2. Review execution history for patterns
3. Formulate strategy (continue, adapt, or pivot)
4. Select best next action with full reasoning
5. Provide comprehensive JSON response

**Remember**: 
- Don't repeat failing actions blindly
- Take screenshots when uncertain
- Adapt strategy based on feedback
- Provide rich reasoning for decisions
- Include fallback plans for failures

Generate your decision now:"""


class PromptOptimizer:
    """Optimizes prompts for better performance."""
    
    @staticmethod
    def compress_context(context: Dict[str, Any], max_items: int = 10) -> Dict[str, Any]:
        """Compress context to essential information."""
        compressed = context.copy()
        
        if 'running_processes' in compressed:
            compressed['running_processes'] = compressed['running_processes'][:max_items]
        
        return compressed
    
    @staticmethod
    def add_few_shot_examples(prompt: str, examples: list) -> str:
        """Add few-shot learning examples to prompt."""
        if not examples:
            return prompt
        
        examples_section = "\n\nEXAMPLES:\n\n"
        for i, example in enumerate(examples, 1):
            examples_section += f"Example {i}:\n"
            examples_section += f"Request: {example['request']}\n"
            examples_section += f"Response: {example['response']}\n\n"
        
        return prompt + examples_section


# Global prompt builder instance
prompt_builder = PromptBuilder()
