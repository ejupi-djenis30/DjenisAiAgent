"""
Launch script for the DjenisAiAgent UI.

This script starts the graphical user interface for the agent.
"""
import sys
import os

# Add the parent directory to the path to import project modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ui.agent_ui import main

if __name__ == "__main__":
    main()
