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
            The template or None if not found
        """
        return self.templates.get(name)
    
    def format_prompt(self, 
                     template_name: str, 
                     context: Dict[str, Any] = None, 
                     **kwargs) -> str:
        """
        Format a prompt using a template and additional variables.
        
        Args:
            template_name: Name of the template to use
            context: Additional context to include in the prompt
            **kwargs: Variables to fill in the template
            
        Returns:
            Formatted prompt text
        """
        template = self.get_template(template_name)
        if not template:
            raise ValueError(f"Template '{template_name}' not found")
            
        # Combine context with kwargs
        variables = kwargs
        if context:
            variables.update(context)
            
        # Format the template with variables
        formatted_prompt = template.format(**variables)
        
        # Add to history
        self._add_to_history(template_name, variables, formatted_prompt)
        
        return formatted_prompt
    
    def create_custom_prompt(self, 
                            base_text: str, 
                            context: Dict[str, Any] = None, 
                            **kwargs) -> str:
        """
        Create a custom prompt without using a template.
        
        Args:
            base_text: The base text for the prompt
            context: Additional context to include
            **kwargs: Additional variables to include
            
        Returns:
            Formatted prompt text
        """
        prompt_parts = [base_text]
        
        # Add context if provided
        if context:
            prompt_parts.append("\nContext:")
            for key, value in context.items():
                prompt_parts.append(f"- {key}: {value}")
        
        # Add additional variables
        for key, value in kwargs.items():
            if isinstance(value, str):
                prompt_parts.append(f"\n{key.replace('_', ' ').title()}: {value}")
        
        formatted_prompt = "\n".join(prompt_parts)
        
        # Add to history
        self._add_to_history("custom_prompt", {**kwargs, **(context or {})}, formatted_prompt)
        
        return formatted_prompt
    
    def _add_to_history(self, template_name: str, variables: Dict[str, Any], formatted_prompt: str):
        """
        Add a prompt to the history.
        
        Args:
            template_name: Name of the template used
            variables: Variables used in the template
            formatted_prompt: The final formatted prompt
        """
        self.prompt_history.append({
            "template": template_name,
            "variables": {k: str(v) for k, v in variables.items()},
            "prompt": formatted_prompt,
            "timestamp": datetime.now().isoformat()
        })
        
        # Trim history if too large
        if len(self.prompt_history) > self.max_history_size:
            self.prompt_history = self.prompt_history[-self.max_history_size:]
    
    def load_templates(self, templates_path: str):
        """
        Load templates from a JSON file.
        
        Args:
            templates_path: Path to the JSON file with templates
        """
        try:
            with open(templates_path, 'r') as file:
                templates_data = json.load(file)
                
            for name, template_text in templates_data.items():
                self.add_template(name, template_text)
                
        except Exception as e:
            print(f"Error loading templates: {str(e)}")
    
    def save_templates(self, templates_path: str):
        """
        Save current templates to a JSON file.
        
        Args:
            templates_path: Path where to save templates
        """
        try:
            templates_data = {name: template.template_text for name, template in self.templates.items()}
            
            with open(templates_path, 'w') as file:
                json.dump(templates_data, file, indent=2)
                
        except Exception as e:
            print(f"Error saving templates: {str(e)}")
    
    def get_recent_prompts(self, count: int = 5) -> List[Dict[str, Any]]:
        """
        Get the most recent prompts from history.
        
        Args:
            count: Number of recent prompts to return
            
        Returns:
            List of recent prompts
        """
        return self.prompt_history[-count:]
    
    def clear_history(self):
        """Clear the prompt history."""
        self.prompt_history.clear()