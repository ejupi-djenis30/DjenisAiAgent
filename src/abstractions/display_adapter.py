class DisplayAdapter:
    def __init__(self):
        pass

    def show_message(self, message: str):
        """Display a message to the user."""
        print(message)

    def update_display(self, content: str):
        """Update the display with new content."""
        print(f"Updating display with content: {content}")

    def clear_display(self):
        """Clear the display."""
        print("Clearing display")