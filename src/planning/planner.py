import google.generativeai as genai
import json
from typing import List, Dict, Any

from src import config
from src.tools.base_tool import BaseTool

def _format_tools(tools: List[BaseTool]) -> str:
    """Formats the list of tools into a string readable by the AI."""
    tool_strings = []
    for tool in tools:
        tool_strings.append(
            f"Tool Name: {tool.name}\nDescription: {tool.description}"
        )
    return "\n---\n".join(tool_strings)

def get_next_step(
    user_goal: str,
    memory_history: str,
    screen_b64: str,
    available_tools: List[BaseTool]
) -> Dict[str, Any]:

    print("--- Planner is thinking about the next step... ---")

    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.GEMINI_MODEL)

    system_prompt = f"""
You are DjenisAiAgent, an autonomous AI assistant that controls a Linux computer to achieve a goal.

CURRENT GOAL: {user_goal}

CONTEXT AND RULES:
1. Analyze the past action history and the current screenshot to understand the system's state.
2. Reason step-by-step to decide which single action gets you closer to the goal.
3. Choose ONLY ONE tool from the provided list. Your main goal is to eventually call the "task_completed" tool.
4. Your response MUST be a valid JSON code block and nothing else. Do not add any text or explanations outside the JSON.

AVAILABLE TOOLS:
---
{_format_tools(available_tools)}
---

RECENT ACTION HISTORY:
{memory_history}

REQUIRED RESPONSE FORMAT (JSON ONLY):
{{
  "thought": "Write your step-by-step reasoning here. Explain why you are choosing a certain tool and what information you are using to decide.",
  "tool": {{
    "name": "chosen_tool_name",
    "args": {{
      "argument_name_1": "argument_value_1",
      "argument_name_2": "argument_value_2"
    }}
  }}
}}
"""

    request_payload = [
        system_prompt,
        {
            "mime_type": "image/png",
            "data": screen_b64
        }
    ]

    try:
        response = model.generate_content(request_payload)
        response_text = response.text.strip()

        # Clean the response from potential markdown code markers
        if response_text.startswith("```json"):
            response_text = response_text[7:-3].strip()

        parsed_json = json.loads(response_text)
        return parsed_json

    except json.JSONDecodeError:
        error_message = f"Error: The AI did not respond with valid JSON. Response received:\n{response_text}"
        print(error_message)
        return {"error": error_message}
    except Exception as e:
        error_message = f"An unexpected error occurred during the call to Gemini: {e}"
        print(error_message)
        return {"error": error_message}
