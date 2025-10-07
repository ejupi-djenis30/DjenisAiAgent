"""
Advanced Prompt Engineering for Gemini API.
"""

from typing import Dict, Any, Optional
from src.core.actions import action_registry


class PromptBuilder:
    """Builds optimized prompts for Gemini API."""
    
    @staticmethod
    def build_task_planning_prompt(user_request: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Build a comprehensive task planning prompt."""
        
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
        
        prompt = f"""You are an advanced AI assistant specialized in Windows PC automation through UI control.
Your role is to analyze user requests and create precise, executable action plans.

{context_section}

{actions_section}

USER REQUEST: "{user_request}"

INSTRUCTIONS:
1. Analyze the user's request carefully
2. Break it down into atomic, executable steps
3. Use ONLY the actions listed above
4. Be specific about targets (window names, button text, etc.)
5. Include verification steps where appropriate
6. Consider edge cases and provide fallback strategies

RESPONSE FORMAT:
Return a JSON object with this EXACT structure:

{{
    "understood": true/false,
    "confidence": 0-100,
    "task_summary": "Brief description of what will be done",
    "complexity": "simple/moderate/complex",
    "estimated_duration": "estimated seconds",
    "prerequisites": ["list any requirements"],
    "steps": [
        {{
            "step_number": 1,
            "action": "action_name from the list above",
            "target": "specific target (app name, element description, text, etc.)",
            "parameters": {{
                "key": "value"
            }},
            "expected_result": "what should happen",
            "verification": "how to verify success",
            "fallback": "what to do if it fails",
            "estimated_time": "seconds"
        }}
    ],
    "success_criteria": "how to know the entire task succeeded",
    "potential_issues": ["list of things that could go wrong"],
    "clarification_needed": null or "question if request is unclear"
}}

IMPORTANT RULES:
- Use action names EXACTLY as listed (e.g., "open_application", "type_text", "click")
- For opening apps, use executable names (notepad.exe, calc.exe, msedge.exe, chrome.exe)
- For typing text, put the actual text in parameters: {{"text": "hello world"}}
- For hotkeys, use format like "ctrl+c" in the target field
- Be specific about what to click on (button names, coordinates if known)
- Include wait steps between actions when needed
- Always verify critical actions

EXAMPLES:

Good step example:
{{
    "step_number": 1,
    "action": "open_application",
    "target": "notepad.exe",
    "parameters": {{}},
    "expected_result": "Notepad window opens",
    "verification": "Check if Notepad window is visible",
    "fallback": "Try using Windows search if direct launch fails",
    "estimated_time": "2"
}}

Good typing example:
{{
    "step_number": 2,
    "action": "type_text",
    "target": "active window",
    "parameters": {{"text": "Hello World"}},
    "expected_result": "Text appears in active window",
    "verification": "Text is visible on screen",
    "fallback": "Ensure window has focus first",
    "estimated_time": "1"
}}

Now analyze the user request and provide your response:"""
        
        return prompt
    
    @staticmethod
    def build_screen_analysis_prompt(question: Optional[str] = None) -> str:
        """Build a prompt for screen analysis."""
        
        default_question = """Analyze this screenshot in detail:

1. MAIN APPLICATION/WINDOW:
   - What application or window is displayed?
   - What is its current state?

2. UI ELEMENTS:
   - List all visible buttons, menus, text fields
   - Note their approximate positions (top-left, center, etc.)
   - Identify any highlighted or focused elements

3. TEXT CONTENT:
   - Any visible text or labels
   - Input fields and their content
   - Menu items or options

4. CURRENT STATE:
   - Is the application idle, loading, or showing an error?
   - Any modal dialogs or popups?
   - Any indicators of activity?

5. ACTIONABLE INFORMATION:
   - What actions could be performed right now?
   - What elements can be clicked or interacted with?

Provide a concise, structured response focused on information useful for automation."""
        
        return question or default_question
    
    @staticmethod
    def build_element_location_prompt(element_description: str) -> str:
        """Build a prompt for finding element locations."""
        
        return f"""Analyze this screenshot to locate: "{element_description}"

TASK: Find the UI element that matches the description.

RESPONSE FORMAT (JSON):
{{
    "found": true/false,
    "confidence": 0-100,
    "element_type": "button/textfield/menu/icon/etc",
    "position": {{
        "x_percent": 0-100,
        "y_percent": 0-100,
        "description": "where it is (e.g., top-left corner, center-right)"
    }},
    "size": "small/medium/large",
    "visible_text": "any text visible on the element",
    "surrounding_context": "what's around it",
    "alternative_descriptions": ["other ways to identify it"]
}}

ANALYSIS APPROACH:
1. Scan the entire image systematically
2. Look for text matching the description
3. Identify UI elements by shape and context
4. Consider common UI patterns (buttons look like buttons, etc.)
5. Estimate position as percentage from top-left (0,0) to bottom-right (100,100)

Be precise and confident. If the element isn't visible, set found=false."""
    
    @staticmethod
    def build_verification_prompt(expected_change: str) -> str:
        """Build a prompt for verifying actions."""
        
        return f"""Compare these two screenshots (BEFORE and AFTER an action).

EXPECTED CHANGE: "{expected_change}"

RESPONSE FORMAT (JSON):
{{
    "success": true/false,
    "confidence": 0-100,
    "changes_detected": [
        "list of actual changes observed"
    ],
    "expected_vs_actual": "comparison",
    "reasoning": "detailed explanation",
    "recommendations": "what to do next"
}}

ANALYSIS:
1. Identify all differences between the images
2. Compare with the expected change
3. Determine if the action achieved its goal
4. Consider partial success scenarios

Be thorough but concise."""
    
    @staticmethod
    def build_next_action_prompt(current_state: str, goal: str, history: list) -> str:
        """Build a prompt for determining next action."""
        
        history_str = "\n".join([f"{i+1}. {a}" for i, a in enumerate(history[-5:])]) if history else "None"
        
        return f"""AUTOMATION CONTEXT:

GOAL: {goal}
CURRENT STATE: {current_state}

RECENT ACTIONS:
{history_str}

TASK: Determine the next best action to move toward the goal.

{action_registry.to_prompt_string()}

RESPONSE FORMAT (JSON):
{{
    "action": "action_name",
    "target": "specific target",
    "parameters": {{}},
    "reasoning": "why this action",
    "alternatives": ["other options if this fails"],
    "confidence": 0-100
}}

Consider:
- What has already been done
- What still needs to be done
- The current state of the system
- Potential obstacles

Choose the most logical next step."""


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
