class TaskCompletedTool:
    def __init__(self):
        self.completed_tasks = []

    def mark_task_completed(self, task_id):
        if task_id not in self.completed_tasks:
            self.completed_tasks.append(task_id)
            return True
        return False

    def get_completed_tasks(self):
        return self.completed_tasks

    def clear_completed_tasks(self):
        self.completed_tasks.clear()