from src.agent_core import AgentCore

def start_agent():
    """
    Initializes and starts the main lifecycle of the agent.
    """
    try:
        agent = AgentCore()
        agent.run()
    except Exception as e:
        print(f"\nA fatal error occurred that stopped the agent: {e}")
        print("Check your configuration, API key, and internet connection.")

if __name__ == "__main__":
    start_agent()
