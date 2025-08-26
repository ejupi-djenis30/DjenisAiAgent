import os
import time
import json
import base64
import requests
from typing import Dict, Any, List, Optional, Union
import io

try:
    import google.generativeai as genai
    from PIL import Image
except ImportError:
    print("Warning: Gemini libraries not installed. Please install: google-generativeai, pillow")

class GeminiClient:
    """
    Client for interacting with Google's Gemini API.
    Provides methods to send prompts and images to the Gemini model and process responses.
    """
    def __init__(self, api_key: str, model_name: str = "gemini-pro-vision"):
        """
        Initialize the Gemini client.
        
        Args:
            api_key: The API key for accessing Gemini API
            model_name: The name of the Gemini model to use
        """
        self.api_key = api_key
        self.model_name = model_name
        self.history = []
        self.retry_attempts = 3
        self.retry_delay = 2  # seconds
        
        # Configure the Gemini API client
        try:
            genai.configure(api_key=api_key)
            
            # Set up the model
            self.model = genai.GenerativeModel(model_name)
            
            # Set up a conversation for maintaining context
            self.chat = self.model.start_chat(history=[])
            
            self.initialized = True
        except Exception as e:
            print(f"Error initializing Gemini client: {str(e)}")
            self.initialized = False

    def send_request(self, 
                    prompt: str, 
                    images: Optional[List[Union[str, Image.Image]]] = None, 
                    temperature: float = 0.7,
                    max_tokens: int = 1024) -> Dict[str, Any]:
        """
        Sends a request to the Gemini service.
        
        Args:
            prompt: Text prompt to send to Gemini
            images: Optional list of images (as file paths or PIL Images)
            temperature: Controls randomness in responses (0.0 to 1.0)
            max_tokens: Maximum number of tokens to generate
            
        Returns:
            Dictionary containing the response and metadata
        """
        if not self.initialized:
            return {"error": "Gemini client not properly initialized"}
            
        try:
            # Prepare images if provided
            content_parts = [prompt]
            
            if images:
                for img in images:
                    if isinstance(img, str):
                        # It's a file path
                        if os.path.exists(img):
                            image = Image.open(img)
                            content_parts.append(image)
                    elif isinstance(img, Image.Image):
                        # It's already a PIL Image
                        content_parts.append(img)
            
            # Generation config
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "top_p": 0.95,
                "top_k": 64
            }
            
            # Safety settings
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
            
            # Send request and get response with retries
            for attempt in range(self.retry_attempts):
                try:
                    # Add the prompt to the chat
                    response = self.chat.send_message(
                        content=content_parts,
                        generation_config=generation_config,
                        safety_settings=safety_settings
                    )
                    
                    # Process the response
                    result = {
                        "text": response.text,
                        "request_time": time.time(),
                        "model": self.model_name,
                    }
                    
                    # Add to history
                    self.history.append({
                        "role": "user",
                        "content": prompt
                    })
                    self.history.append({
                        "role": "assistant",
                        "content": response.text
                    })
                    
                    return result
                    
                except Exception as e:
                    if attempt < self.retry_attempts - 1:
                        print(f"Error in Gemini request (attempt {attempt+1}/{self.retry_attempts}): {str(e)}")
                        time.sleep(self.retry_delay)
                    else:
                        return {"error": f"Failed to get response from Gemini: {str(e)}"}
            
        except Exception as e:
            return {"error": f"Error preparing Gemini request: {str(e)}"}

    def format_prompt(self, 
                     user_input: str, 
                     context: Dict[str, Any] = None, 
                     screenshot_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Formats the user input into a prompt for the Gemini service.
        
        Args:
            user_input: The user's input/request
            context: Additional context information to include
            screenshot_path: Optional path to a screenshot to include
            
        Returns:
            Dictionary containing the formatted prompt and any images
        """
        # Build the prompt with context
        prompt_parts = []
        
        # Add system context
        prompt_parts.append(
            "You are an AI assistant that helps control a Windows 11 computer. "
            "You can see what's on the screen and can control the mouse and keyboard. "
            "You should analyze the screen content and decide what actions to take."
        )
        
        # Add user context if provided
        if context:
            prompt_parts.append("Current context:")
            for key, value in context.items():
                if isinstance(value, str):
                    prompt_parts.append(f"- {key}: {value}")
            prompt_parts.append("")
        
        # Add the user input
        prompt_parts.append(f"User request: {user_input}")
        
        # Add screenshot prompt if provided
        if screenshot_path:
            prompt_parts.append(
                "Below is a screenshot of the current screen. "
                "Please analyze it and suggest actions based on the user's request."
            )
            
        # Combine prompt parts
        formatted_prompt = "\n".join(prompt_parts)
        
        # Prepare images list
        images = []
        if screenshot_path and os.path.exists(screenshot_path):
            images.append(screenshot_path)
            
        return {
            "prompt": formatted_prompt,
            "images": images
        }

    def handle_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles and processes the response from the Gemini service.
        
        Args:
            response: Response dictionary from send_request
            
        Returns:
            Processed response with extracted actions
        """
        if "error" in response:
            return {"error": response["error"], "actions": []}
            
        text = response.get("text", "")
        
        # Try to extract structured actions from the response
        actions = []
        
        # Look for action blocks in the format [ACTION: action_type]
        import re
        action_matches = re.finditer(r'\[ACTION:\s*(\w+)(.*?)\]', text, re.DOTALL)
        
        for match in action_matches:
            action_type = match.group(1).strip()
            action_params_text = match.group(2).strip()
            
            # Try to parse parameters
            params = {}
            
            # Look for parameter patterns like param=value
            param_matches = re.finditer(r'(\w+)=([^,\]]+)', action_params_text)
            for param_match in param_matches:
                param_name = param_match.group(1).strip()
                param_value = param_match.group(2).strip()
                
                # Try to convert to appropriate types
                if param_value.isdigit():
                    param_value = int(param_value)
                elif param_value.replace('.', '', 1).isdigit():
                    param_value = float(param_value)
                
                params[param_name] = param_value
                
            actions.append({
                "type": action_type,
                "parameters": params
            })
        
        # If no structured actions were found, try to provide general reasoning
        if not actions:
            reasoning = text
        else:
            reasoning = text.split('[ACTION:', 1)[0].strip()
            
        return {
            "text": text,
            "actions": actions,
            "reasoning": reasoning
        }
        
    def reset_chat(self):
        """
        Resets the conversation history.
        """
        try:
            self.history = []
            self.chat = self.model.start_chat(history=[])
            return True
        except Exception as e:
            print(f"Error resetting chat: {str(e)}")
            return False