from pydantic import BaseModel, Field
from typing import Dict, Any

class ToolCall(BaseModel):
    name: str = Field(description="The name of the tool to be called.")
    args: Dict[str, Any] = Field(description="The arguments for the tool, as a dictionary.")

class PlannerResponse(BaseModel):
    thought: str = Field(description="Your step-by-step reasoning for choosing the action based on the screenshot and history.")
    tool_call: ToolCall = Field(description="The tool to be executed to progress towards the goal.")
