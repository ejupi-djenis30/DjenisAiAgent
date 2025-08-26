class BaseTool:
    def __init__(self):
        pass

    def execute(self):
        raise NotImplementedError("Subclasses should implement this method.")

    def configure(self, **kwargs):
        pass

    def cleanup(self):
        pass