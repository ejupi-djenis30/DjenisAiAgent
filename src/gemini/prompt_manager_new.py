import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

class PromptTemplate:
    """
    A template for generating prompts with placeholders for dynamic content.
    """
    def __init__(self, template_text: str, name: str = "unnamed_template"):
        """
        Initialize a prompt template.
        
        Args:
            template_text: The template text with {placeholders}
            name: Name of the template for reference
        """
        self.template_text = template_text
        self.name = name
        
    def format(self, **kwargs) -> str:
        """
        Format the template with provided variables.
        
        Args:
            **kwargs: Key-value pairs to fill in the template placeholders
            
        Returns:
            Formatted prompt text
        """
        try:
            return self.template_text.format(**kwargs)
        except KeyError as e:
            print(f"Warning: Missing key {e} in template {self.name}")
            # Return partial formatting with missing keys marked
            return self.template_text.format(**{
                **kwargs,
                **{str(e)[1:-1]: f"[MISSING_{str(e)[1:-1]}]" for e in [e]}
            })

class PromptManager:
    """
    Manages prompt templates and prompt history for the Gemini AI.
    """
    def __init__(self, templates_path: Optional[str] = None):
        """
        Initialize the prompt manager.
        
        Args:
            templates_path: Optional path to JSON file containing prompt templates
        """
        self.templates: Dict[str, PromptTemplate] = {}
        self.prompt_history: List[Dict[str, Any]] = []
        self.max_history_size = 100
        
        # Add default templates
        self._add_default_templates()
        
        # Load additional templates if provided
        if templates_path and os.path.exists(templates_path):
            self.load_templates(templates_path)
    
    def _add_default_templates(self):
        """Add default templates for common scenarios."""
        
        # Base template for analyzing the screen
        self.add_template(
            name="screen_analysis",
            template="""
You are an AI assistant that controls a Windows 11 computer by seeing the screen and executing actions.

Current context:
- Current application: {current_app}
- Recent actions: {recent_actions}

I'm showing you a screenshot of the current state of the screen.

Detailed analysis of the screenshot:
{screen_analysis_details}

Your task:
1. Describe what you see on the screen
2. Identify UI elements (buttons, text fields, menus, etc.)
3. Suggest possible actions based on the user's request: "{user_request}"

Important: Format actions using [ACTION: action_type param1=value1, param2=value2] syntax.
Available actions: click, type_text, key_press, scroll, wait

Provide your reasoning and then suggest specific actions to take.
"""
        )
        
        # Template for error handling
        self.add_template(
            name="error_handling",
            template="""
You are an AI assistant helping to control a Windows 11 computer.

An error has occurred: {error_message}

Current context:
- Current application: {current_app}
- Action that caused error: {failed_action}

I'm showing you a screenshot of the current error state.

Detailed analysis of the error screen:
{screen_analysis_details}

Your task:
1. Analyze the error shown on screen
2. Explain what might have gone wrong
3. Suggest how to recover from this error

Important: Format actions using [ACTION: action_type param1=value1, param2=value2] syntax.
Available actions: click, type_text, key_press, escape, wait

Provide your reasoning and then suggest specific actions to take.
"""
        )
        
        # Template for navigation tasks
        self.add_template(
            name="navigation",
            template="""
You are an AI assistant controlling a Windows 11 computer.

User wants to: {user_request}

Current context:
- Current location: {current_app}
- Target destination: {target_destination}

I'm showing you a screenshot of the current screen.

Detailed analysis of the screen:
{screen_analysis_details}

Your task:
1. Determine where we are in the navigation process
2. Identify the next step to get closer to the target destination
3. Suggest specific UI elements to interact with

Important: Format actions using [ACTION: action_type param1=value1, param2=value2] syntax.
Available actions: click, type_text, key_press, scroll, wait

Provide your reasoning and then suggest one or more actions to take.
"""
        )
        
        # Template for form filling
        self.add_template(
            name="form_filling",
            template="""
You are an AI assistant controlling a Windows 11 computer.

User wants to fill out a form with the following information:
{form_data}

Current context:
- Current application: {current_app}
- Form name: {form_name}
- Progress: {form_progress}

I'm showing you a screenshot of the current form state.

Detailed analysis of the form elements:
{screen_analysis_details}

Your task:
1. Identify the form fields visible on screen
2. Match them with the information that needs to be filled
3. Suggest specific actions to fill in the appropriate fields
4. Identify the submit/next button when the form is complete

Important: Format actions using [ACTION: action_type param1=value1, param2=value2] syntax.
Available actions: click, type_text, key_press, tab, wait

Provide your reasoning and then suggest specific actions to take.
"""
        )
        
        # Template for pattern recognition
        self.add_template(
            name="pattern_recognition",
            template="""
You are an AI assistant controlling a Windows 11 computer.

User wants to: {user_request}

Current context:
- Current application: {current_app}
- Recent actions: {recent_actions}

I'm showing you a screenshot of the current screen.

Detailed analysis of UI elements with recognized patterns:
{recognized_patterns_details}

Screen hierarchy information:
{window_hierarchy_details}

Your task:
1. Identify familiar UI patterns from the screen (e.g., standard buttons, menus, dialogs)
2. Use pattern recognition to suggest the most efficient way to accomplish the user's request
3. Suggest specific actions based on recognized patterns

Important: Format actions using [ACTION: action_type param1=value1, param2=value2] syntax.
Available actions: click, type_text, key_press, scroll, wait

Provide your reasoning and then suggest specific actions to take.
"""
        )
    
    def add_template(self, name: str, template: str):
        """
        Add a new prompt template.
        
        Args:
            name: Name of the template
            template: Template text with {placeholders}
        """
        self.templates[name] = PromptTemplate(template, name)
        
    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """
        Get a template by name.
        
        Args:
            name: Name of the template
            
        Returns:
            PromptTemplate object or None if not found
        """
        return self.templates.get(name)
        
    def format_prompt(self, template_name: str, **kwargs) -> str:
        """
        Format a prompt using a named template.
        
        Args:
            template_name: Name of the template
            **kwargs: Variables to fill in the template
            
        Returns:
            Formatted prompt text
        """
        template = self.get_template(template_name)
        if not template:
            raise ValueError(f"Template '{template_name}' not found")
            
        prompt_text = template.format(**kwargs)
        
        # Record prompt in history
        self._add_to_history(template_name, kwargs, prompt_text)
        
        return prompt_text
    
    def _add_to_history(self, template_name: str, variables: Dict[str, Any], result: str):
        """Add a prompt to the history."""
        self.prompt_history.append({
            "timestamp": datetime.now().isoformat(),
            "template": template_name,
            "variables": variables,
            "result": result
        })
        
        # Trim history if it gets too long
        if len(self.prompt_history) > self.max_history_size:
            self.prompt_history = self.prompt_history[-self.max_history_size:]
    
    def load_templates(self, file_path: str):
        """
        Load templates from a JSON file.
        
        Args:
            file_path: Path to the JSON file containing templates
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                templates_dict = json.load(f)
                
            for name, template_text in templates_dict.items():
                self.add_template(name, template_text)
                
        except Exception as e:
            print(f"Error loading templates from {file_path}: {str(e)}")
    
    def save_templates(self, file_path: str):
        """
        Save current templates to a JSON file.
        
        Args:
            file_path: Path to save the templates
        """
        try:
            templates_dict = {name: template.template_text 
                             for name, template in self.templates.items()}
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(templates_dict, f, indent=2)
                
        except Exception as e:
            print(f"Error saving templates to {file_path}: {str(e)}")
    
    def get_formatted_history(self, limit: int = 5) -> str:
        """
        Get a formatted string of recent prompt history.
        
        Args:
            limit: Maximum number of history items to include
            
        Returns:
            Formatted history text
        """
        recent_history = self.prompt_history[-limit:] if self.prompt_history else []
        
        if not recent_history:
            return "No prompt history available."
            
        history_text = "Recent prompt history:\n\n"
        
        for idx, item in enumerate(recent_history):
            timestamp = datetime.fromisoformat(item["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            history_text += f"[{idx+1}] {timestamp} - Template: {item['template']}\n"
            
            # Add truncated result
            result = item["result"]
            if len(result) > 100:
                result = result[:100] + "..."
            history_text += f"Result: {result}\n\n"
            
        return history_text
    
    def generate_structured_prompt(self, 
                                 template_name: str, 
                                 user_request: str,
                                 screenshot_path: Optional[str] = None,
                                 context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate a structured prompt for the Gemini API.
        
        Args:
            template_name: Name of the template to use
            user_request: The user's request
            screenshot_path: Optional path to a screenshot image
            context: Additional context variables
            
        Returns:
            Structured prompt dictionary for Gemini API
        """
        if context is None:
            context = {}
            
        # Common context variables
        common_context = {
            "user_request": user_request,
            "current_app": context.get("current_app", "Unknown"),
            "recent_actions": context.get("recent_actions", "None"),
            "screen_analysis_details": context.get("screen_analysis_details", "No detailed analysis available"),
            "recognized_patterns_details": context.get("recognized_patterns", "No patterns recognized"),
            "window_hierarchy_details": context.get("window_hierarchy", "No hierarchy information available")
        }
        
        # Merge with template-specific context
        template_context = {**common_context, **context}
        
        # Format the prompt text
        prompt_text = self.format_prompt(template_name, **template_context)
        
        # Create the structured prompt
        structured_prompt = {
            "text": prompt_text
        }
        
        # Add screenshot if provided
        if screenshot_path and os.path.exists(screenshot_path):
            structured_prompt["image"] = screenshot_path
            
        return structured_prompt
