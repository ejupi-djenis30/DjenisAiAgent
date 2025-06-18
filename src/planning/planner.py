import base64
from google import genai
from google.generativeai import types as genai_types
from typing import List, Dict, Any

from src import config
from src.planning.schemas import PlannerResponse

def _format_tools(tools: List[Dict[str, str]]) -> str:
    tool_strings = []
    for tool in tools:
        tool_strings.append(
            f"Tool Name: {tool['name']}\nDescription: {tool['description']}"
        )
    return "\n---\n".join(tool_strings)

def get_next_step(
    user_goal: str,
    memory_history: str,
    screen_b64: str,
    available_tools: List[Dict[str, str]]
) -> Dict[str, Any]:

    print("--- Planner is thinking about the next step... ---")

    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
    except Exception as e:
        return {"error": f"Failed to initialize Gemini Client: {e}"}

    system_prompt = f"""
You are DjenisAiAgent, an autonomous AI assistant that controls a Linux computer to achieve a goal.

CURRENT GOAL: {user_goal}

CONTEXT AND RULES:
1. Analyze the recent action history and the current screenshot to understand the system's state.
2. Reason step-by-step to decide which single action gets you closer to the goal. Your main objective is to eventually call the "task_completed" tool.
3. Your response MUST be a valid JSON that adheres to the required schema. Do not add any text or explanations outside the JSON.

AVAILABLE TOOLS:
---
{_format_tools(available_tools)}
---

RECENT ACTION HISTORY:
{memory_history}
"""

    request_contents = [
        system_prompt,
        genai_types.Part(
            inline_data=genai_types.Blob(
                mime_type="image/jpeg",
                data=base64.b64decode(screen_b64)
            )
        )
    ]

    generation_config = genai_types.GenerationConfig(
        response_mime_type="application/json",
        response_schema=PlannerResponse
    )

    try:
        model = client.get_model(f"models/{config.GEMINI_MODEL}")
        response = model.generate_content(
            contents=request_contents,
            generation_config=generation_config
        )

        parsed_model_output = PlannerResponse.parse_raw(response.text)
        return parsed_model_output.dict()

    except Exception as e:
        error_message = f"An unexpected error occurred during the call to Gemini or during response parsing: {e}"
        print(error_message)
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"Gemini API Response Text: {response.text}")

        return {"error": error_message}
