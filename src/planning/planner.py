import google.generativeai as genai
import json
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from src import config
from src.tools.base_tool import BaseTool

class ToolCall(BaseModel):
    name: str = Field(description="The name of the tool to be called.")
    args: Dict[str, Any] = Field(description="The arguments for the tool.")

class PlannerResponse(BaseModel):
    thought: str = Field(description="Your step-by-step reasoning for choosing the action based on the screenshot and history.")
    tool_call: ToolCall = Field(description="The tool to be executed to progress towards the goal.")

def _format_tools(tools: List[BaseTool]) -> str:
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

    request_payload = [
        system_prompt,
        {
            "mime_type": "image/png",
            "data": screen_b64
        }
    ]

    generation_config = genai.types.GenerationConfig(
        response_mime_type="application/json",
        response_schema=PlannerResponse
    )

    try:
        response = model.generate_content(
            request_payload,
            generation_config=generation_config
        )

        parsed_model_output = PlannerResponse.parse_raw(response.text)

        return json.loads(parsed_model_output.json())

    except Exception as e:
        error_message = f"An unexpected error occurred during the call to Gemini or during response parsing: {e}"
        print(error_message)
        # Attempt to get more detailed error information if available
        try:
            print(f"Gemini API Response: {response.text}")
        except:
            pass
        return {"error": error_message}
