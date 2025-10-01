"""
DjenisAiAgent - An intelligent UI automation agent.

This package provides AI-powered UI automation capabilities using Google's Gemini AI
for Windows 11 environments.
"""

__version__ = "0.1.0"
__author__ = "Djenis Ejupi"
__license__ = "MIT"

# Import main components for easier access
from src.agent_core import AgentCore
from src.config import Config

__all__ = ["AgentCore", "Config", "__version__"]
